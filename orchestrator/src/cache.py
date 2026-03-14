"""Fetch cache — LRU in-memory cache for fetched page content."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock

log = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    url: str
    title: str
    text: str
    provider: str
    source_date: str | None
    error: str | None
    fetched_at: float


class FetchCache:
    """Thread-safe LRU cache for fetched pages."""

    def __init__(self, max_size: int = 500, ttl_seconds: float = 3600.0) -> None:
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = Lock()
        self._hits = 0
        self._misses = 0

    def get(self, url: str) -> CacheEntry | None:
        with self._lock:
            entry = self._cache.get(url)
            if entry is None:
                self._misses += 1
                return None
            if time.monotonic() - entry.fetched_at > self._ttl:
                del self._cache[url]
                self._misses += 1
                return None
            # Move to end (most recently used)
            self._cache.move_to_end(url)
            self._hits += 1
            return entry

    def put(self, url: str, title: str, text: str, provider: str,
            source_date: str | None = None, error: str | None = None) -> None:
        with self._lock:
            if url in self._cache:
                self._cache.move_to_end(url)
            self._cache[url] = CacheEntry(
                url=url, title=title, text=text, provider=provider,
                source_date=source_date, error=error,
                fetched_at=time.monotonic(),
            )
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    @property
    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{self._hits / total:.0%}" if total else "0%",
            }

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0


# Global singleton
fetch_cache = FetchCache()
