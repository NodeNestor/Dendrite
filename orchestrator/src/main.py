"""FastAPI app — REST API, WebSocket progress, static frontend, MCP entry."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from .config import settings, get_runtime_config, update_runtime_config
from .engine import run_investigation
from .models import (
    InvestigateRequest, ProgressEvent, ResearchTree, TreeStatus, TreeSummary,
)
from .providers import register
from .providers.web import WebProvider
from .storage.trees import save_tree, load_tree, list_trees

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


# -- Session manager -------------------------------------------------------

class InvestigationManager:
    def __init__(self) -> None:
        self.trees: dict[str, ResearchTree] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.progress_queues: dict[str, asyncio.Queue[ProgressEvent]] = {}
        self.ws_clients: dict[str, list[WebSocket]] = {}

    def get_tree(self, tree_id: str) -> ResearchTree | None:
        tree = self.trees.get(tree_id)
        if not tree:
            tree = load_tree(tree_id)
            if tree:
                self.trees[tree_id] = tree
        return tree

    def is_running(self, tree_id: str) -> bool:
        task = self.tasks.get(tree_id)
        return task is not None and not task.done()

    def stop(self, tree_id: str) -> bool:
        """Cancel a running investigation."""
        task = self.tasks.get(tree_id)
        if task and not task.done():
            task.cancel()
            tree = self.trees.get(tree_id)
            if tree:
                tree.status = TreeStatus.FAILED
                tree.synthesis = "Investigation stopped by user."
                save_tree(tree)
            return True
        return False

    async def start(
        self, question: str, max_depth: int = 4,
        max_branch_iterations: int = 5, blocking: bool = False,
    ) -> ResearchTree:
        progress_queue: asyncio.Queue[ProgressEvent] = asyncio.Queue()

        tree = ResearchTree(
            question=question,
            max_depth=max_depth,
            max_branch_iterations=max_branch_iterations,
            verification_threshold=settings.verification_threshold,
        )
        self.trees[tree.id] = tree
        self.progress_queues[tree.id] = progress_queue

        if blocking:
            tree = await run_investigation(
                question=question, settings=settings,
                progress=progress_queue, tree=tree,
            )
            await self._drain_progress(tree.id)
            save_tree(tree)
            return tree

        async def _run():
            try:
                await run_investigation(
                    question=question, settings=settings,
                    progress=progress_queue, tree=tree,
                )
            except Exception as e:
                log.error("Background investigation failed: %s", e)
            finally:
                await self._drain_progress(tree.id)
                save_tree(tree)

        task = asyncio.create_task(_run())
        self.tasks[tree.id] = task
        asyncio.create_task(self._forward_progress(tree.id))
        return tree

    async def _forward_progress(self, tree_id: str) -> None:
        queue = self.progress_queues.get(tree_id)
        if not queue:
            return
        while True:
            try:
                update = await asyncio.wait_for(queue.get(), timeout=1.0)
                for ws in self.ws_clients.get(tree_id, []):
                    try:
                        await ws.send_json(update.model_dump(mode="json", exclude_none=True))
                    except Exception:
                        pass
                if update.event_type in ("tree_complete", "tree_failed"):
                    break
            except asyncio.TimeoutError:
                task = self.tasks.get(tree_id)
                if task and task.done():
                    break
            except Exception:
                break

    async def _drain_progress(self, tree_id: str) -> None:
        queue = self.progress_queues.get(tree_id)
        if not queue:
            return
        while True:
            try:
                update = queue.get_nowait()
                for ws in self.ws_clients.get(tree_id, []):
                    try:
                        await ws.send_json(update.model_dump(mode="json", exclude_none=True))
                    except Exception:
                        pass
            except asyncio.QueueEmpty:
                break

    def subscribe_ws(self, tree_id: str, ws: WebSocket) -> None:
        self.ws_clients.setdefault(tree_id, []).append(ws)

    def unsubscribe_ws(self, ws: WebSocket) -> None:
        for clients in self.ws_clients.values():
            if ws in clients:
                clients.remove(ws)


manager = InvestigationManager()


# -- Lifespan --------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Dendrite starting")
    log.info("  SearXNG: %s", settings.searxng_url)
    log.info("  HiveMindDB: %s", settings.hivemind_url)
    log.info("  Bulk model: %s @ %s", settings.bulk_model, settings.bulk_api_url)
    log.info("  Synthesis model: %s @ %s", settings.synthesis_model, settings.synthesis_api_url)

    # Register default providers
    register(WebProvider(settings.searxng_url))

    # Register academic providers
    if settings.enable_arxiv:
        from .providers.academic import ArxivProvider
        register(ArxivProvider())
        log.info("  arXiv provider: enabled")

    if settings.enable_semantic_scholar:
        from .providers.academic import SemanticScholarProvider
        register(SemanticScholarProvider(api_key=settings.semantic_scholar_api_key))
        log.info("  Semantic Scholar provider: enabled")

    yield
    log.info("Dendrite shutting down")


# -- App -------------------------------------------------------------------

app = FastAPI(
    title="Dendrite",
    description="Recursive branching truth engine",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# -- API routes ------------------------------------------------------------

@app.get("/api/health")
async def health():
    import httpx
    services = {}
    async with httpx.AsyncClient(timeout=5) as client:
        for name, url in [
            ("searxng", settings.searxng_url),
            ("hiveminddb", settings.hivemind_url + "/health"),
            ("vllm", settings.bulk_api_url.replace("/v1", "") + "/health"),
        ]:
            try:
                resp = await client.get(url)
                services[name] = "ok" if resp.status_code == 200 else f"error ({resp.status_code})"
            except Exception:
                services[name] = "unreachable"

    # Cache stats
    from .cache import fetch_cache
    services["fetch_cache"] = fetch_cache.stats

    return {"status": "ok", "services": services}


@app.get("/api/config")
async def get_config():
    return get_runtime_config()


@app.put("/api/config")
async def put_config(request: Request):
    body = await request.json()
    return update_runtime_config(body)


@app.post("/api/research")
async def start_research(req: InvestigateRequest):
    """Start investigation. Blocking — returns when complete."""
    tree = await manager.start(
        question=req.question,
        max_depth=req.max_depth,
        max_branch_iterations=req.max_branch_iterations,
        blocking=True,
    )
    return _tree_response(tree)


@app.post("/api/research/async")
async def start_research_async(req: InvestigateRequest):
    """Start investigation in background."""
    tree = await manager.start(
        question=req.question,
        max_depth=req.max_depth,
        max_branch_iterations=req.max_branch_iterations,
        blocking=False,
    )
    return {"tree_id": tree.id, "status": "started", "question": req.question}


@app.post("/api/research/{tree_id}/stop")
async def stop_research(tree_id: str):
    """Stop a running investigation."""
    if manager.stop(tree_id):
        return {"status": "stopped", "tree_id": tree_id}
    return {"status": "not_running", "tree_id": tree_id}


@app.get("/api/research/{tree_id}")
async def get_research(tree_id: str):
    tree = manager.get_tree(tree_id)
    if not tree:
        return {"error": "Tree not found"}
    resp = _tree_response(tree)
    resp["status"] = "running" if manager.is_running(tree_id) else tree.status.value
    return resp


@app.get("/api/trees")
async def get_trees():
    """List all research trees."""
    saved = list_trees()
    # Merge with in-memory running trees
    saved_ids = {t["id"] for t in saved}
    for tree_id, tree in manager.trees.items():
        if tree_id not in saved_ids:
            saved.append({
                "id": tree.id,
                "question": tree.question,
                "status": "running" if manager.is_running(tree_id) else tree.status.value,
                "total_claims": tree.total_claims,
                "verified_claims": tree.verified_claims,
                "created_at": tree.created_at.isoformat(),
                "finished_at": tree.finished_at.isoformat() if tree.finished_at else None,
            })
    return saved


@app.get("/api/tree/{tree_id}")
async def get_tree_full(tree_id: str):
    """Get full tree with all branches and claims."""
    tree = manager.get_tree(tree_id)
    if not tree:
        return {"error": "Tree not found"}
    return tree.model_dump(mode="json")


# -- Export endpoints -------------------------------------------------------

@app.get("/api/tree/{tree_id}/export/markdown")
async def export_markdown(tree_id: str):
    """Export tree as a Markdown report with citations."""
    tree = manager.get_tree(tree_id)
    if not tree:
        return {"error": "Tree not found"}

    md = _tree_to_markdown(tree)
    return Response(
        content=md,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=dendrite-{tree_id}.md"},
    )


@app.get("/api/tree/{tree_id}/export/json")
async def export_json(tree_id: str):
    """Export tree as structured JSON."""
    tree = manager.get_tree(tree_id)
    if not tree:
        return {"error": "Tree not found"}

    export = _tree_to_export_json(tree)
    return Response(
        content=json.dumps(export, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=dendrite-{tree_id}.json"},
    )


def _tree_to_markdown(tree: ResearchTree) -> str:
    """Convert tree to readable Markdown report with citations."""
    lines = [
        f"# {tree.question}",
        "",
        f"*Generated by Dendrite — {tree.created_at.strftime('%Y-%m-%d %H:%M UTC')}*",
        "",
    ]

    # Try to parse synthesis as JSON for structured output
    synthesis_data = None
    try:
        synthesis_data = json.loads(tree.synthesis)
    except (json.JSONDecodeError, TypeError):
        pass

    if synthesis_data and isinstance(synthesis_data, dict):
        if synthesis_data.get("summary"):
            lines.extend(["## Summary", "", synthesis_data["summary"], ""])

        for section in synthesis_data.get("sections", []):
            heading = section.get("heading", "")
            body = section.get("body", "")
            confidence = section.get("confidence", 0)
            citations = section.get("citations", [])

            lines.append(f"## {heading}")
            lines.append("")
            lines.append(body)
            if confidence:
                lines.append(f"\n*Confidence: {confidence:.0%}*")
            if citations:
                lines.append("\nSources:")
                for url in citations:
                    lines.append(f"- {url}")
            lines.append("")

        if synthesis_data.get("verified_conclusions"):
            lines.extend(["## Verified Conclusions", ""])
            for c in synthesis_data["verified_conclusions"]:
                lines.append(f"- {c}")
            lines.append("")

        if synthesis_data.get("contested_points"):
            lines.extend(["## Contested Points", ""])
            for c in synthesis_data["contested_points"]:
                lines.append(f"- {c}")
            lines.append("")

        if synthesis_data.get("open_questions"):
            lines.extend(["## Open Questions", ""])
            for q in synthesis_data["open_questions"]:
                lines.append(f"- {q}")
            lines.append("")

    elif tree.synthesis:
        lines.extend(["## Synthesis", "", tree.synthesis, ""])

    # Claims appendix
    all_claims = tree.all_claims()
    if all_claims:
        lines.extend(["---", "", "## All Claims", ""])
        for claim in all_claims:
            status_icon = {
                "verified": "[+]", "accepted": "[~]", "refuted": "[-]",
                "contested": "[?]", "pending": "[ ]",
            }.get(claim.status.value, "[ ]")
            sources = " | ".join(claim.source_urls[:3])
            lines.append(
                f"- {status_icon} **{claim.status.value.upper()}** "
                f"({claim.confidence:.0%}) {claim.content}"
            )
            if sources:
                lines.append(f"  Sources: {sources}")

    # Stats
    tree.update_stats()
    lines.extend([
        "", "---", "",
        "## Statistics", "",
        f"- Total claims: {tree.total_claims}",
        f"- Verified: {tree.verified_claims}",
        f"- Refuted: {tree.refuted_claims}",
        f"- Contested: {tree.contested_claims}",
        f"- Branches: {len(tree.branches)}",
        f"- Pages fetched: {tree.pages_fetched}",
        f"- LLM tokens: {tree.llm_prompt_tokens + tree.llm_completion_tokens:,}",
    ])

    return "\n".join(lines)


def _tree_to_export_json(tree: ResearchTree) -> dict:
    """Convert tree to a clean export format with citation chains."""
    tree.update_stats()
    all_claims = tree.all_claims()

    claims_by_status = {}
    for claim in all_claims:
        status = claim.status.value
        if status not in claims_by_status:
            claims_by_status[status] = []
        claims_by_status[status].append({
            "claim": claim.content,
            "confidence": claim.confidence,
            "sources": claim.source_urls,
            "evidence_for": [
                {"content": e.content, "source": e.source_url, "quality": e.source_quality}
                for e in claim.evidence_for
            ],
            "evidence_against": [
                {"content": e.content, "source": e.source_url, "quality": e.source_quality}
                for e in claim.evidence_against
            ],
            "status_history": claim.status_history,
        })

    return {
        "question": tree.question,
        "tree_id": tree.id,
        "status": tree.status.value,
        "created_at": tree.created_at.isoformat(),
        "finished_at": tree.finished_at.isoformat() if tree.finished_at else None,
        "stats": {
            "total_claims": tree.total_claims,
            "verified": tree.verified_claims,
            "refuted": tree.refuted_claims,
            "contested": tree.contested_claims,
            "branches": len(tree.branches),
            "pages_fetched": tree.pages_fetched,
            "llm_tokens": tree.llm_prompt_tokens + tree.llm_completion_tokens,
        },
        "claims": claims_by_status,
        "synthesis": tree.synthesis,
    }


def _tree_response(tree: ResearchTree) -> dict:
    tree.update_stats()
    return {
        "tree_id": tree.id,
        "question": tree.question,
        "status": tree.status.value,
        "total_claims": tree.total_claims,
        "verified_claims": tree.verified_claims,
        "refuted_claims": tree.refuted_claims,
        "contested_claims": tree.contested_claims,
        "total_evidence": tree.total_evidence,
        "total_sources": tree.total_sources,
        "branches": len(tree.branches),
        "pages_fetched": tree.pages_fetched,
        "llm_tokens": tree.llm_prompt_tokens + tree.llm_completion_tokens,
        "synthesis": tree.synthesis,
    }


# -- WebSocket -------------------------------------------------------------

@app.websocket("/ws")
async def websocket_progress(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                tree_id = msg.get("tree_id")
                if tree_id:
                    manager.subscribe_ws(tree_id, ws)
                    await ws.send_json({"subscribed": tree_id})
            except json.JSONDecodeError:
                await ws.send_json({"error": "Invalid JSON"})
    except WebSocketDisconnect:
        manager.unsubscribe_ws(ws)


# -- Static frontend (SPA) ------------------------------------------------

if STATIC_DIR.exists():
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        file_path = STATIC_DIR / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")


# -- MCP mode entry --------------------------------------------------------

def run_mcp():
    from .mcp.server import run_mcp_server
    asyncio.run(run_mcp_server())


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "mcp":
        run_mcp()
    else:
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=8080)
