# Dendrite — Recursive Branching Truth Engine

## What This Is

A modular, recursive truth-finding engine that builds research TREES, not flat lists. Each claim gets independently verified. Each sub-topic gets its own branch. Contradictions get investigated from both sides. The tree grows until convergence.

## Architecture

Docker containers on `dendrite-net` bridge network:
- **searxng** (:8888->8080) — metasearch engine proxy
- **hiveminddb** (:8100) — knowledge graph + vector DB
- **orchestrator** (:8082->8080) — Python FastAPI backend + React frontend + MCP server
- **vllm** (:8000) — CUDA local LLM inference

## Two-Model Architecture

- **Bulk model**: Small, fast. Used for claim extraction, query generation, claim triage. Default: Qwen3.5-0.8B on local vLLM.
- **Synthesis model**: Larger, smarter. Used for cross-validation, final synthesis. Can be any OpenAI-compatible endpoint.

## Project Layout

```
orchestrator/src/
  main.py          — FastAPI + WebSocket + MCP entry + export endpoints
  config.py        — Pydantic settings + runtime config
  models.py        — ResearchTree, Branch, Claim, Evidence
  engine.py        — THE CORE — recursive branching loop + refinement + feedback
  validation.py    — Three-pass cross-validation with Bayesian confidence
  convergence.py   — Multi-heuristic convergence (per-branch-type thresholds)
  cache.py         — LRU fetch cache for page content
  source_quality.py — Source authority/type/recency scoring
  semantic_dedup.py — TF-IDF cosine similarity deduplication
  providers/
    __init__.py    — Registry + search_all/fetch_all + cache + failover
    base.py        — Provider ABC
    web.py         — SearXNG + trafilatura
    academic.py    — arXiv + Semantic Scholar providers
  llm/
    __init__.py
    client.py      — Provider-agnostic LLM (from DeepResearch)
    batch.py       — Batched concurrent calls
    prompts.py     — All prompts (10 types: query gen, extraction, triage,
                     validation, independence, synthesis, convergence,
                     resolution, refinement, bayesian)
  storage/
    __init__.py
    hivemind.py    — HiveMindDB client
    models.py      — HiveMindDB Pydantic models
    trees.py       — Persist trees to JSON
  mcp/
    __init__.py
    server.py      — 7 MCP tools
```

## Key Concepts

### Research Tree
A full investigation. Contains branches, which contain claims, which have evidence.

### Branch Types
- **investigation**: Main line of inquiry
- **verification**: Independent search to verify a specific claim
- **deepening**: Drill deeper into a sub-question
- **counter**: Search for counter-evidence to a contested claim
- **resolution**: Contradiction resolution between conflicting claims

### Claim Statuses
- **pending**: Not yet evaluated
- **verified**: Confirmed by 2+ independent sources
- **refuted**: Contradicted by stronger evidence
- **contested**: Conflicting evidence found
- **accepted**: Trivially true or from trusted source

### Branching Algorithm
```
run_branch(branch):
  for iteration until converged:
    1. Generate queries (iteration-aware strategy: broad -> targeted -> adversarial)
    2. Search all providers in parallel (web + arXiv + Semantic Scholar)
    3. Fetch content with caching, extract claims (bulk model, batched)
    4. Source quality scoring (domain authority, recency, source type)
    5. Semantic deduplication (TF-IDF cosine + string-based)
    6. Confidence adjustment based on source quality
    7. For each claim, LLM decides: ACCEPT / VERIFY / DEEPEN / COUNTER
    8. Check convergence (branch-type-aware thresholds)
  Process child branches recursively (depth-limited)
```

### Post-Investigation Pipeline
1. **Cross-validation**: Independent search + Bayesian confidence updates
2. **Contradiction resolution**: LLM-driven analysis of CONTESTED claims (A_STRONGER / B_STRONGER / BOTH_PARTIAL)
3. **Synthesis**: Coherent narrative report with citations
4. **Multi-turn refinement**: Self-critique, identify gaps, targeted follow-up research
5. **HiveMindDB feedback**: Store verified claims for future investigations

### Cross-Validation (3-pass)
1. Rate all claims (VERIFIED/PLAUSIBLE/REFUTED/VERIFY)
2. VERIFY claims trigger independent searches from different sources
3. Source independence check — same article republished != independent confirmation

### Source Quality Scoring
Each source gets scored on:
- **Authority** (0-1): Domain-based tier (nature.com=0.95, blog=0.35)
- **Recency** (0-1): Time-decayed (last month=1.0, 5+ years=0.1)
- **Source Type**: peer_reviewed, preprint, academic, news, blog, forum, etc.
- **Overall** (0-1): Weighted composite propagated into claim confidence

### Semantic Deduplication
TF-IDF cosine similarity (default threshold: 0.75) catches semantically equivalent claims that differ in wording. No external embedding API needed.

### Fetch Caching
LRU in-memory cache (500 pages, 1hr TTL) prevents redundant downloads across branches.

## Commands

```bash
# Start everything
docker compose up -d

# Rebuild after code changes
docker compose build orchestrator && docker compose up -d orchestrator

# Open web UI
open http://localhost:8082

# Test health
curl http://localhost:8082/api/health

# Start research via API
curl -X POST http://localhost:8082/api/research \
  -H "Content-Type: application/json" \
  -d '{"question":"Is fusion power viable by 2035?"}'

# Stop a running investigation
curl -X POST http://localhost:8082/api/research/{tree_id}/stop

# Export as Markdown
curl http://localhost:8082/api/tree/{tree_id}/export/markdown

# Export as JSON
curl http://localhost:8082/api/tree/{tree_id}/export/json

# MCP mode (stdio)
python -m orchestrator.src.main mcp
```

## MCP Tools

| Tool | Purpose |
|------|---------|
| `investigate` | Start full research tree on a question |
| `investigate_status` | Check running investigation progress |
| `investigate_result` | Get final verified claims + synthesis |
| `verify_claim` | Cross-validate a single claim |
| `search_knowledge` | Search past trees + HiveMindDB |
| `add_provider` | Register custom provider at runtime |
| `configure` | Update models, concurrency, depth limits |

## Frontend

React + Vite + Tailwind + @xyflow/react for interactive tree visualization.

Features:
- Interactive tree graph with branch-type coloring (including resolution branches)
- Claim search & filtering by status
- Stop button for running investigations
- Synthesis report viewer (structured JSON rendering)
- Export to Markdown / JSON
- Source quality badges on claims
- Status history audit trail
- Settings for all new features (academic providers, quality scoring, dedup, etc.)

```bash
cd orchestrator/frontend
npm install
npm run dev    # Dev server at :5173 with API proxy to :8082
npm run build  # Production build
```
