"""Web provider — SearXNG search + trafilatura text extraction."""

from __future__ import annotations

import asyncio
import logging

import httpx
import trafilatura

from .base import BaseProvider, FetchedContent, SearchHit

log = logging.getLogger(__name__)


class WebProvider(BaseProvider):
    """SearXNG metasearch + trafilatura content extraction."""

    def __init__(self, searxng_url: str = "http://searxng:8080") -> None:
        self.searxng_url = searxng_url

    @property
    def name(self) -> str:
        return "web"

    async def search(self, queries: list[str], max_results: int = 10) -> list[SearchHit]:
        results: list[SearchHit] = []
        seen_urls: set[str] = set()

        async def _search_one(client: httpx.AsyncClient, query: str) -> list[SearchHit]:
            try:
                resp = await client.get(
                    f"{self.searxng_url}/search",
                    params={"q": query, "format": "json"},
                )
                resp.raise_for_status()
                data = resp.json()
                hits = []
                for r in data.get("results", []):
                    url = r.get("url", "")
                    if url:
                        hits.append(SearchHit(
                            url=url,
                            title=r.get("title", ""),
                            snippet=r.get("content", ""),
                            provider="web",
                            source_date=r.get("publishedDate"),
                        ))
                return hits
            except Exception as e:
                log.warning("SearXNG search failed for %r: %s", query, e)
                return []

        async with httpx.AsyncClient(timeout=30) as client:
            all_hits = await asyncio.gather(*[_search_one(client, q) for q in queries])

        for hits in all_hits:
            for hit in hits:
                if hit.url not in seen_urls:
                    seen_urls.add(hit.url)
                    results.append(hit)

        return results[:max_results]

    async def fetch(self, url: str) -> FetchedContent:
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                html = resp.text

            text = trafilatura.extract(html) or ""
            title = ""
            if "<title>" in html.lower():
                start = html.lower().index("<title>") + 7
                end = html.lower().index("</title>", start)
                title = html[start:end].strip()

            return FetchedContent(url=url, title=title, text=text, provider="web")
        except Exception as e:
            log.warning("Fetch failed for %s: %s", url, e)
            return FetchedContent(url=url, title="", text="", provider="web", error=str(e))
