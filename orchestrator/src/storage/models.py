"""Pydantic models for HiveMindDB API — copied from DeepResearch."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    FACT = "fact"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    SEMANTIC = "semantic"


class MemoryCreate(BaseModel):
    content: str
    memory_type: MemoryType = MemoryType.FACT
    agent_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class MemoryResponse(BaseModel):
    id: int
    content: str
    memory_type: MemoryType
    agent_id: str | None = None
    confidence: float = 0.9
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    metadata: dict = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str
    agent_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    limit: int = 10
    include_graph: bool = False


class SearchResult(BaseModel):
    memory: MemoryResponse
    score: float
    related_entities: list[EntityResponse] = Field(default_factory=list)


class EntityCreate(BaseModel):
    name: str
    entity_type: str
    description: str | None = None
    agent_id: str | None = None
    metadata: dict = Field(default_factory=dict)


class EntityResponse(BaseModel):
    id: int
    name: str
    entity_type: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata: dict = Field(default_factory=dict)


class RelationCreate(BaseModel):
    source_entity_id: int
    target_entity_id: int
    relation_type: str
    description: str | None = None
    weight: float = 1.0
    created_by: str = "dendrite"
    metadata: dict = Field(default_factory=dict)


SearchResult.model_rebuild()
