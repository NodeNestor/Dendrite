"""Provider registry — discover and query all registered data providers."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BaseProvider, FetchedContent, SearchHit

log = logging.getLogger(__name__)

_PROVIDERS: dict[str, "BaseProvider"] = {}


def register(provider: "BaseProvider") -> None:
    _PROVIDERS[provider.name] = provider
    log.info("Registered provider: %s", provider.name)


def get(name: str) -> "BaseProvider | None":
    return _PROVIDERS.get(name)


def all_providers() -> list["BaseProvider"]:
    return list(_PROVIDERS.values())


async def search_all(queries: list[str], max_per_provider: int = 10) -> list["SearchHit"]:
    """Search all registered providers in parallel."""
    from .base import SearchHit

    async def _search_one(provider: "BaseProvider") -> list[SearchHit]:
        try:
            return await provider.search(queries, max_results=max_per_provider)
        except Exception as e:
            log.warning("Provider %s search failed: %s", provider.name, e)
            return []

    results = await asyncio.gather(*[_search_one(p) for p in _PROVIDERS.values()])
    return [hit for batch in results for hit in batch]


async def fetch_all(urls: list[str], max_concurrent: int = 50) -> list["FetchedContent"]:
    """Fetch URLs using the first provider that can handle each URL."""
    from .base import FetchedContent

    providers = list(_PROVIDERS.values())
    if not providers:
        return []

    # Use the first provider for all URLs (web provider)
    provider = providers[0]
    sem = asyncio.Semaphore(max_concurrent)

    async def _fetch(url: str) -> FetchedContent:
        async with sem:
            try:
                return await provider.fetch(url)
            except Exception as e:
                log.warning("Fetch failed for %s: %s", url, e)
                return FetchedContent(url=url, title="", text="", error=str(e))

    return await asyncio.gather(*[_fetch(u) for u in urls])
