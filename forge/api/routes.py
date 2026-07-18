"""HTTP routes that delegate to the existing Forge engine."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, Response, status

from forge import __version__
from forge.agent.executor import ask as execute_ask
from forge.config import EMBEDDING_MODEL, EMBEDDING_PROVIDER
from forge.profiling import capture

from forge.api.dependencies import ForgeRuntime, get_runtime
from forge.api.models import (
    AskRequest,
    AskResponse,
    EvidenceItem,
    RetrievalHealthResponse,
    RootResponse,
    StatsResponse,
    Timings,
)


logger = logging.getLogger("forge.api")
router = APIRouter()


def _tool_names(payload: dict[str, Any]) -> list[str]:
    calls = payload.get("tool_calls", [])
    return [call.get("name", "") if isinstance(call, dict) else str(call) for call in calls]


def _retrieval_strategy(payload: dict[str, Any], notes: list[str]) -> str:
    if any(message.startswith("Retrieval strategy=semantic") for message in notes):
        return "semantic"
    if any(message.startswith("Retrieval strategy=sql_fallback") for message in notes):
        return "sql_fallback"
    if "query_structured" in _tool_names(payload):
        return "structured"
    return str(payload.get("retrieval_strategy") or "unknown")


def _evidence_rows(payload: dict[str, Any], max_evidence: int) -> list[EvidenceItem]:
    evidence = payload.get("tickets") or []
    if not evidence and isinstance(payload.get("evidence"), dict):
        evidence = payload["evidence"].get("tickets") or []
    result: list[EvidenceItem] = []
    confidence = float(payload.get("confidence", 0.0) or 0.0)
    for ticket in evidence[:max_evidence]:
        distance = ticket.get("_retrieval_distance")
        score = 1.0 - float(distance) if distance is not None else confidence
        score = max(0.0, min(1.0, score))
        resolution = str(ticket.get("resolution_notes") or "").strip()
        issue = str(ticket.get("issue_description") or "").strip()
        category = str(ticket.get("category") or "").strip()
        summary = resolution or issue or category or "Indexed support ticket evidence."
        result.append(EvidenceItem(ticket_id=str(ticket.get("ticket_id", "")), score=score, summary=summary[:500]))
    if not result and "query_structured" in _tool_names(payload):
        result.append(EvidenceItem(ticket_id="query_structured", score=confidence, summary="Structured SQLite result."))
    return result


def _timings(captured: dict[str, Any], total_ms: float) -> Timings:
    values = captured.get("timings", {})
    embedding = float(values.get("Embedding request", 0.0)) * 1000
    retrieval = float(values.get("Retrieval", 0.0)) * 1000
    reasoning_names = ("OpenAI initialization", "OpenAI request")
    reasoning = sum(float(values.get(name, 0.0)) for name in reasoning_names) * 1000
    if reasoning == 0:
        reasoning = sum(float(values.get(name, 0.0)) for name in ("Planner", "Summary")) * 1000
    return Timings(embedding_ms=round(embedding, 2), retrieval_ms=round(retrieval, 2), reasoning_ms=round(reasoning, 2), total_ms=round(total_ms, 2))


@router.get("/", response_model=RootResponse)
def root(runtime: ForgeRuntime = Depends(get_runtime)) -> RootResponse:
    return RootResponse(
        status="ok",
        version=__version__,
        embedding_provider=EMBEDDING_PROVIDER,
        embedding_model=EMBEDDING_MODEL,
        llm_provider="openai",
        semantic_ready=runtime.semantic_ready,
    )


@router.post("/ask", response_model=AskResponse)
def ask(request: AskRequest, runtime: ForgeRuntime = Depends(get_runtime)) -> AskResponse:
    started = time.perf_counter()
    logger.info("ask question=%r", request.question)
    try:
        with capture() as captured:
            context = request.investigation_context.model_dump() if request.investigation_context else None
            if context is None:
                payload = execute_ask(runtime.connection(), request.question)
            else:
                payload = execute_ask(runtime.connection(), request.question, context)
    except Exception:
        logger.exception("ask failed question=%r", request.question)
        raise
    total_ms = (time.perf_counter() - started) * 1000
    strategy = _retrieval_strategy(payload, captured["notes"])
    logger.info("ask strategy=%s latency_ms=%.2f", strategy, total_ms)
    return AskResponse(
        question=request.question,
        answer=str(payload.get("answer", "")),
        confidence=max(0.0, min(1.0, float(payload.get("confidence", 0.0) or 0.0))),
        retrieval_strategy=strategy,
        reasoning_provider="openai",
        evidence=_evidence_rows(payload, request.max_evidence),
        timings=_timings(captured, total_ms),
    )


@router.post("/health/retrieval", response_model=RetrievalHealthResponse)
def retrieval_health(response: Response, runtime: ForgeRuntime = Depends(get_runtime)) -> RetrievalHealthResponse:
    started = time.perf_counter()
    sqlite_reachable = False
    chroma_reachable = False
    collection_size: int | None = None
    try:
        runtime.connection().execute("SELECT 1").fetchone()
        sqlite_reachable = True
    except Exception:
        logger.exception("retrieval health SQLite check failed")
    try:
        if runtime.chroma_store is not None:
            collection_size = runtime.chroma_store.count()
            chroma_reachable = True
    except Exception:
        logger.exception("retrieval health Chroma check failed")
    healthy = sqlite_reachable and chroma_reachable and runtime.embedding_service is not None
    response.status_code = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return RetrievalHealthResponse(
        status="ok" if healthy else "degraded",
        chroma_reachable=chroma_reachable,
        sqlite_reachable=sqlite_reachable,
        embedding_model_loaded=runtime.embedding_service is not None,
        collection_size=collection_size,
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
    )


@router.get("/stats", response_model=StatsResponse)
def stats(runtime: ForgeRuntime = Depends(get_runtime)) -> StatsResponse:
    row = runtime.connection().execute(
        "SELECT COUNT(*) AS total, SUM(CASE WHEN embedding_status = 'embedded' THEN 1 ELSE 0 END) AS embedded FROM tickets"
    ).fetchone()
    collection_count = runtime.chroma_store.count() if runtime.chroma_store is not None else None
    dimension = getattr(runtime.embedding_service, "dimension", None)
    return StatsResponse(
        total_tickets=int(row["total"] or 0),
        embedded_tickets=int(row["embedded"] or 0),
        embedding_model=EMBEDDING_MODEL,
        vector_dimension=int(dimension) if dimension is not None else None,
        chroma_collection_count=collection_count,
    )
