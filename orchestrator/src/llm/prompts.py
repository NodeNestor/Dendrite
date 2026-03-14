"""All prompt templates for the Dendrite truth-finding engine."""

from __future__ import annotations

# ------------------------------------------------------------------ #
# 1. Query Generation — generate search queries for a branch
# ------------------------------------------------------------------ #

QUERY_GENERATION_SYSTEM = (
    "You generate diverse search queries to investigate a question. "
    "Output raw JSON only — no markdown, no explanation."
)


def query_generation_prompt(
    question: str,
    existing_claims: str,
    iteration: int,
) -> str:
    # Strategy varies by iteration to maximize coverage
    if iteration == 0:
        strategy = (
            "This is the FIRST iteration. Generate broad, exploratory queries "
            "covering different aspects of the question."
        )
    elif iteration == 1:
        strategy = (
            "This is iteration 2. Generate SPECIFIC queries targeting gaps in "
            "existing claims. Also include one query seeking COUNTER-EVIDENCE "
            "or opposing viewpoints to challenge what we've found so far."
        )
    else:
        strategy = (
            f"This is iteration {iteration + 1}. Focus on:\n"
            "- Queries targeting SPECIFIC GAPS not covered by existing claims\n"
            "- At least one ADVERSARIAL query (find evidence that contradicts existing claims)\n"
            "- At least one query targeting ACADEMIC or PRIMARY sources "
            '(include terms like "study", "research", "data", "peer-reviewed")\n'
            "- At least one query with TEMPORAL specificity "
            '(include year ranges like "2023-2024" or "latest" or "recent")'
        )

    return (
        f"Research question: {question}\n\n"
        f"Iteration: {iteration}\n\n"
        f"Claims found so far:\n{existing_claims or 'None yet.'}\n\n"
        f"STRATEGY: {strategy}\n\n"
        "Generate 4 search queries to find NEW information not covered by existing claims. "
        "Vary specificity — mix broad and narrow queries. Avoid redundancy.\n\n"
        'Return a JSON array of strings: ["query1", "query2", "query3", "query4"]'
    )


# ------------------------------------------------------------------ #
# 2. Claim Extraction — extract factual claims from page content
# ------------------------------------------------------------------ #

EXTRACTION_SYSTEM = (
    "You extract specific factual claims from text. Each claim must be a concrete, "
    "verifiable assertion. Output raw JSON only."
)


def extraction_prompt(page_text: str, page_url: str, research_question: str) -> str:
    return (
        f"RESEARCH QUESTION: {research_question}\n"
        f"SOURCE URL: {page_url}\n\n"
        f"TEXT:\n{page_text}\n\n"
        "Extract all concrete, verifiable factual claims from this text that are "
        "relevant to the research question.\n\n"
        "IMPORTANT: For each claim, also extract the DATE or TIME PERIOD the claim "
        "refers to, if mentioned (e.g., 'as of 2024', 'in Q3 2023'). Include this "
        "in the claim text itself.\n\n"
        "Good claims (specific, verifiable, time-anchored):\n"
        '- "ITER first plasma is scheduled for 2025 (as announced in 2023)"\n'
        '- "NIF achieved fusion ignition on December 5, 2022, producing 3.15 MJ"\n'
        '- "Commonwealth Fusion Systems raised $1.8B in Series B funding in 2021"\n\n'
        "Bad claims (DO NOT extract):\n"
        '- "Fusion research is progressing" (vague)\n'
        '- "The article discusses fusion" (meta)\n'
        '- "Experts are optimistic" (no specifics)\n\n'
        "Rate page quality 0-10 (0=irrelevant, 10=primary source).\n\n"
        "Return JSON:\n"
        "{\n"
        '  "quality": 0-10,\n'
        '  "claims": [\n'
        '    {"claim": "specific factual assertion with dates", "confidence": 0.0-1.0}\n'
        "  ]\n"
        "}"
    )


