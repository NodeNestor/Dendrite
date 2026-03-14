"""Academic providers — arXiv + Semantic Scholar for scholarly sources."""

from __future__ import annotations

import asyncio
import logging
import re
import xml.etree.ElementTree as ET

import httpx

from .base import BaseProvider, FetchedContent, SearchHit

log = logging.getLogger(__name__)


class ArxivProvider(BaseProvider):
    """arXiv API search + abstract extraction."""

    API_URL = "http://export.arxiv.org/api/query"

    @property
    def name(self) -> str:
        return "arxiv"

    async def search(self, queries: list[str], max_results: int = 10) -> list[SearchHit]:
        results: list[SearchHit] = []
        seen: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            tasks = [self._search_one(client, q, max_results) for q in queries]
            all_hits = await asyncio.gather(*tasks, return_exceptions=True)

        for hits in all_hits:
            if isinstance(hits, Exception):
                log.warning("arXiv search failed: %s", hits)
                continue
            for hit in hits:
                if hit.url not in seen:
                    seen.add(hit.url)
                    results.append(hit)

        return results[:max_results]

    async def _search_one(
        self, client: httpx.AsyncClient, query: str, max_results: int,
    ) -> list[SearchHit]:
        try:
            resp = await client.get(
                self.API_URL,
                params={
                    "search_query": f"all:{query}",
                    "start": 0,
                    "max_results": max_results,
                    "sortBy": "relevance",
                },
            )
            resp.raise_for_status()
            return self._parse_atom(resp.text)
        except Exception as e:
            log.warning("arXiv query failed for %r: %s", query, e)
            return []

    @staticmethod
    def _parse_atom(xml_text: str) -> list[SearchHit]:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        hits: list[SearchHit] = []
        try:
            root = ET.fromstring(xml_text)
            for entry in root.findall("atom:entry", ns):
                title_el = entry.find("atom:title", ns)
                summary_el = entry.find("atom:summary", ns)
                published_el = entry.find("atom:published", ns)
                link_el = entry.find("atom:id", ns)

                url = ""
                if link_el is not None and link_el.text:
                    url = link_el.text.strip()
                    # Convert API URL to abs URL
                    url = url.replace("http://arxiv.org/abs/", "https://arxiv.org/abs/")

                title = title_el.text.strip() if title_el is not None and title_el.text else ""
                title = re.sub(r"\s+", " ", title)
                snippet = summary_el.text.strip() if summary_el is not None and summary_el.text else ""
                snippet = re.sub(r"\s+", " ", snippet)
                pub_date = published_el.text.strip() if published_el is not None and published_el.text else None

                # Get all authors
                authors = []
                for author_el in entry.findall("atom:author/atom:name", ns):
                    if author_el.text:
                        authors.append(author_el.text.strip())
                if authors:
                    title = f"{title} ({', '.join(authors[:3])}{'...' if len(authors) > 3 else ''})"

                if url:
                    hits.append(SearchHit(
                        url=url,
                        title=title,
                        snippet=snippet[:500],
                        provider="arxiv",
                        source_date=pub_date,
                    ))
        except ET.ParseError as e:
            log.warning("Failed to parse arXiv XML: %s", e)
        return hits

    async def fetch(self, url: str) -> FetchedContent:
        """Fetch arXiv abstract page and extract text."""
        try:
            # For arXiv, the abstract is already in the search results,
            # but we can also fetch the HTML page for more context
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                # Try to get the abstract via API for cleaner text
                arxiv_id = ""
                if "/abs/" in url:
                    arxiv_id = url.split("/abs/")[-1]
                elif "/pdf/" in url:
                    arxiv_id = url.split("/pdf/")[-1].replace(".pdf", "")

                if arxiv_id:
                    api_resp = await client.get(
                        self.API_URL,
                        params={"id_list": arxiv_id},
                    )
                    if api_resp.status_code == 200:
                        hits = self._parse_atom(api_resp.text)
                        if hits:
                            return FetchedContent(
                                url=url,
                                title=hits[0].title,
                                text=hits[0].snippet,
                                provider="arxiv",
                                source_date=hits[0].source_date,
                            )

                # Fallback: fetch HTML
                resp = await client.get(url)
                resp.raise_for_status()
                import trafilatura
                text = trafilatura.extract(resp.text) or ""
                title = ""
                html_lower = resp.text.lower()
                if "<title>" in html_lower:
                    start = html_lower.index("<title>") + 7
                    end = html_lower.index("</title>", start)
                    title = resp.text[start:end].strip()
                return FetchedContent(url=url, title=title, text=text, provider="arxiv")

        except Exception as e:
            log.warning("arXiv fetch failed for %s: %s", url, e)
            return FetchedContent(url=url, title="", text="", provider="arxiv", error=str(e))


