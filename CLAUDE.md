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
  main.py          — FastAPI + WebSocket + MCP entry
  config.py        — Pydantic settings + runtime config
  models.py        — ResearchTree, Branch, Claim, Evidence
  engine.py        — THE CORE — recursive branching loop
  validation.py    — Three-pass cross-validation
  convergence.py   — Multi-heuristic convergence detection
  providers/
    __init__.py    — Registry + search_all/fetch_all
    base.py        — Provider ABC
    web.py         — SearXNG + trafilatura
    academic.py    — arXiv + Semantic Scholar (future)
  llm/
    __init__.py
    client.py      — Provider-agnostic LLM (from DeepResearch)
    batch.py       — Batched concurrent calls
    prompts.py     — All prompts for truth-finding
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
    1. Generate queries from branch question + existing claims
    2. Search all providers in parallel
    3. Fetch content, extract claims (bulk model, batched)
    4. For each claim, LLM decides: ACCEPT / VERIFY / DEEPEN / COUNTER
    5. Check convergence
  Process child branches recursively (depth-limited)
```

### Cross-Validation (3-pass)
1. Rate all claims (VERIFIED/PLAUSIBLE/REFUTED/VERIFY)
2. VERIFY claims trigger independent searches from different sources
3. Source independence check — same article republished != independent confirmation

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

```bash
cd orchestrator/frontend
npm install
npm run dev    # Dev server at :5173 with API proxy to :8082
npm run build  # Production build
```