# ------------------------------------------------------------------ #
# 3. Claim Triage — decide what to do with each new claim
# ------------------------------------------------------------------ #

TRIAGE_SYSTEM = (
    "You are a truth evaluator. For each claim, decide how to handle it. "
    "Output raw JSON only."
)


def triage_prompt(claims_text: str, existing_claims: str, research_question: str) -> str:
    return (
        f"Research question: {research_question}\n\n"
        f"Existing verified/accepted claims:\n{existing_claims or 'None yet.'}\n\n"
        f"New claims to triage:\n{claims_text}\n\n"
        "For each new claim, decide:\n"
        "- ACCEPT: Obviously true, well-known, or from highly trusted source. "
        "No verification needed.\n"
        "- VERIFY: Specific, important claim that should be independently confirmed. "
        'Include a search query to verify it (different angle than original source).\n'
        "- DEEPEN: This claim opens an important sub-question worth investigating. "
        "Include the sub-question.\n"
        "- COUNTER: This claim is surprising or controversial. Search for counter-evidence. "
        "Include a search query targeting opposing viewpoints.\n"
        "- DUPLICATE: Already covered by existing claims (even if worded differently). Skip.\n\n"
        "IMPORTANT guidelines:\n"
        "- Claims with specific numbers, dates, or statistics should usually be VERIFY\n"
        "- Claims that CONTRADICT existing claims should be COUNTER\n"
        "- Claims about rapidly evolving situations should be VERIFY with a recent-focused query\n\n"
        "Return JSON:\n"
        "{\n"
        '  "decisions": [\n'
        "    {\n"
        '      "index": 0,\n'
        '      "action": "ACCEPT|VERIFY|DEEPEN|COUNTER|DUPLICATE",\n'
        '      "reason": "brief explanation",\n'
        '      "query": "search query (for VERIFY/COUNTER)",\n'
        '      "sub_question": "question (for DEEPEN)"\n'
        "    }\n"
        "  ]\n"
        "}"
    )


# ------------------------------------------------------------------ #
# 4. Cross-Validation — verify claims from independent sources
# ------------------------------------------------------------------ #

VALIDATION_SYSTEM = (
    "You are a fact checker comparing claims against verification evidence. "
    "Output raw JSON only."
)


def validation_prompt(claim: str, original_source: str, verification_texts: str) -> str:
    return (
        f"ORIGINAL CLAIM: {claim}\n"
        f"ORIGINAL SOURCE: {original_source}\n\n"
        f"INDEPENDENT VERIFICATION EVIDENCE:\n{verification_texts}\n\n"
        "Does the independent evidence support, contradict, or leave "
        "the original claim uncertain?\n\n"
        "Check for:\n"
        "- Source independence: Is this truly a different source, or the same "
        "article/press release republished?\n"
        "- Factual consistency: Do the details match exactly?\n"
        "- Temporal consistency: Are the dates/timelines compatible? "
        "Has this information been SUPERSEDED by newer data?\n"
        "- Numerical consistency: Do specific numbers, percentages, amounts match?\n\n"
        "Return JSON:\n"
        "{\n"
        '  "verdict": "VERIFIED|REFUTED|CONTESTED|INSUFFICIENT",\n'
        '  "confidence": 0.0-1.0,\n'
        '  "reason": "explanation of verdict",\n'
        '  "source_independent": true/false,\n'
        '  "key_discrepancy": "if any",\n'
        '  "temporal_note": "if the claim may be outdated or superseded"\n'
        "}"
    )


# ------------------------------------------------------------------ #
# 5. Source Independence Check
# ------------------------------------------------------------------ #

SOURCE_INDEPENDENCE_SYSTEM = (
    "You determine whether two texts are from truly independent sources "
    "or just republished/aggregated versions of the same content. "
    "Output raw JSON only."
)