class SemanticScholarProvider(BaseProvider):
    """Semantic Scholar API — free academic paper search."""

    API_URL = "https://api.semanticscholar.org/graph/v1"
    SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key

    @property
    def name(self) -> str:
        return "semantic_scholar"

    async def search(self, queries: list[str], max_results: int = 10) -> list[SearchHit]:
        results: list[SearchHit] = []
        seen: set[str] = set()

        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for query in queries:
                try:
                    resp = await client.get(
                        self.SEARCH_URL,
                        params={
                            "query": query,
                            "limit": max_results,
                            "fields": "title,abstract,url,year,authors,citationCount,publicationDate,externalIds",
                        },
                    )
                    if resp.status_code == 429:
                        log.warning("Semantic Scholar rate limited, backing off")
                        await asyncio.sleep(2)
                        continue
                    resp.raise_for_status()
                    data = resp.json()

                    for paper in data.get("data", []):
                        paper_url = paper.get("url", "")
                        # Prefer DOI URL if available
                        ext_ids = paper.get("externalIds", {})
                        if ext_ids and ext_ids.get("DOI"):
                            paper_url = f"https://doi.org/{ext_ids['DOI']}"
                        elif ext_ids and ext_ids.get("ArXiv"):
                            paper_url = f"https://arxiv.org/abs/{ext_ids['ArXiv']}"

                        if not paper_url or paper_url in seen:
                            continue
                        seen.add(paper_url)

                        title = paper.get("title", "")
                        authors = paper.get("authors", [])
                        author_str = ", ".join(
                            a.get("name", "") for a in authors[:3]
                        )
                        if len(authors) > 3:
                            author_str += "..."
                        if author_str:
                            title = f"{title} ({author_str})"

                        citations = paper.get("citationCount", 0)
                        abstract = paper.get("abstract", "") or ""
                        snippet = abstract[:500]
                        if citations:
                            snippet = f"[{citations} citations] {snippet}"

                        results.append(SearchHit(
                            url=paper_url,
                            title=title,
                            snippet=snippet,
                            provider="semantic_scholar",
                            source_date=paper.get("publicationDate"),
                        ))

                except Exception as e:
                    log.warning("Semantic Scholar search failed for %r: %s", query, e)

                # Rate limit: 100 requests per 5 min without key
                if not self.api_key:
                    await asyncio.sleep(0.5)

        return results[:max_results]

    async def fetch(self, url: str) -> FetchedContent:
        """Fetch paper details from Semantic Scholar or fall back to web."""
        try:
            # Try to extract paper ID and get abstract from S2 API
            headers = {}
            if self.api_key:
                headers["x-api-key"] = self.api_key

            async with httpx.AsyncClient(timeout=30, headers=headers, follow_redirects=True) as client:
                # Try direct URL fetch with trafilatura
                resp = await client.get(url)
                resp.raise_for_status()
                import trafilatura
                text = trafilatura.extract(resp.text) or ""
                title = ""
                html_lower = resp.text.lower()
                if "<title>" in html_lower:
                    start = html_lower.index("<title>") + 7
                    end = html_lower.index("</title>", start)
                    title = resp.text[start:end].strip()

                return FetchedContent(
                    url=url, title=title, text=text,
                    provider="semantic_scholar",
                )

        except Exception as e:
            log.warning("Semantic Scholar fetch failed for %s: %s", url, e)
            return FetchedContent(
                url=url, title="", text="",
                provider="semantic_scholar", error=str(e),
            )
