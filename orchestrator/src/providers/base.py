"""Provider ABC — plug in any data source."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SearchHit:
    """A single search result from any provider."""
    url: str
    title: str
    snippet: str
    provider: str
    source_date: str | None = None


@dataclass
class FetchedContent:
    """Downloaded and text-extracted page content."""
    url: str
    title: str
    text: str
    provider: str = ""
    source_date: str | None = None
    error: str | None = None


class BaseProvider(ABC):
    """Abstract base for all data providers.

    Implementations must provide:
    - name: unique provider identifier
    - search(): find relevant URLs given queries
    - fetch(): download and extract text from a URL
    """

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def search(self, queries: list[str], max_results: int = 10) -> list[SearchHit]:
        """Search for relevant content matching the given queries."""
        ...

    @abstractmethod
    async def fetch(self, url: str) -> FetchedContent:
        """Fetch and extract text content from a URL."""
        ...
