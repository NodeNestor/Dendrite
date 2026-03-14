"""Semantic claim deduplication — embedding-based similarity detection."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

log = logging.getLogger(__name__)


def _tokenize(text: str) -> list[str]:
    """Simple word tokenizer — lowercase, strip punctuation."""
    import re
    return re.findall(r"\b[a-z0-9]+\b", text.lower())


def _tfidf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    """Build TF-IDF vector from tokens."""
    tf: dict[str, float] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    total = len(tokens) or 1
    return {t: (count / total) * idf.get(t, 1.0) for t, count in tf.items()}


def _cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity between two sparse vectors."""
    keys = set(a) & set(b)
    if not keys:
        return 0.0
    dot = sum(a[k] * b[k] for k in keys)
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


@dataclass
class DedupResult:
    is_duplicate: bool
    similarity: float
    matched_claim: str | None = None


class SemanticDeduplicator:
    """Detect semantically similar claims using TF-IDF cosine similarity.

    This is a lightweight approach that doesn't require external embedding models.
    Falls back gracefully without GPU/API dependencies.
    """

    def __init__(self, threshold: float = 0.75) -> None:
        self.threshold = threshold
        self._claims: list[str] = []
        self._vectors: list[dict[str, float]] = []
        self._idf: dict[str, float] = {}
        self._doc_freq: dict[str, int] = {}
        self._n_docs = 0

    def add_claim(self, text: str) -> DedupResult:
        """Check if claim is duplicate, then add to index.

        Returns DedupResult indicating if it's a duplicate.
        """
        tokens = _tokenize(text)
        if not tokens:
            return DedupResult(is_duplicate=False, similarity=0.0)

        # Update IDF
        self._n_docs += 1
        seen_tokens = set(tokens)
        for t in seen_tokens:
            self._doc_freq[t] = self._doc_freq.get(t, 0) + 1
        self._idf = {
            t: math.log((self._n_docs + 1) / (freq + 1)) + 1
            for t, freq in self._doc_freq.items()
        }

        # Build vector for new claim
        vec = _tfidf_vector(tokens, self._idf)

        # Check against existing claims
        best_sim = 0.0
        best_match: str | None = None
        for i, existing_vec in enumerate(self._vectors):
            sim = _cosine_similarity(vec, existing_vec)
            if sim > best_sim:
                best_sim = sim
                best_match = self._claims[i]

        is_dup = best_sim >= self.threshold

        if not is_dup:
            self._claims.append(text)
            self._vectors.append(vec)

        return DedupResult(
            is_duplicate=is_dup,
            similarity=best_sim,
            matched_claim=best_match if is_dup else None,
        )

    def check(self, text: str) -> DedupResult:
        """Check similarity without adding to the index."""
        tokens = _tokenize(text)
        if not tokens:
            return DedupResult(is_duplicate=False, similarity=0.0)

        vec = _tfidf_vector(tokens, self._idf)

        best_sim = 0.0
        best_match: str | None = None
        for i, existing_vec in enumerate(self._vectors):
            sim = _cosine_similarity(vec, existing_vec)
            if sim > best_sim:
                best_sim = sim
                best_match = self._claims[i]

        return DedupResult(
            is_duplicate=best_sim >= self.threshold,
            similarity=best_sim,
            matched_claim=best_match if best_sim >= self.threshold else None,
        )

    @property
    def size(self) -> int:
        return len(self._claims)

    def reset(self) -> None:
        self._claims.clear()
        self._vectors.clear()
        self._idf.clear()
        self._doc_freq.clear()
        self._n_docs = 0
