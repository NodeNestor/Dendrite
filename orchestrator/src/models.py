"""Dendrite data models — tree-structured research with claim verification."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id() -> str:
    return uuid.uuid4().hex[:12]


# -- Enums ---------------------------------------------------------------

class BranchType(str, Enum):
    INVESTIGATION = "investigation"
    VERIFICATION = "verification"
    DEEPENING = "deepening"
    COUNTER = "counter"
    RESOLUTION = "resolution"  # contradiction resolution branch


class ClaimStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REFUTED = "refuted"
    CONTESTED = "contested"
    ACCEPTED = "accepted"


class TreeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    CONVERGED = "converged"
    FAILED = "failed"


class TriageAction(str, Enum):
    ACCEPT = "accept"
    VERIFY = "verify"
    DEEPEN = "deepen"
    COUNTER = "counter"


# -- Evidence -------------------------------------------------------------

class Evidence(BaseModel):
    """A piece of data supporting or contradicting a claim."""
    id: str = Field(default_factory=_id)
    content: str
    source_url: str = ""
    source_title: str = ""
    source_date: Optional[str] = None
    provider: str = ""  # which provider found this
    supports_claim: bool = True  # True=supports, False=contradicts
    confidence: float = 0.5
    discovered_at: datetime = Field(default_factory=_now)
    # Source quality scoring
    source_quality: float = 0.0  # 0.0-1.0 overall source quality
    source_type: str = ""  # peer_reviewed, preprint, news, blog, etc.
    source_authority: float = 0.0  # 0.0-1.0 domain authority


# -- Claim ----------------------------------------------------------------

class Claim(BaseModel):
    """A factual assertion extracted from evidence."""
    id: str = Field(default_factory=_id)
    content: str
    status: ClaimStatus = ClaimStatus.PENDING
    confidence: float = 0.5
    evidence_for: list[Evidence] = Field(default_factory=list)
    evidence_against: list[Evidence] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    verification_query: Optional[str] = None  # search query for verification branch
    deepening_question: Optional[str] = None  # sub-question for deepening branch
    created_at: datetime = Field(default_factory=_now)
    updated_at: Optional[datetime] = None
    status_history: list[str] = Field(default_factory=list)  # audit trail

    @property
    def independent_sources(self) -> int:
        """Count truly independent sources (different domains)."""
        domains = set()
        for e in self.evidence_for:
            if e.source_url:
                from urllib.parse import urlparse
                domain = urlparse(e.source_url).netloc
                domains.add(domain)
        return len(domains)


# -- Branch ---------------------------------------------------------------

class Branch(BaseModel):
    """A line of investigation within the research tree."""
    id: str = Field(default_factory=_id)
    question: str
    branch_type: BranchType = BranchType.INVESTIGATION
    parent_branch_id: Optional[str] = None
    parent_claim_id: Optional[str] = None  # claim that spawned this branch
    depth: int = 0
    iteration: int = 0
    max_iterations: int = 5
    claims: list[Claim] = Field(default_factory=list)
    child_branch_ids: list[str] = Field(default_factory=list)
    converged: bool = False
    convergence_reason: str = ""
    created_at: datetime = Field(default_factory=_now)
    finished_at: Optional[datetime] = None

    # Stats
    urls_searched: int = 0
    pages_fetched: int = 0
    queries_used: list[str] = Field(default_factory=list)


# -- ResearchTree ---------------------------------------------------------

class ResearchTree(BaseModel):
    """The full investigation — a tree of branches containing claims."""
    id: str = Field(default_factory=_id)
    question: str
    status: TreeStatus = TreeStatus.PENDING
    root_branch_id: Optional[str] = None
    branches: dict[str, Branch] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    finished_at: Optional[datetime] = None

    # Config
    max_depth: int = 4
    max_branch_iterations: int = 5
    verification_threshold: float = 0.6  # confidence below this triggers verification

    # Stats
    total_claims: int = 0
    verified_claims: int = 0
    refuted_claims: int = 0
    contested_claims: int = 0
    total_evidence: int = 0
    total_sources: int = 0

    # Token tracking
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0
    llm_requests: int = 0
    pages_fetched: int = 0

    # Final output
    synthesis: str = ""

    # Refinement tracking
    refinement_pass: int = 0  # how many self-critique rounds completed

    def add_branch(self, branch: Branch) -> None:
        self.branches[branch.id] = branch
        if branch.parent_branch_id and branch.parent_branch_id in self.branches:
            parent = self.branches[branch.parent_branch_id]
            if branch.id not in parent.child_branch_ids:
                parent.child_branch_ids.append(branch.id)

    def get_branch(self, branch_id: str) -> Branch | None:
        return self.branches.get(branch_id)

    def all_claims(self) -> list[Claim]:
        claims = []
        for branch in self.branches.values():
            claims.extend(branch.claims)
        return claims

    def update_stats(self) -> None:
        all_claims = self.all_claims()
        self.total_claims = len(all_claims)
        self.verified_claims = sum(1 for c in all_claims if c.status == ClaimStatus.VERIFIED)
        self.refuted_claims = sum(1 for c in all_claims if c.status == ClaimStatus.REFUTED)
        self.contested_claims = sum(1 for c in all_claims if c.status == ClaimStatus.CONTESTED)
        self.total_evidence = sum(
            len(c.evidence_for) + len(c.evidence_against) for c in all_claims
        )
        source_urls = set()
        for c in all_claims:
            source_urls.update(c.source_urls)
        self.total_sources = len(source_urls)


# -- Progress events (WebSocket) ------------------------------------------

class ProgressEvent(BaseModel):
    """Real-time progress update sent over WebSocket."""
    tree_id: str
    branch_id: str = ""
    event_type: str  # branch_started, claims_extracted, claim_triaged, branch_converged, tree_complete, etc.
    message: str = ""
    data: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_now)


# -- API models -----------------------------------------------------------

class InvestigateRequest(BaseModel):
    question: str
    max_depth: int = 4
    max_branch_iterations: int = 5
    providers: list[str] | None = None  # which providers to use


class TreeSummary(BaseModel):
    id: str
    question: str
    status: TreeStatus
    total_claims: int = 0
    verified_claims: int = 0
    refuted_claims: int = 0
    contested_claims: int = 0
    created_at: datetime
    finished_at: Optional[datetime] = None
