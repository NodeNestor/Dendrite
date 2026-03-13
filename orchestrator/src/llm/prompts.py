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
    return (
        f"Research question: {question}\n\n"
        f"Iteration: {iteration}\n\n"
        f"Claims found so far:\n{existing_claims or 'None yet.'}\n\n"
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
        "Good claims (specific, verifiable):\n"
        '- "ITER first plasma is scheduled for 2025"\n'
        '- "NIF achieved fusion ignition on December 5, 2022"\n'
        '- "Commonwealth Fusion Systems raised $1.8B in Series B funding"\n\n'
        "Bad claims (DO NOT extract):\n"
        '- "Fusion research is progressing" (vague)\n'
        '- "The article discusses fusion" (meta)\n'
        '- "Experts are optimistic" (no specifics)\n\n'
        "Rate page quality 0-10 (0=irrelevant, 10=primary source).\n\n"
        "Return JSON:\n"
        "{\n"
        '  "quality": 0-10,\n'
        '  "claims": [\n'
        '    {"claim": "specific factual assertion", "confidence": 0.0-1.0}\n'
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
        "- DUPLICATE: Already covered by existing claims. Skip.\n\n"
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
        "- Temporal consistency: Are the dates/timelines compatible?\n\n"
        "Return JSON:\n"
        "{\n"
        '  "verdict": "VERIFIED|REFUTED|CONTESTED|INSUFFICIENT",\n'
        '  "confidence": 0.0-1.0,\n'
        '  "reason": "explanation of verdict",\n'
        '  "source_independent": true/false,\n'
        '  "key_discrepancy": "if any"\n'
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
        "- Cite sources for each claim"
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
        "- Are the main aspects covered?\n"
        "- Are there obvious gaps?\n"
        "- Would more searching likely find novel information?\n\n"
        "Return JSON:\n"
        "{\n"
        '  "coverage_score": 0.0-1.0,\n'
        '  "gaps": ["..."],\n'
        '  "should_continue": true/false,\n'
        '  "reason": "..."\n'
        "}"
    )
