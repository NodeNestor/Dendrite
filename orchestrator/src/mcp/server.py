"""MCP server — 7 tools for Dendrite research engine."""

from __future__ import annotations

import asyncio
import json
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from ..config import settings, get_runtime_config, update_runtime_config
from ..engine import run_investigation
from ..models import ResearchTree
from ..providers import register, search_all
from ..providers.web import WebProvider
from ..storage.hivemind import HiveMindClient
from ..storage.trees import save_tree, load_tree, list_trees
from ..validation import cross_validate_claims
from ..llm.client import LLMClient

log = logging.getLogger(__name__)

mcp = Server("dendrite")

_running: dict[str, asyncio.Task] = {}
_trees: dict[str, ResearchTree] = {}


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="investigate",
            description=(
                "Start a full recursive research investigation on a question. "
                "Builds a tree of branches, extracts and verifies claims from "
                "multiple independent sources, and synthesizes a report."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The research question"},
                    "max_depth": {
                        "type": "integer", "description": "Max tree depth (1-6, default 4)",
                        "default": 4, "minimum": 1, "maximum": 6,
                    },
                },
                "required": ["question"],
            },
        ),
        Tool(
            name="investigate_status",
            description="Check the progress of a running investigation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "tree_id": {"type": "string", "description": "Tree ID to check"},
                },
                "required": ["tree_id"],
            },
        ),
        Tool(
            name="investigate_result",
            description="Get the final results of a completed investigation — verified claims and synthesis.",
            inputSchema={
                "type": "object",
                "properties": {
                    "tree_id": {"type": "string", "description": "Tree ID to get results for"},
                },
                "required": ["tree_id"],
            },
        ),
        Tool(
            name="verify_claim",
            description="Cross-validate a single claim by searching for independent evidence.",
            inputSchema={
                "type": "object",
                "properties": {
                    "claim": {"type": "string", "description": "The factual claim to verify"},
                    "search_query": {"type": "string", "description": "Optional custom search query"},
                },
                "required": ["claim"],
            },
        ),
        Tool(
            name="search_knowledge",
            description="Search past research trees and HiveMindDB for existing knowledge.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for"},
                    "limit": {"type": "integer", "description": "Max results (default 20)", "default": 20},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="add_provider",
            description="Register a custom data provider at runtime.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Provider name"},
                    "type": {"type": "string", "description": "Provider type (web)", "enum": ["web"]},
                    "url": {"type": "string", "description": "Provider URL"},
                },
                "required": ["name", "type", "url"],
            },
        ),
        Tool(
            name="configure",
            description="Update Dendrite configuration — models, concurrency, depth limits.",
            inputSchema={
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "object",
                        "description": "Key-value pairs to update (e.g. {\"max_depth\": 5})",
                    },
                },
                "required": ["updates"],
            },
        ),
    ]


@mcp.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    # Ensure web provider is registered
    from ..providers import all_providers
    if not all_providers():
        register(WebProvider(settings.searxng_url))

    try:
        if name == "investigate":
            question = arguments["question"]
            max_depth = arguments.get("max_depth", 4)

            progress_queue: asyncio.Queue = asyncio.Queue()
            tree = await run_investigation(
                question=question,
                settings=settings,
                progress=progress_queue,
                tree=ResearchTree(
                    question=question,
                    max_depth=max_depth,
                    max_branch_iterations=settings.max_branch_iterations,
                    verification_threshold=settings.verification_threshold,
                ),
            )
            save_tree(tree)
            _trees[tree.id] = tree

            tree.update_stats()
            result = {
                "tree_id": tree.id,
                "question": tree.question,
                "status": tree.status.value,
                "total_claims": tree.total_claims,
                "verified_claims": tree.verified_claims,
                "refuted_claims": tree.refuted_claims,
                "contested_claims": tree.contested_claims,
                "branches": len(tree.branches),
                "synthesis": tree.synthesis,
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

        elif name == "investigate_status":
            tree_id = arguments["tree_id"]
            tree = _trees.get(tree_id) or load_tree(tree_id)
            if not tree:
                return [TextContent(type="text", text=f"Tree {tree_id} not found")]
            tree.update_stats()
            return [TextContent(type="text", text=json.dumps({
                "tree_id": tree.id, "status": tree.status.value,
                "total_claims": tree.total_claims, "verified_claims": tree.verified_claims,
                "branches": len(tree.branches),
            }, indent=2))]

        elif name == "investigate_result":
            tree_id = arguments["tree_id"]
            tree = _trees.get(tree_id) or load_tree(tree_id)
            if not tree:
                return [TextContent(type="text", text=f"Tree {tree_id} not found")]

            tree.update_stats()
            all_claims = tree.all_claims()
            claims_by_status = {}
            for c in all_claims:
                status = c.status.value
                if status not in claims_by_status:
                    claims_by_status[status] = []
                claims_by_status[status].append({
                    "claim": c.content,
                    "confidence": c.confidence,
                    "sources": c.source_urls[:5],
                })

            result = {
                "tree_id": tree.id,
                "question": tree.question,
                "claims_by_status": claims_by_status,
                "synthesis": tree.synthesis,
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

        elif name == "verify_claim":
            claim_text = arguments["claim"]
            query = arguments.get("search_query", claim_text)

            from ..models import Claim, ClaimStatus
            from ..providers import fetch_all

            claim = Claim(content=claim_text, verification_query=query)
            synthesis_client = LLMClient(settings.synthesis_llm)
            try:
                await cross_validate_claims(
                    [claim],
                    search_fn=lambda qs: search_all(qs),
                    fetch_fn=lambda urls: fetch_all(urls),
                    synthesis_client=synthesis_client,
                )
            finally:
                await synthesis_client.close()

            result = {
                "claim": claim.content,
                "status": claim.status.value,
                "confidence": claim.confidence,
                "evidence_count": len(claim.evidence_for) + len(claim.evidence_against),
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "search_knowledge":
            query = arguments["query"]
            limit = arguments.get("limit", 20)

            # Search HiveMindDB
            hivemind = HiveMindClient(settings.hivemind_url)
            try:
                hits = await hivemind.search(query, limit=limit)
                results = [
                    {"content": h.memory.content, "tags": h.memory.tags, "score": h.score}
                    for h in hits
                ]
            except Exception:
                results = []
            finally:
                await hivemind.close()

            # Also search past trees
            past_trees = list_trees()
            matching_trees = [
                t for t in past_trees
                if query.lower() in t["question"].lower()
            ][:5]

            return [TextContent(type="text", text=json.dumps({
                "hivemind_results": results,
                "matching_trees": matching_trees,
            }, indent=2, default=str))]

        elif name == "add_provider":
            ptype = arguments["type"]
            pname = arguments["name"]
            url = arguments["url"]

            if ptype == "web":
                register(WebProvider(url))
                return [TextContent(type="text", text=f"Registered web provider '{pname}' at {url}")]

            return [TextContent(type="text", text=f"Unknown provider type: {ptype}")]

        elif name == "configure":
            updates = arguments["updates"]
            new_config = update_runtime_config(updates)
            return [TextContent(type="text", text=json.dumps(new_config, indent=2))]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        log.error("MCP tool %s failed: %s", name, e, exc_info=True)
        return [TextContent(type="text", text=f"Error: {e}")]


async def run_mcp_server():
    async with stdio_server() as (read, write):
        await mcp.run(read, write, mcp.create_initialization_options())
