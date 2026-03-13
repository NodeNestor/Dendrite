"""Persist research trees to JSON files."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..models import ResearchTree

log = logging.getLogger(__name__)

_TREES_DIR = Path("/app/data/trees")


def save_tree(tree: ResearchTree) -> None:
    """Save a research tree to disk as JSON."""
    try:
        _TREES_DIR.mkdir(parents=True, exist_ok=True)
        path = _TREES_DIR / f"{tree.id}.json"
        path.write_text(tree.model_dump_json(indent=2))
        log.info("Saved tree %s to %s", tree.id, path)
    except Exception as e:
        log.warning("Failed to save tree %s: %s", tree.id, e)


def load_tree(tree_id: str) -> ResearchTree | None:
    """Load a research tree from disk."""
    path = _TREES_DIR / f"{tree_id}.json"
    if not path.exists():
        return None
    try:
        return ResearchTree.model_validate_json(path.read_text())
    except Exception as e:
        log.warning("Failed to load tree %s: %s", tree_id, e)
        return None


def list_trees() -> list[dict]:
    """List all saved trees (id, question, status)."""
    if not _TREES_DIR.exists():
        return []

    trees = []
    for path in sorted(_TREES_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            tree = ResearchTree.model_validate_json(path.read_text())
            trees.append({
                "id": tree.id,
                "question": tree.question,
                "status": tree.status.value,
                "total_claims": tree.total_claims,
                "verified_claims": tree.verified_claims,
                "created_at": tree.created_at.isoformat(),
                "finished_at": tree.finished_at.isoformat() if tree.finished_at else None,
            })
        except Exception:
            continue

    return trees