def source_independence_prompt(text_a: str, source_a: str, text_b: str, source_b: str) -> str:
    return (
        f"SOURCE A ({source_a}):\n{text_a[:2000]}\n\n"
        f"SOURCE B ({source_b}):\n{text_b[:2000]}\n\n"
        "Are these truly INDEPENDENT sources? Or is one a copy/aggregation of the other?\n\n"
        "Signs of dependence:\n"
        "- Identical or near-identical phrasing\n"
        "- Same quotes attributed the same way\n"
        "- One is a press release, the other a reprint\n\n"
        "Signs of independence:\n"
        "- Different angles or additional reporting\n"
        "- Different quotes or sources cited\n"
        "- Original analysis or commentary\n\n"
        "Return JSON:\n"
        '{"independent": true/false, "confidence": 0.0-1.0, "reason": "..."}'
    )


# ------------------------------------------------------------------ #
# 6. Synthesis — final report from verified claims
# ------------------------------------------------------------------ #

SYNTHESIS_SYSTEM = (
    "You synthesize research findings into a clear, well-structured report. "
    "Only include verified claims. Flag uncertainties and contradictions. "
    "Output raw JSON only."
)


def synthesis_prompt(question: str, claims_text: str, tree_structure: str) -> str:
    return (
        f"Research question: {question}\n\n"
        f"=== RESEARCH TREE STRUCTURE ===\n{tree_structure}\n\n"
        f"=== ALL CLAIMS WITH VERIFICATION STATUS ===\n{claims_text}\n\n"
        "Produce a synthesis report as JSON:\n"
        "{\n"
        '  "title": "...",\n'
        '  "summary": "2-3 sentence executive summary",\n'
        '  "sections": [\n'
        '    {"heading": "...", "body": "...", "confidence": 0.0-1.0, "citations": ["url1"]}\n'
        "  ],\n"
        '  "verified_conclusions": ["..."],\n'
        '  "contested_points": ["..."],\n'
        '  "open_questions": ["..."],\n'
        '  "confidence_overall": 0.0-1.0\n'
        "}\n\n"
        "Rules:\n"
        "- Only state verified claims as conclusions\n"
        "- Explicitly note contested or refuted claims\n"
        "- List open questions that couldn't be resolved\n"
        "- Cite sources for each claim\n"
        "- Weave claims into a COHERENT NARRATIVE, not just a list\n"
        "- Note when information may be outdated and flag temporal uncertainties"
    )


# ------------------------------------------------------------------ #
# 7. Convergence Assessment
# ------------------------------------------------------------------ #

CONVERGENCE_SYSTEM = (
    "You assess whether a research branch has sufficient coverage. "
    "Output raw JSON only."
)


def convergence_prompt(question: str, claims_text: str) -> str:
    return (
        f"Research question: {question}\n\n"
        f"Claims found:\n{claims_text}\n\n"
        "Assess coverage:\n"
        "- List all MAIN ASPECTS that should be covered for this question\n"
        "- For each aspect, note whether it's covered by existing claims\n"
        "- Are there obvious gaps?\n"
        "- Would more searching likely find novel information?\n\n"
        "Return JSON:\n"
        "{\n"
        '  "coverage_score": 0.0-1.0,\n'
        '  "aspects": [{"topic": "...", "covered": true/false}],\n'
        '  "gaps": ["..."],\n'
        '  "should_continue": true/false,\n'
        '  "reason": "..."\n'
        "}"
    )


# ------------------------------------------------------------------ #
# 8. Contradiction Resolution — resolve conflicting claims
# ------------------------------------------------------------------ #

RESOLUTION_SYSTEM = (
    "You are a contradiction resolution expert. Analyze conflicting claims "
    "and determine which is more likely correct based on evidence quality, "
    "source authority, and recency. Output raw JSON only."
)


