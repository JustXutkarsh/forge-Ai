"""Pydantic request and response models for the Forge API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RootResponse(BaseModel):
    status: str
    version: str
    embedding_provider: str
    embedding_model: str
    llm_provider: str
    semantic_ready: bool


class EvidenceItem(BaseModel):
    ticket_id: str
    score: float = Field(ge=0.0, le=1.0)
    summary: str


class InvestigationContext(BaseModel):
    retrieval_strategy: str = Field(min_length=1, max_length=40)
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=20)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    max_evidence: int = Field(default=5, ge=1, le=20)
    investigation_context: InvestigationContext | None = None


class Timings(BaseModel):
    embedding_ms: float
    retrieval_ms: float
    reasoning_ms: float
    total_ms: float


class AskResponse(BaseModel):
    question: str
    answer: str
    confidence: float = Field(ge=0.0, le=1.0)
    retrieval_strategy: str
    reasoning_provider: str
    evidence: list[EvidenceItem]
    timings: Timings


class RetrievalHealthResponse(BaseModel):
    status: str
    chroma_reachable: bool
    sqlite_reachable: bool
    embedding_model_loaded: bool
    collection_size: int | None
    latency_ms: float


class StatsResponse(BaseModel):
    total_tickets: int
    embedded_tickets: int
    embedding_model: str
    vector_dimension: int | None
    chroma_collection_count: int | None


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
