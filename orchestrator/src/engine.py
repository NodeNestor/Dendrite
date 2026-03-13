"""THE CORE — Recursive branching research engine.

Architecture:
    run_investigation(question) creates a ResearchTree, then:
    1. Creates root branch for the main question
    2. Calls run_branch() which iterates:
       a. Generate search queries
       b. Search all providers in parallel
       c. Fetch content, extract claims (bulk model, batched)
       d. Triage each claim: ACCEPT / VERIFY / DEEPEN / COUNTER
       e. Check convergence
    3. Process child branches recursively (depth-limited)
    4. Cross-validate important claims
    5. Synthesize final report
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from .config import Settings
from .convergence import check_convergence
from .llm.client import LLMClient
from .llm.batch import batch_complete
from .llm.prompts import (
    EXTRACTION_SYSTEM, QUERY_GENERATION_SYSTEM, SYNTHESIS_SYSTEM, TRIAGE_SYSTEM,
    extraction_prompt, query_generation_prompt, synthesis_prompt, triage_prompt,
)
from .models import (
    Branch, BranchType, Claim, ClaimStatus, Evidence,
    ProgressEvent, ResearchTree, TreeStatus,
)
from .providers import fetch_all, search_all
from .validation import cross_validate_claims

log = logging.getLogger(__name__)

ProgressCallback = asyncio.Queue[ProgressEvent] | None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_json(text: str) -> dict | list | None:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for sc, ec in [("{", "}"), ("[", "]")]:
            s = text.find(sc)
            e = text.rfind(ec)
            if s != -1 and e > s:
                try:
                    return json.loads(text[s:e + 1])
                except json.JSONDecodeError:
                    continue
        return None


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().rstrip(".").split())


def _is_duplicate(text: str, existing: set[str]) -> bool:
    key = _normalize(text)
    if key in existing:
        return True
    for ex in existing:
        shorter, longer = (key, ex) if len(key) <= len(ex) else (ex, key)
        if shorter in longer:
            return True
    return False


async def _emit(queue: ProgressCallback, event: ProgressEvent) -> None:
    if queue is not None:
        await queue.put(event)


# ══════════════════════════════════════════════════════════════════════
# Main entry point
# ══════════════════════════════════════════════════════════════════════

async def run_investigation(
    question: str,
    settings: Settings,
    progress: ProgressCallback = None,
    tree: ResearchTree | None = None,
) -> ResearchTree:
    """Execute the full recursive research pipeline."""
    if tree is None:
        tree = ResearchTree(
            question=question,
            max_depth=settings.max_depth,
            max_branch_iterations=settings.max_branch_iterations,
            verification_threshold=settings.verification_threshold,
        )

    tree.status = TreeStatus.RUNNING

    bulk_client = LLMClient(settings.bulk_llm)
    synthesis_client = LLMClient(settings.synthesis_llm)

    try:
        # Create root branch
        root = Branch(
            question=question,
            branch_type=BranchType.INVESTIGATION,
            depth=0,
            max_iterations=settings.max_branch_iterations,
        )
        tree.root_branch_id = root.id
        tree.add_branch(root)

        await _emit(progress, ProgressEvent(
            tree_id=tree.id,
            branch_id=root.id,
            event_type="tree_started",
            message=f"Starting investigation: {question}",
        ))

        # Run the root branch (which recursively spawns child branches)
        await _run_branch(
            tree=tree,
            branch=root,
            settings=settings,
            bulk_client=bulk_client,
            synthesis_client=synthesis_client,
            progress=progress,
            visited_urls=set(),
            seen_claims=set(),
        )

        # Cross-validate all pending claims
        await _emit(progress, ProgressEvent(
            tree_id=tree.id,
            event_type="validation_started",
            message="Cross-validating claims...",
        ))

        all_claims = tree.all_claims()
        pending_with_queries = [
            c for c in all_claims
            if c.status == ClaimStatus.PENDING and c.verification_query
        ]

        if pending_with_queries:
            async def _search(queries):
                return await search_all(queries)

            async def _fetch(urls):
                return await fetch_all(urls)

            await cross_validate_claims(
                pending_with_queries,
                search_fn=_search,
                fetch_fn=_fetch,
                synthesis_client=synthesis_client,
                max_concurrent_verifications=settings.max_concurrent_verifications,
                verification_fetch_count=settings.verification_fetch_count,
            )

        # Auto-verify claims with multiple independent sources
        for claim in all_claims:
            if claim.status == ClaimStatus.PENDING:
                if claim.independent_sources >= settings.min_independent_sources:
                    claim.status = ClaimStatus.VERIFIED
                    claim.confidence = min(0.8 + 0.05 * claim.independent_sources, 1.0)

        # Synthesize final report
        await _emit(progress, ProgressEvent(
            tree_id=tree.id,
            event_type="synthesis_started",
            message="Synthesizing final report...",
        ))

        tree.synthesis = await _synthesize(
            tree, question, synthesis_client, settings,
        )

        tree.status = TreeStatus.CONVERGED
        tree.finished_at = _now()
        tree.update_stats()

        await _emit(progress, ProgressEvent(
            tree_id=tree.id,
            event_type="tree_complete",
            message=(
                f"Complete! {tree.total_claims} claims "
                f"({tree.verified_claims} verified, "
                f"{tree.refuted_claims} refuted, "
                f"{tree.contested_claims} contested)"
            ),
            data={
                "total_claims": tree.total_claims,
                "verified_claims": tree.verified_claims,
                "refuted_claims": tree.refuted_claims,
                "contested_claims": tree.contested_claims,
            },
        ))

        return tree

    except Exception as e:
        log.error("Investigation failed: %s", e, exc_info=True)
        tree.status = TreeStatus.FAILED
        tree.finished_at = _now()
        tree.synthesis = f"Investigation failed: {e}"

        await _emit(progress, ProgressEvent(
            tree_id=tree.id,
            event_type="tree_failed",
            message=f"Failed: {e}",
        ))

        return tree
    finally:
        await bulk_client.close()
        await synthesis_client.close()


# ══════════════════════════════════════════════════════════════════════
# Branch execution — the recursive core
# ══════════════════════════════════════════════════════════════════════

async def _run_branch(
    tree: ResearchTree,
    branch: Branch,
    settings: Settings,
    bulk_client: LLMClient,
    synthesis_client: LLMClient,
    progress: ProgressCallback,
    visited_urls: set[str],
    seen_claims: set[str],
) -> None:
    """Run a single branch through search-extract-triage iterations."""

    await _emit(progress, ProgressEvent(
        tree_id=tree.id,
        branch_id=branch.id,
        event_type="branch_started",
        message=f"[depth={branch.depth}] {branch.branch_type.value}: {branch.question}",
    ))

    # Track child branches to process after this branch converges
    child_branches: list[Branch] = []

    for iteration in range(branch.max_iterations):
        branch.iteration = iteration + 1
        claims_before = len(branch.claims)

        # 1. Generate search queries
        existing_claims_text = "\n".join(
            f"- [{c.status.value}] {c.content}" for c in branch.claims
        ) if branch.claims else ""

        query_batch = await batch_complete(
            bulk_client,
            [query_generation_prompt(branch.question, existing_claims_text, iteration)],
            system=QUERY_GENERATION_SYSTEM,
            max_tokens=1024,
            thinking=False,
        )
        tree.llm_prompt_tokens += query_batch.total_prompt_tokens
        tree.llm_completion_tokens += query_batch.total_completion_tokens
        tree.llm_requests += query_batch.successful + query_batch.failed

        queries: list[str] = []
        if query_batch.texts and query_batch.texts[0]:
            parsed = _parse_json(query_batch.texts[0])
            if isinstance(parsed, list):
                queries = [str(q) for q in parsed if isinstance(q, str)]

        if not queries:
            queries = [branch.question]

        branch.queries_used.extend(queries)

        # 2. Search all providers
        search_results = await search_all(queries, max_per_provider=settings.results_per_provider)
        new_results = [r for r in search_results if r.url not in visited_urls]

        if not new_results:
            log.info("Branch %s: no new URLs at iteration %d", branch.id, iteration)
            break

        branch.urls_searched += len(new_results)

        # 3. Fetch content
        urls_to_fetch = [r.url for r in new_results[:settings.urls_per_iteration]]
        fetched = await fetch_all(urls_to_fetch, max_concurrent=settings.max_concurrent_fetches)
        visited_urls.update(f.url for f in fetched)
        good_pages = [f for f in fetched if f.text and not f.error]
        branch.pages_fetched += len(good_pages)
        tree.pages_fetched += len(good_pages)

        if not good_pages:
            continue

        # 4. Extract claims (batched)
        extraction_prompts = [
            extraction_prompt(p.text[:8000], p.url, branch.question)
            for p in good_pages
        ]

        extraction_batch = await batch_complete(
            bulk_client,
            extraction_prompts,
            system=EXTRACTION_SYSTEM,
            max_tokens=2048,
            thinking=False,
            temperature=0.1,
        )
        tree.llm_prompt_tokens += extraction_batch.total_prompt_tokens
        tree.llm_completion_tokens += extraction_batch.total_completion_tokens
        tree.llm_requests += extraction_batch.successful + extraction_batch.failed

        # Parse extractions and build claims
        new_claims: list[Claim] = []
        for page, response in zip(good_pages, extraction_batch.texts):
            if not response:
                continue
            parsed = _parse_json(response)
            if not isinstance(parsed, dict):
                continue

            quality = parsed.get("quality", 5)
            if isinstance(quality, str):
                try:
                    quality = int(float(quality))
                except (ValueError, TypeError):
                    quality = 5
            if quality < 3:
                continue

            for c in parsed.get("claims", []):
                if not isinstance(c, dict):
                    continue
                claim_text = c.get("claim", "")
                if not claim_text or _is_duplicate(claim_text, seen_claims):
                    continue

                seen_claims.add(_normalize(claim_text))
                claim = Claim(
                    content=claim_text,
                    confidence=float(c.get("confidence", 0.5)),
                    source_urls=[page.url],
                    evidence_for=[Evidence(
                        content=claim_text,
                        source_url=page.url,
                        source_title=page.title,
                        provider=page.provider,
                        source_date=page.source_date,
                        confidence=float(c.get("confidence", 0.5)),
                    )],
                )
                new_claims.append(claim)

        if not new_claims:
            continue

        await _emit(progress, ProgressEvent(
            tree_id=tree.id,
            branch_id=branch.id,
            event_type="claims_extracted",
            message=f"Extracted {len(new_claims)} claims from {len(good_pages)} pages",
            data={"new_claims": len(new_claims), "pages": len(good_pages)},
        ))

        # 5. Triage new claims
        claims_text = "\n".join(
            f"[{i}] {c.content} (confidence: {c.confidence:.1f})"
            for i, c in enumerate(new_claims)
        )
        existing_text = "\n".join(
            f"- [{c.status.value}] {c.content}" for c in branch.claims
        ) if branch.claims else ""

        triage_batch = await batch_complete(
            bulk_client,
            [triage_prompt(claims_text, existing_text, branch.question)],
            system=TRIAGE_SYSTEM,
            max_tokens=4096,
            thinking=False,
        )
        tree.llm_prompt_tokens += triage_batch.total_prompt_tokens
        tree.llm_completion_tokens += triage_batch.total_completion_tokens
        tree.llm_requests += triage_batch.successful + triage_batch.failed

        # Apply triage decisions
        triage_decisions = {}
        if triage_batch.texts and triage_batch.texts[0]:
            parsed = _parse_json(triage_batch.texts[0])
            if isinstance(parsed, dict):
                for d in parsed.get("decisions", []):
                    if isinstance(d, dict) and "index" in d:
                        triage_decisions[d["index"]] = d

        for i, claim in enumerate(new_claims):
            decision = triage_decisions.get(i, {})
            action = decision.get("action", "ACCEPT").upper()

            if action == "DUPLICATE":
                continue

            if action == "ACCEPT":
                claim.status = ClaimStatus.ACCEPTED
                claim.confidence = max(claim.confidence, 0.7)
                branch.claims.append(claim)

            elif action == "VERIFY":
                claim.verification_query = decision.get("query", "")
                branch.claims.append(claim)

                # Spawn verification branch if we have depth budget
                if branch.depth + 1 < tree.max_depth and claim.verification_query:
                    child = Branch(
                        question=f"Verify: {claim.content}",
                        branch_type=BranchType.VERIFICATION,
                        parent_branch_id=branch.id,
                        parent_claim_id=claim.id,
                        depth=branch.depth + 1,
                        max_iterations=settings.verification_iterations,
                    )
                    tree.add_branch(child)
                    child_branches.append(child)

                    await _emit(progress, ProgressEvent(
                        tree_id=tree.id,
                        branch_id=branch.id,
                        event_type="claim_triaged",
                        message=f"VERIFY: {claim.content[:60]}...",
                        data={"action": "VERIFY", "child_branch": child.id},
                    ))

            elif action == "DEEPEN":
                claim.status = ClaimStatus.ACCEPTED
                claim.deepening_question = decision.get("sub_question", "")
                branch.claims.append(claim)

                if branch.depth + 1 < tree.max_depth and claim.deepening_question:
                    child = Branch(
                        question=claim.deepening_question,
                        branch_type=BranchType.DEEPENING,
                        parent_branch_id=branch.id,
                        parent_claim_id=claim.id,
                        depth=branch.depth + 1,
                        max_iterations=settings.max_branch_iterations,
                    )
                    tree.add_branch(child)
                    child_branches.append(child)

                    await _emit(progress, ProgressEvent(
                        tree_id=tree.id,
                        branch_id=branch.id,
                        event_type="claim_triaged",
                        message=f"DEEPEN: {claim.deepening_question[:60]}...",
                        data={"action": "DEEPEN", "child_branch": child.id},
                    ))

            elif action == "COUNTER":
                branch.claims.append(claim)
                counter_query = decision.get("query", "")

                if branch.depth + 1 < tree.max_depth and counter_query:
                    child = Branch(
                        question=f"Counter-evidence: {claim.content}",
                        branch_type=BranchType.COUNTER,
                        parent_branch_id=branch.id,
                        parent_claim_id=claim.id,
                        depth=branch.depth + 1,
                        max_iterations=settings.verification_iterations,
                    )
                    tree.add_branch(child)
                    child_branches.append(child)

                    await _emit(progress, ProgressEvent(
                        tree_id=tree.id,
                        branch_id=branch.id,
                        event_type="claim_triaged",
                        message=f"COUNTER: {claim.content[:60]}...",
                        data={"action": "COUNTER", "child_branch": child.id},
                    ))

            else:
                # Default: accept
                branch.claims.append(claim)

        # 6. Check convergence
        new_claims_count = len(branch.claims) - claims_before
        convergence = await check_convergence(
            branch=branch,
            new_claims_this_iteration=new_claims_count,
            max_iterations=branch.max_iterations,
            client=bulk_client if iteration >= 1 else None,
            min_iterations=settings.min_convergence_iterations,
            diminishing_returns_threshold=settings.diminishing_returns_threshold,
            coverage_target=settings.coverage_target,
        )

        log.info(
            "Branch %s iteration %d: %d new claims, converged=%s (%s)",
            branch.id, iteration + 1, new_claims_count,
            convergence.converged, convergence.reason,
        )

        if convergence.converged:
            branch.converged = True
            branch.convergence_reason = convergence.reason
            break

    branch.finished_at = _now()

    await _emit(progress, ProgressEvent(
        tree_id=tree.id,
        branch_id=branch.id,
        event_type="branch_converged",
        message=f"Branch done: {len(branch.claims)} claims, {branch.convergence_reason or 'max iterations'}",
        data={"claims": len(branch.claims), "iterations": branch.iteration},
    ))

    # Process child branches recursively
    if child_branches:
        log.info("Processing %d child branches for branch %s", len(child_branches), branch.id)
        for child in child_branches:
            # Verification and counter branches need their own seen_claims
            # so they can independently find the same claim from different sources
            # (finding it again = confirmation, not a duplicate)
            if child.branch_type in (BranchType.VERIFICATION, BranchType.COUNTER):
                child_seen = set()  # fresh set — independent search
            else:
                child_seen = seen_claims  # deepening shares parent dedup

            await _run_branch(
                tree=tree,
                branch=child,
                settings=settings,
                bulk_client=bulk_client,
                synthesis_client=synthesis_client,
                progress=progress,
                visited_urls=visited_urls,
                seen_claims=child_seen,
            )

            # If this was a verification branch, update the parent claim
            if child.branch_type == BranchType.VERIFICATION and child.parent_claim_id:
                parent_claim = None
                for c in branch.claims:
                    if c.id == child.parent_claim_id:
                        parent_claim = c
                        break

                if parent_claim and child.claims:
                    # Check if child branch found supporting evidence
                    supporting = sum(1 for c in child.claims if c.status in (ClaimStatus.ACCEPTED, ClaimStatus.VERIFIED))
                    contradicting = sum(1 for c in child.claims if c.status == ClaimStatus.REFUTED)

                    if supporting > contradicting:
                        parent_claim.status = ClaimStatus.VERIFIED
                        parent_claim.confidence = min(0.8 + 0.05 * supporting, 1.0)
                    elif contradicting > supporting:
                        parent_claim.status = ClaimStatus.REFUTED
                        parent_claim.confidence = 0.2
                    else:
                        parent_claim.status = ClaimStatus.CONTESTED

            # Counter branches: mark original claim as contested if counter-evidence found
            if child.branch_type == BranchType.COUNTER and child.parent_claim_id:
                parent_claim = None
                for c in branch.claims:
                    if c.id == child.parent_claim_id:
                        parent_claim = c
                        break

                if parent_claim and child.claims:
                    parent_claim.status = ClaimStatus.CONTESTED
                    for counter_claim in child.claims:
                        parent_claim.evidence_against.append(Evidence(
                            content=counter_claim.content,
                            source_url=counter_claim.source_urls[0] if counter_claim.source_urls else "",
                            provider="counter-branch",
                            supports_claim=False,
                            confidence=counter_claim.confidence,
                        ))


# ══════════════════════════════════════════════════════════════════════
# Synthesis
# ══════════════════════════════════════════════════════════════════════

async def _synthesize(
    tree: ResearchTree,
    question: str,
    client: LLMClient,
    settings: Settings,
) -> str:
    """Generate the final synthesis report from verified claims."""
    all_claims = tree.all_claims()
    if not all_claims:
        return ""

    # Build claims text with status
    claims_text = "\n".join(
        f"[{c.status.value.upper()}] (confidence={c.confidence:.2f}) {c.content} "
        f"(sources: {', '.join(c.source_urls[:3])})"
        for c in all_claims
    )

    # Build tree structure summary
    tree_lines = []
    if tree.root_branch_id:
        _build_tree_summary(tree, tree.root_branch_id, tree_lines, indent=0)
    tree_structure = "\n".join(tree_lines)

    result = await batch_complete(
        client,
        [synthesis_prompt(question, claims_text, tree_structure)],
        system=SYNTHESIS_SYSTEM,
        max_tokens=settings.synthesis_max_tokens,
        thinking=False,
        temperature=0.3,
    )
    tree.llm_prompt_tokens += result.total_prompt_tokens
    tree.llm_completion_tokens += result.total_completion_tokens
    tree.llm_requests += result.successful + result.failed

    return result.texts[0] if result.texts else ""


def _build_tree_summary(tree: ResearchTree, branch_id: str, lines: list[str], indent: int) -> None:
    branch = tree.get_branch(branch_id)
    if not branch:
        return

    prefix = "  " * indent
    type_icon = {"investigation": "+", "verification": "?", "deepening": "v", "counter": "!"}
    icon = type_icon.get(branch.branch_type.value, "-")

    lines.append(f"{prefix}{icon} {branch.question} [{len(branch.claims)} claims]")

    for child_id in branch.child_branch_ids:
        _build_tree_summary(tree, child_id, lines, indent + 1)