def resolution_prompt(
    claim_a: str, evidence_a: str, sources_a: str,
    claim_b: str, evidence_b: str, sources_b: str,
    research_question: str,
) -> str:
    return (
        f"Research question: {research_question}\n\n"
        f"=== CLAIM A ===\n{claim_a}\n"
        f"Evidence: {evidence_a}\n"
        f"Sources: {sources_a}\n\n"
        f"=== CLAIM B (contradicting) ===\n{claim_b}\n"
        f"Evidence: {evidence_b}\n"
        f"Sources: {sources_b}\n\n"
        "These claims CONTRADICT each other. Analyze:\n"
        "1. Which sources are more authoritative? (peer-reviewed > news > blog)\n"
        "2. Which is more recent? (newer data may supersede older)\n"
        "3. Which has more independent supporting evidence?\n"
        "4. Could both be partially correct in different contexts?\n"
        "5. Is the contradiction due to different time periods, definitions, or scopes?\n\n"
        "Return JSON:\n"
        "{\n"
        '  "verdict": "A_STRONGER|B_STRONGER|BOTH_PARTIAL|UNRESOLVABLE",\n'
        '  "confidence": 0.0-1.0,\n'
        '  "reasoning": "detailed explanation",\n'
        '  "resolution": "what we can confidently conclude",\n'
        '  "caveats": ["any important nuances"],\n'
        '  "recommended_search": "query to find more evidence if needed"\n'
        "}"
    )


# ------------------------------------------------------------------ #
# 9. Self-Critique / Refinement — identify gaps after synthesis
# ------------------------------------------------------------------ #

REFINEMENT_SYSTEM = (
    "You critically evaluate a research synthesis to identify weaknesses, "
    "gaps, and areas needing more evidence. Output raw JSON only."
)


def refinement_prompt(question: str, synthesis: str, claim_summary: str) -> str:
    return (
        f"Research question: {question}\n\n"
        f"=== CURRENT SYNTHESIS ===\n{synthesis}\n\n"
        f"=== CLAIM SUMMARY ===\n{claim_summary}\n\n"
        "Critically evaluate this synthesis:\n"
        "1. What important aspects of the question are NOT adequately answered?\n"
        "2. Which conclusions rest on WEAK evidence (few sources, low-quality sources)?\n"
        "3. Are there CONTRADICTIONS that weren't resolved?\n"
        "4. What FOLLOW-UP QUESTIONS would strengthen the analysis?\n\n"
        "Return JSON:\n"
        "{\n"
        '  "quality_score": 0.0-1.0,\n'
        '  "critical_gaps": ["specific gap descriptions"],\n'
        '  "weak_conclusions": ["conclusions needing more evidence"],\n'
        '  "follow_up_queries": [\n'
        '    {"question": "follow-up question", "search_query": "query to search"}\n'
        "  ],\n"
        '  "needs_more_research": true/false\n'
        "}"
    )


# ------------------------------------------------------------------ #
# 10. Bayesian Confidence Update prompt
# ------------------------------------------------------------------ #

BAYESIAN_SYSTEM = (
    "You estimate how a new piece of evidence should update the probability "
    "of a claim being true. Think like a Bayesian reasoner. Output raw JSON only."
)


def bayesian_prompt(
    claim: str, current_confidence: float,
    new_evidence: str, source_quality: float,
    source_independent: bool,
) -> str:
    return (
        f"CLAIM: {claim}\n"
        f"Current confidence: {current_confidence:.2f}\n\n"
        f"NEW EVIDENCE: {new_evidence}\n"
        f"Source quality: {source_quality:.2f}\n"
        f"Source independent from prior evidence: {source_independent}\n\n"
        "How should this evidence update our confidence in the claim?\n\n"
        "Consider:\n"
        "- Does the evidence SUPPORT or CONTRADICT the claim?\n"
        "- How reliable is the source? (quality score above)\n"
        "- Is it truly independent? (independent sources provide stronger updates)\n"
        "- How surprising is this evidence? (unexpected evidence = bigger update)\n\n"
        "Return JSON:\n"
        "{\n"
        '  "direction": "support|contradict|neutral",\n'
        '  "strength": 0.0-1.0,\n'
        '  "new_confidence": 0.0-1.0,\n'
        '  "reasoning": "brief explanation"\n'
        "}"
    )
