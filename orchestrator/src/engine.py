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
    5. Resolve contradictions
    6. Synthesize final report
    7. Self-critique and refine (multi-turn)
    8. Store verified claims to HiveMindDB (feedback loop)
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
    RESOLUTION_SYSTEM, REFINEMENT_SYSTEM,
    extraction_prompt, query_generation_prompt, synthesis_prompt, triage_prompt,
    resolution_prompt, refinement_prompt,
)
from .models import (
    Branch, BranchType, Claim, ClaimStatus, Evidence,
    ProgressEvent, ResearchTree, TreeStatus,
)
from .providers import fetch_all, search_all
from .semantic_dedup import SemanticDeduplicator
from .source_quality import score_source
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

        # Initialize semantic deduplicator
        dedup = SemanticDeduplicator(threshold=settings.semantic_dedup_threshold)

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
            dedup=dedup,
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
                    claim.status_history.append(f"auto-verified: {claim.independent_sources} independent sources")
                    claim.updated_at = _now()

        # ── Contradiction Resolution ──────────────────────────────────
        if settings.enable_contradiction_resolution:
            await _emit(progress, ProgressEvent(
                tree_id=tree.id,
                event_type="resolution_started",
                message="Resolving contradictions...",
            ))
            await _resolve_contradictions(
                tree, all_claims, synthesis_client, settings, progress,
            )

        # ── Synthesize final report ───────────────────────────────────
        await _emit(progress, ProgressEvent(
            tree_id=tree.id,
            event_type="synthesis_started",
            message="Synthesizing final report...",
        ))

        tree.synthesis = await _synthesize(
            tree, question, synthesis_client, settings,
        )

        # ── Multi-Turn Refinement ─────────────────────────────────────
        if settings.enable_refinement and settings.max_refinement_passes > 0:
            await _refine(
                tree, question, settings, bulk_client, synthesis_client,
                progress, dedup,
            )

        # ── HiveMindDB Feedback Loop ─────────────────────────────────
        if settings.enable_hivemind_feedback:
            await _store_to_hivemind(tree, settings, progress)

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
    dedup: SemanticDeduplicator,
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

        # 1. Generate search queries (improved strategy per iteration)
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

        # 3. Fetch content (with caching via provider registry)
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

        # Parse extractions and build claims with source quality scoring
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

            # Score the source
            sq = score_source(
                url=page.url,
                source_date=page.source_date,
                provider=page.provider,
                recency_weight=settings.recency_weight,
            )

            for c in parsed.get("claims", []):
                if not isinstance(c, dict):
                    continue
                claim_text = c.get("claim", "")
                if not claim_text:
                    continue

                # String-based dedup (fast)
                if _is_duplicate(claim_text, seen_claims):
                    continue

                # Semantic dedup (TF-IDF cosine)
                dedup_result = dedup.add_claim(claim_text)
                if dedup_result.is_duplicate:
                    log.debug(
                        "Semantic duplicate (%.2f): %s ~= %s",
                        dedup_result.similarity, claim_text[:60], dedup_result.matched_claim[:60] if dedup_result.matched_claim else "",
                    )
                    continue

                seen_claims.add(_normalize(claim_text))

                # Adjust confidence based on source quality
                raw_confidence = float(c.get("confidence", 0.5))
                adjusted_confidence = (
                    raw_confidence * (1 - settings.source_quality_weight)
                    + sq.overall * settings.source_quality_weight
                )

                claim = Claim(
                    content=claim_text,
                    confidence=adjusted_confidence,
                    source_urls=[page.url],
                    evidence_for=[Evidence(
                        content=claim_text,
                        source_url=page.url,
                        source_title=page.title,
                        provider=page.provider,
                        source_date=page.source_date,
                        confidence=adjusted_confidence,
                        source_quality=sq.overall,
                        source_type=sq.source_type,
                        source_authority=sq.authority,
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
                claim.status_history.append("triaged: ACCEPT")
                branch.claims.append(claim)

            elif action == "VERIFY":
                claim.verification_query = decision.get("query", "")
                claim.status_history.append(f"triaged: VERIFY (query={claim.verification_query})")
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
                claim.status_history.append(f"triaged: DEEPEN (q={claim.deepening_question})")
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
                claim.status_history.append("triaged: COUNTER")
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
            # Verification, counter, and resolution branches need their own seen_claims
            # so they can independently find the same claim from different sources
            # (finding it again = confirmation, not a duplicate)
            if child.branch_type in (BranchType.VERIFICATION, BranchType.COUNTER, BranchType.RESOLUTION):
                child_seen = set()  # fresh set — independent search
                child_dedup = SemanticDeduplicator(threshold=settings.semantic_dedup_threshold)
            else:
                child_seen = seen_claims  # deepening shares parent dedup
                child_dedup = dedup

            await _run_branch(
                tree=tree,
                branch=child,
                settings=settings,
                bulk_client=bulk_client,
                synthesis_client=synthesis_client,
                progress=progress,
                visited_urls=visited_urls,
                seen_claims=child_seen,
                dedup=child_dedup,
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

                    old_status = parent_claim.status
                    if supporting > contradicting:
                        parent_claim.status = ClaimStatus.VERIFIED
                        parent_claim.confidence = min(0.8 + 0.05 * supporting, 1.0)
                    elif contradicting > supporting:
                        parent_claim.status = ClaimStatus.REFUTED
                        parent_claim.confidence = 0.2
                    else:
                        parent_claim.status = ClaimStatus.CONTESTED

                    parent_claim.updated_at = _now()
                    parent_claim.status_history.append(
                        f"verification: {old_status.value} -> {parent_claim.status.value} "
                        f"(+{supporting}/-{contradicting})"
                    )

            # Counter branches: mark original claim as contested if counter-evidence found
            if child.branch_type == BranchType.COUNTER and child.parent_claim_id:
                parent_claim = None
                for c in branch.claims:
                    if c.id == child.parent_claim_id:
                        parent_claim = c
                        break

                if parent_claim and child.claims:
                    parent_claim.status = ClaimStatus.CONTESTED
                    parent_claim.updated_at = _now()
                    parent_claim.status_history.append("counter-evidence found")
                    for counter_claim in child.claims:
                        parent_claim.evidence_against.append(Evidence(
                            content=counter_claim.content,
                            source_url=counter_claim.source_urls[0] if counter_claim.source_urls else "",
                            provider="counter-branch",
                            supports_claim=False,
                            confidence=counter_claim.confidence,
                        ))


# ══════════════════════════════════════════════════════════════════════
# Contradiction Resolution
# ══════════════════════════════════════════════════════════════════════

async def _resolve_contradictions(
    tree: ResearchTree,
    all_claims: list[Claim],
    client: LLMClient,
    settings: Settings,
    progress: ProgressCallback,
) -> None:
    """Find contested claims and attempt to resolve contradictions."""
    contested = [c for c in all_claims if c.status == ClaimStatus.CONTESTED]
    if not contested:
        return

    log.info("Resolving %d contested claims", len(contested))

    for claim in contested:
        if not claim.evidence_against:
            continue

        # Build evidence summaries
        evidence_for_text = "\n".join(
            f"- {e.content} (source: {e.source_url}, quality: {e.source_quality:.2f})"
            for e in claim.evidence_for[:5]
        )
        sources_for = ", ".join(e.source_url for e in claim.evidence_for[:3])

        evidence_against_text = "\n".join(
            f"- {e.content} (source: {e.source_url}, quality: {e.source_quality:.2f})"
            for e in claim.evidence_against[:5]
        )
        sources_against = ", ".join(e.source_url for e in claim.evidence_against[:3])

        # Get the main counter-claim text
        counter_claim_text = claim.evidence_against[0].content if claim.evidence_against else "Unknown counter-evidence"

        try:
            result = await client.complete(
                messages=[
                    {"role": "system", "content": RESOLUTION_SYSTEM},
                    {"role": "user", "content": resolution_prompt(
                        claim_a=claim.content,
                        evidence_a=evidence_for_text,
                        sources_a=sources_for,
                        claim_b=counter_claim_text,
                        evidence_b=evidence_against_text,
                        sources_b=sources_against,
                        research_question=tree.question,
                    )},
                ],
                max_tokens=2048,
                thinking=False,
                temperature=0.2,
            )
            tree.llm_prompt_tokens += result.prompt_tokens
            tree.llm_completion_tokens += result.completion_tokens
            tree.llm_requests += 1

            parsed = _parse_json(result.text)
            if not isinstance(parsed, dict):
                continue

            verdict = parsed.get("verdict", "UNRESOLVABLE").upper()
            confidence = float(parsed.get("confidence", 0.5))
            resolution_text = parsed.get("resolution", "")

            if verdict == "A_STRONGER":
                claim.status = ClaimStatus.VERIFIED
                claim.confidence = confidence
                claim.status_history.append(f"resolution: A_STRONGER — {resolution_text[:100]}")
            elif verdict == "B_STRONGER":
                claim.status = ClaimStatus.REFUTED
                claim.confidence = 1.0 - confidence
                claim.status_history.append(f"resolution: B_STRONGER — {resolution_text[:100]}")
            elif verdict == "BOTH_PARTIAL":
                claim.status = ClaimStatus.CONTESTED
                claim.confidence = 0.5
                claim.status_history.append(f"resolution: BOTH_PARTIAL — {resolution_text[:100]}")
            # UNRESOLVABLE: leave as contested

            claim.updated_at = _now()

            await _emit(progress, ProgressEvent(
                tree_id=tree.id,
                event_type="contradiction_resolved",
                message=f"Resolved: {claim.content[:60]}... → {verdict}",
                data={"verdict": verdict, "confidence": confidence},
            ))

        except Exception as e:
            log.warning("Resolution failed for claim: %s", e)


# ══════════════════════════════════════════════════════════════════════
# Multi-Turn Refinement
# ══════════════════════════════════════════════════════════════════════

async def _refine(
    tree: ResearchTree,
    question: str,
    settings: Settings,
    bulk_client: LLMClient,
    synthesis_client: LLMClient,
    progress: ProgressCallback,
    dedup: SemanticDeduplicator,
) -> None:
    """Self-critique synthesis and do targeted follow-up research."""
    for pass_num in range(settings.max_refinement_passes):
        tree.refinement_pass = pass_num + 1

        await _emit(progress, ProgressEvent(
            tree_id=tree.id,
            event_type="refinement_started",
            message=f"Refinement pass {pass_num + 1}...",
        ))

        # Build claim summary for critique
        all_claims = tree.all_claims()
        claim_summary = "\n".join(
            f"[{c.status.value}] (conf={c.confidence:.2f}) {c.content}"
            for c in all_claims
        )

        # Self-critique
        try:
            result = await synthesis_client.complete(
                messages=[
                    {"role": "system", "content": REFINEMENT_SYSTEM},
                    {"role": "user", "content": refinement_prompt(
                        question, tree.synthesis, claim_summary,
                    )},
                ],
                max_tokens=2048,
                thinking=False,
                temperature=0.3,
            )
            tree.llm_prompt_tokens += result.prompt_tokens
            tree.llm_completion_tokens += result.completion_tokens
            tree.llm_requests += 1

            parsed = _parse_json(result.text)
            if not isinstance(parsed, dict):
                break

            quality = float(parsed.get("quality_score", 0.8))
            needs_more = parsed.get("needs_more_research", False)
            follow_ups = parsed.get("follow_up_queries", [])

            if not needs_more or quality >= 0.85 or not follow_ups:
                log.info("Refinement pass %d: quality=%.2f, no more research needed", pass_num + 1, quality)
                break

            # Execute follow-up searches
            for fup in follow_ups[:3]:  # max 3 follow-ups per pass
                fup_question = fup.get("question", "")
                fup_query = fup.get("search_query", fup_question)

                if not fup_query:
                    continue

                await _emit(progress, ProgressEvent(
                    tree_id=tree.id,
                    event_type="refinement_search",
                    message=f"Follow-up: {fup_question[:60]}...",
                ))

                # Create a refinement branch
                root = tree.get_branch(tree.root_branch_id) if tree.root_branch_id else None
                if root and root.depth + 1 < tree.max_depth:
                    child = Branch(
                        question=fup_question,
                        branch_type=BranchType.DEEPENING,
                        parent_branch_id=tree.root_branch_id,
                        depth=1,
                        max_iterations=2,
                    )
                    tree.add_branch(child)

                    await _run_branch(
                        tree=tree,
                        branch=child,
                        settings=settings,
                        bulk_client=bulk_client,
                        synthesis_client=synthesis_client,
                        progress=progress,
                        visited_urls=set(),
                        seen_claims=set(),
                        dedup=dedup,
                    )

            # Re-synthesize with new data
            tree.synthesis = await _synthesize(
                tree, question, synthesis_client, settings,
            )

        except Exception as e:
            log.warning("Refinement pass %d failed: %s", pass_num + 1, e)
            break


# ══════════════════════════════════════════════════════════════════════
# HiveMindDB Feedback Loop
# ══════════════════════════════════════════════════════════════════════

async def _store_to_hivemind(
    tree: ResearchTree,
    settings: Settings,
    progress: ProgressCallback,
) -> None:
    """Store verified claims to HiveMindDB for future research."""
    try:
        from .storage.hivemind import HiveMindClient
        from .storage.models import MemoryCreate, MemoryType

        client = HiveMindClient(settings.hivemind_url)
        verified_claims = [
            c for c in tree.all_claims()
            if c.status in (ClaimStatus.VERIFIED, ClaimStatus.ACCEPTED) and c.confidence >= 0.7
        ]

        if not verified_claims:
            return

        stored = 0
        for claim in verified_claims[:50]:  # cap at 50 per tree
            sources = ", ".join(claim.source_urls[:3])
            memory = MemoryCreate(
                content=f"{claim.content} [sources: {sources}]",
                memory_type=MemoryType.FACT,
                agent_id="dendrite",
                tags=["dendrite", f"tree:{tree.id}", "verified"],
                metadata={
                    "tree_id": tree.id,
                    "question": tree.question,
                    "confidence": claim.confidence,
                    "source_urls": claim.source_urls[:5],
                    "status": claim.status.value,
                },
            )
            result = await client.create_memory(memory)
            if result:
                stored += 1

        await client.close()

        if stored > 0:
            await _emit(progress, ProgressEvent(
                tree_id=tree.id,
                event_type="hivemind_stored",
                message=f"Stored {stored} verified claims to HiveMindDB",
                data={"stored": stored},
            ))

        log.info("Stored %d/%d verified claims to HiveMindDB", stored, len(verified_claims))

    except Exception as e:
        log.warning("HiveMindDB feedback failed: %s", e)


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

    # Build claims text with status and source quality
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
    type_icon = {
        "investigation": "+", "verification": "?", "deepening": "v",
        "counter": "!", "resolution": "~",
    }
    icon = type_icon.get(branch.branch_type.value, "-")

    lines.append(f"{prefix}{icon} {branch.question} [{len(branch.claims)} claims]")

    for child_id in branch.child_branch_ids:
        _build_tree_summary(tree, child_id, lines, indent + 1)
