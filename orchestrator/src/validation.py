"""Three-pass cross-validation — adapted from Spindeln's fact_validator."""

from __future__ import annotations

import asyncio
import json
import logging

from .llm.client import LLMClient
from .llm.batch import batch_complete
from .llm.prompts import (
    VALIDATION_SYSTEM, validation_prompt,
    SOURCE_INDEPENDENCE_SYSTEM, source_independence_prompt,
)
from .models import Claim, ClaimStatus, Evidence
from .providers.base import FetchedContent, SearchHit

log = logging.getLogger(__name__)


async def cross_validate_claims(
    claims: list[Claim],
    search_fn,
    fetch_fn,
    synthesis_client: LLMClient,
    max_concurrent_verifications: int = 3,
) -> list[Claim]:
    """Three-pass cross-validation of claims.

    Pass 1: Rate all claims (already done by triage — claims have statuses)
    Pass 2: For claims needing verification, search independently and compare
    Pass 3: Source independence check

    Args:
        claims: Claims to validate
        search_fn: async fn(queries) -> list[SearchHit]
        fetch_fn: async fn(urls) -> list[FetchedContent]
        synthesis_client: LLM client for validation
    """
    needs_verification = [c for c in claims if c.verification_query and c.status == ClaimStatus.PENDING]

    if not needs_verification:
        return claims

    log.info("Cross-validating %d claims", len(needs_verification))

    sem = asyncio.Semaphore(max_concurrent_verifications)

    async def _verify_one(claim: Claim) -> None:
        async with sem:
            await _verify_claim(claim, search_fn, fetch_fn, synthesis_client)

    await asyncio.gather(*[_verify_one(c) for c in needs_verification], return_exceptions=True)

    log.info(
        "Validation complete: %d verified, %d refuted, %d contested",
        sum(1 for c in claims if c.status == ClaimStatus.VERIFIED),
        sum(1 for c in claims if c.status == ClaimStatus.REFUTED),
        sum(1 for c in claims if c.status == ClaimStatus.CONTESTED),
    )

    return claims


async def _verify_claim(
    claim: Claim,
    search_fn,
    fetch_fn,
    client: LLMClient,
) -> None:
    """Verify a single claim via independent search + LLM comparison."""
    if not claim.verification_query:
        return

    log.info("Verifying: %.60s (query: %s)", claim.content, claim.verification_query)

    # Search for independent evidence
    try:
        hits: list[SearchHit] = await search_fn([claim.verification_query])
    except Exception as e:
        log.warning("Verification search failed for claim: %s", e)
        return

    if not hits:
        log.info("No verification results found — claim remains pending")
        return

    # Fetch top results
    urls = [h.url for h in hits[:3]]
    try:
        fetched: list[FetchedContent] = await fetch_fn(urls)
    except Exception as e:
        log.warning("Verification fetch failed: %s", e)
        return

    good_pages = [f for f in fetched if f.text and not f.error]
    if not good_pages:
        return

    # Build verification context
    verification_texts = "\n\n---\n\n".join(
        f"Source: {p.url}\nTitle: {p.title}\n{p.text[:3000]}"
        for p in good_pages
    )

    original_source = claim.source_urls[0] if claim.source_urls else "unknown"

    # Ask LLM to compare
    try:
        result = await client.complete(
            messages=[
                {"role": "system", "content": VALIDATION_SYSTEM},
                {"role": "user", "content": validation_prompt(
                    claim.content, original_source, verification_texts
                )},
            ],
            max_tokens=1024,
            thinking=False,
            temperature=0.1,
        )

        parsed = _parse_json(result.text)
        if not isinstance(parsed, dict):
            return

        verdict = parsed.get("verdict", "INSUFFICIENT").upper()
        confidence = float(parsed.get("confidence", 0.5))
        source_independent = parsed.get("source_independent", True)
        reason = parsed.get("reason", "")

        # Add verification evidence to the correct list based on verdict
        for page in good_pages:
            evidence = Evidence(
                content=f"Verification: {reason}",
                source_url=page.url,
                source_title=page.title,
                provider="verification",
                supports_claim=verdict in ("VERIFIED", "CONTESTED"),
                confidence=confidence,
            )
            if verdict == "REFUTED":
                claim.evidence_against.append(evidence)
            else:
                claim.evidence_for.append(evidence)

        # Update claim status
        if verdict == "VERIFIED" and source_independent:
            claim.status = ClaimStatus.VERIFIED
            claim.confidence = max(claim.confidence, confidence)
        elif verdict == "REFUTED":
            claim.status = ClaimStatus.REFUTED
            claim.confidence = min(claim.confidence, 1.0 - confidence)
        elif verdict == "CONTESTED":
            claim.status = ClaimStatus.CONTESTED
            claim.confidence = 0.5
        # INSUFFICIENT leaves it pending

        log.info(
            "Verification result: %s (confidence=%.2f, independent=%s) — %.60s",
            verdict, confidence, source_independent, claim.content,
        )

    except Exception as e:
        log.warning("Verification LLM call failed: %s", e)


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
