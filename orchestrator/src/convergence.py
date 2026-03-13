"""Multi-heuristic convergence detection for branches."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from .llm.client import LLMClient
from .llm.prompts import CONVERGENCE_SYSTEM, convergence_prompt
from .models import Branch, Claim

log = logging.getLogger(__name__)

MIN_ITERATIONS = 2
DIMINISHING_RETURNS_THRESHOLD = 0.10


@dataclass
class ConvergenceResult:
    converged: bool
    reason: str
    coverage_score: float = 0.0
    gaps: list[str] = field(default_factory=list)


async def check_convergence(
    branch: Branch,
    new_claims_this_iteration: int,
    max_iterations: int = 5,
    client: LLMClient | None = None,
) -> ConvergenceResult:
    """Decide whether a branch should continue or stop.

    Combines heuristics with optional LLM coverage assessment.
    """
    # Hard cap
    if branch.iteration >= max_iterations:
        return ConvergenceResult(
            converged=True,
            reason=f"Reached max iterations ({max_iterations})",
            coverage_score=0.8,
        )

    # Min iterations
    if branch.iteration < MIN_ITERATIONS:
        return ConvergenceResult(
            converged=False,
            reason=f"Below minimum iterations ({MIN_ITERATIONS})",
        )

    # No claims at all
    if not branch.claims:
        return ConvergenceResult(
            converged=False,
            reason="No claims discovered yet",
        )

    # Zero new claims
    if new_claims_this_iteration == 0:
        return ConvergenceResult(
            converged=True,
            reason="No new claims found — saturated",
            coverage_score=0.9,
        )

    # Diminishing returns
    total = len(branch.claims)
    if total > 0 and new_claims_this_iteration > 0:
        ratio = new_claims_this_iteration / total
        if ratio < DIMINISHING_RETURNS_THRESHOLD:
            return ConvergenceResult(
                converged=True,
                reason=f"Diminishing returns: {new_claims_this_iteration} new / {total} total ({ratio:.0%})",
                coverage_score=0.75,
            )

    # LLM coverage check (after first iteration, if client available)
    if client is not None and len(branch.claims) >= 3:
        try:
            claims_text = "\n".join(f"- {c.content}" for c in branch.claims[:100])
            result = await client.complete(
                messages=[
                    {"role": "system", "content": CONVERGENCE_SYSTEM},
                    {"role": "user", "content": convergence_prompt(branch.question, claims_text)},
                ],
                max_tokens=1024,
                thinking=False,
                temperature=0.1,
            )

            parsed = _parse_json(result.text)
            if isinstance(parsed, dict):
                coverage = float(parsed.get("coverage_score", 0.5))
                should_continue = parsed.get("should_continue", True)
                gaps = parsed.get("gaps", [])

                if not should_continue or coverage >= 0.85:
                    return ConvergenceResult(
                        converged=True,
                        reason=f"LLM assessment: coverage={coverage:.0%}",
                        coverage_score=coverage,
                        gaps=gaps if isinstance(gaps, list) else [],
                    )

                return ConvergenceResult(
                    converged=False,
                    reason=f"LLM assessment: coverage={coverage:.0%}, continuing",
                    coverage_score=coverage,
                    gaps=gaps if isinstance(gaps, list) else [],
                )
        except Exception as e:
            log.warning("LLM convergence check failed: %s", e)

    # Default: keep going
    return ConvergenceResult(
        converged=False,
        reason="Research still productive",
    )


def _parse_json(text: str) -> dict | list | None:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            start = text.find(start_char)
            end = text.rfind(end_char)
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    continue
        return None
