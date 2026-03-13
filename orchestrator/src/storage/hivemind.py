"""Async REST client for HiveMindDB — adapted from DeepResearch."""

from __future__ import annotations

import logging

import httpx

from .models import (
    EntityCreate, EntityResponse, MemoryCreate, MemoryResponse,
    SearchRequest, SearchResult,
)

log = logging.getLogger(__name__)


class HiveMindClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(30.0),
        )

    async def health(self) -> bool:
        try:
            resp = await self._client.get("/health")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def create_memory(self, memory: MemoryCreate) -> MemoryResponse | None:
        try:
            resp = await self._client.post("/api/v1/memories", json=memory.model_dump(mode="json"))
            resp.raise_for_status()
            return MemoryResponse.model_validate(resp.json())
        except httpx.HTTPError as exc:
            log.warning("create_memory failed: %s", exc)
            return None

    async def search(self, query: str, limit: int = 50, tags: list[str] | None = None) -> list[SearchResult]:
        try:
            req = SearchRequest(query=query, limit=limit, tags=tags or [])
            resp = await self._client.post("/api/v1/search", json=req.model_dump(mode="json"))
            resp.raise_for_status()
            return [SearchResult.model_validate(r) for r in resp.json()]
        except httpx.HTTPError as exc:
            log.warning("search failed: %s", exc)
            return []

    async def create_entity(self, entity: EntityCreate) -> EntityResponse | None:
        try:
            resp = await self._client.post("/api/v1/entities", json=entity.model_dump(mode="json"))
            resp.raise_for_status()
            return EntityResponse.model_validate(resp.json())
        except httpx.HTTPError as exc:
            log.warning("create_entity failed: %s", exc)
            return None

    async def find_entity(self, name: str) -> EntityResponse | None:
        try:
            resp = await self._client.post("/api/v1/entities/find", json={"name": name})
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return EntityResponse.model_validate(resp.json())
        except httpx.HTTPError as exc:
            log.warning("find_entity(%s) failed: %s", name, exc)
            return None

    async def close(self) -> None:
        await self._client.aclose()
