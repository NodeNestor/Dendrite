"""Source quality scoring — rate sources by authority, type, and recency."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

# Domain authority tiers (higher = more trustworthy)
_AUTHORITY_TIERS: dict[str, float] = {
    # Tier 1: Peer-reviewed / official (0.9-1.0)
    "nature.com": 0.95, "science.org": 0.95, "thelancet.com": 0.95,
    "nejm.org": 0.95, "cell.com": 0.95, "pnas.org": 0.95,
    "arxiv.org": 0.90, "pubmed.ncbi.nlm.nih.gov": 0.90,
    "scholar.google.com": 0.85, "semanticscholar.org": 0.85,
    "who.int": 0.90, "cdc.gov": 0.90, "nih.gov": 0.90,
    "gov.uk": 0.85, "europa.eu": 0.85, "un.org": 0.85,
    "ieee.org": 0.90, "acm.org": 0.90, "springer.com": 0.85,
    "wiley.com": 0.85, "elsevier.com": 0.85, "jstor.org": 0.85,

    # Tier 2: Quality journalism / encyclopedias (0.7-0.85)
    "reuters.com": 0.80, "apnews.com": 0.80,
    "bbc.com": 0.78, "bbc.co.uk": 0.78,
    "nytimes.com": 0.75, "washingtonpost.com": 0.75,
    "theguardian.com": 0.73, "economist.com": 0.75,
    "wikipedia.org": 0.70, "britannica.com": 0.75,
    "ft.com": 0.75, "wsj.com": 0.75,
    "scientificamerican.com": 0.78, "newscientist.com": 0.75,

    # Tier 3: Established tech/business sources (0.6-0.7)
    "techcrunch.com": 0.65, "arstechnica.com": 0.68,
    "wired.com": 0.65, "theverge.com": 0.62,
    "bloomberg.com": 0.72, "cnbc.com": 0.65,
    "github.com": 0.60, "stackoverflow.com": 0.60,
}

# TLD-based baseline scores
_TLD_SCORES: dict[str, float] = {
    ".gov": 0.80, ".edu": 0.75, ".ac.uk": 0.75,
    ".org": 0.55, ".int": 0.70,
    ".com": 0.40, ".net": 0.40, ".io": 0.35,
}

# Source type detection patterns
_SOURCE_PATTERNS: list[tuple[str, str, float]] = [
    # (pattern in URL/domain, source_type, base_score_boost)
    (r"doi\.org|/doi/", "peer_reviewed", 0.15),
    (r"arxiv\.org", "preprint", 0.10),
    (r"pubmed|ncbi\.nlm", "peer_reviewed", 0.15),
    (r"github\.com", "code_repository", 0.0),
    (r"wikipedia\.org", "encyclopedia", 0.05),
    (r"reddit\.com|forum|discuss", "forum", -0.10),
    (r"blog\.|medium\.com|substack", "blog", -0.05),
    (r"youtube\.com|youtu\.be", "video", -0.10),
    (r"twitter\.com|x\.com", "social_media", -0.15),
]


def score_source(
    url: str,
    source_date: str | None = None,
    provider: str = "",
    recency_weight: float = 0.2,
) -> SourceScore:
    """Score a source for authority, type, and recency.

    Returns a SourceScore with:
    - authority: 0.0-1.0 (domain trust)
    - recency: 0.0-1.0 (how recent)
    - source_type: classified type
    - overall: weighted composite 0.0-1.0
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower().lstrip("www.")

    # Authority score
    authority = _get_authority(domain)

    # Source type detection
    source_type = "web"
    type_boost = 0.0
    for pattern, stype, boost in _SOURCE_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            source_type = stype
            type_boost = boost
            break

    # Provider boost
    if provider in ("arxiv", "semantic_scholar"):
        source_type = "academic"
        type_boost = max(type_boost, 0.10)

    # Recency score
    recency = _get_recency(source_date)

    # Overall composite
    overall = (
        (authority + type_boost) * 0.6
        + recency * recency_weight
        + 0.2  # baseline
    )
    overall = max(0.0, min(1.0, overall))

    return SourceScore(
        authority=authority,
        recency=recency,
        source_type=source_type,
        type_boost=type_boost,
        overall=overall,
    )


def _get_authority(domain: str) -> float:
    """Get domain authority score."""
    # Exact match
    if domain in _AUTHORITY_TIERS:
        return _AUTHORITY_TIERS[domain]

    # Subdomain match (e.g., news.bbc.co.uk -> bbc.co.uk)
    parts = domain.split(".")
    for i in range(len(parts) - 1):
        parent = ".".join(parts[i:])
        if parent in _AUTHORITY_TIERS:
            return _AUTHORITY_TIERS[parent]

    # TLD-based fallback
    for tld, score in _TLD_SCORES.items():
        if domain.endswith(tld):
            return score

    return 0.35  # unknown domain baseline


def _get_recency(source_date: str | None) -> float:
    """Score recency: 1.0 = today, decays over time."""
    if not source_date:
        return 0.5  # unknown date = neutral

    try:
        # Try common date formats
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%Y-%m", "%Y"):
            try:
                dt = datetime.strptime(source_date[:len(fmt) + 5], fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue
        else:
            return 0.5

        now = datetime.now(timezone.utc)
        days_old = max(0, (now - dt).days)

        if days_old <= 30:
            return 1.0
        elif days_old <= 90:
            return 0.9
        elif days_old <= 365:
            return 0.7
        elif days_old <= 365 * 2:
            return 0.5
        elif days_old <= 365 * 5:
            return 0.3
        else:
            return 0.1

    except Exception:
        return 0.5


class SourceScore:
    """Source quality assessment."""

    __slots__ = ("authority", "recency", "source_type", "type_boost", "overall")

    def __init__(
        self, authority: float, recency: float,
        source_type: str, type_boost: float, overall: float,
    ) -> None:
        self.authority = authority
        self.recency = recency
        self.source_type = source_type
        self.type_boost = type_boost
        self.overall = overall

    def to_dict(self) -> dict:
        return {
            "authority": round(self.authority, 3),
            "recency": round(self.recency, 3),
            "source_type": self.source_type,
            "overall": round(self.overall, 3),
        }
