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
    """Search all registered providers in parallel with failover."""
    from .base import SearchHit

    async def _search_one(provider: "BaseProvider") -> list[SearchHit]:
        try:
            return await provider.search(queries, max_results=max_per_provider)
        except Exception as e:
            log.warning("Provider %s search failed: %s", provider.name, e)
            return []

    results = await asyncio.gather(*[_search_one(p) for p in _PROVIDERS.values()])

    # Merge and deduplicate across providers
    seen_urls: set[str] = set()
    merged: list[SearchHit] = []
    for batch in results:
        for hit in batch:
            if hit.url not in seen_urls:
                seen_urls.add(hit.url)
                merged.append(hit)

    return merged


async def fetch_all(urls: list[str], max_concurrent: int = 50) -> list["FetchedContent"]:
    """Fetch URLs using appropriate provider for each URL, with caching."""
    from .base import FetchedContent
    from ..cache import fetch_cache

    providers = list(_PROVIDERS.values())
    if not providers:
        return []

    sem = asyncio.Semaphore(max_concurrent)

    def _pick_provider(url: str) -> "BaseProvider":
        """Route URL to best provider."""
        if "arxiv.org" in url:
            p = _PROVIDERS.get("arxiv")
            if p:
                return p
        if "semanticscholar.org" in url or "doi.org" in url:
            p = _PROVIDERS.get("semantic_scholar")
            if p:
                return p
        # Default: first provider (web)
        return providers[0]

    async def _fetch(url: str) -> FetchedContent:
        # Check cache first
        cached = fetch_cache.get(url)
        if cached is not None:
            return FetchedContent(
                url=cached.url, title=cached.title, text=cached.text,
                provider=cached.provider, source_date=cached.source_date,
                error=cached.error,
            )

        async with sem:
            provider = _pick_provider(url)
            try:
                result = await provider.fetch(url)
                # Cache the result
                fetch_cache.put(
                    url=result.url, title=result.title, text=result.text,
                    provider=result.provider, source_date=result.source_date,
                    error=result.error,
                )
                return result
            except Exception as e:
                log.warning("Fetch failed for %s via %s: %s", url, provider.name, e)
                # Try fallback provider
                fallback = providers[0] if provider != providers[0] else None
                if fallback:
                    try:
                        result = await fallback.fetch(url)
                        fetch_cache.put(
                            url=result.url, title=result.title, text=result.text,
                            provider=result.provider, source_date=result.source_date,
                            error=result.error,
                        )
                        return result
                    except Exception:
                        pass
                return FetchedContent(url=url, title="", text="", error=str(e))

    return await asyncio.gather(*[_fetch(u) for u in urls])
