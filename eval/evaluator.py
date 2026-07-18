"""Bounded-memory evaluation harness for Forge planner and retrieval quality."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Callable

from forge.agent.planner import AgentPlan, plan_question
from forge.agent.tools import MIN_EVIDENCE_CONFIDENCE, SUPPORTED_QUERY_TERMS, summarize
from forge.analytics.queries import query_structured
from forge.config import CHROMA_PATH
from forge.rag.rerank import rerank
from forge.rag.retrieve import PUBLIC_FIELDS, STOPWORDS
from forge.rag.vectorstore import ChromaStore
from forge.search.query_normalizer import expand_query

from eval.metrics import (
    average_latency,
    precision_at_k,
)


AnswerFunction = Callable[[sqlite3.Connection, str], dict[str, Any]]
ALLOWED_GOLD_FIELDS = {"ticket_id", "product", "category", "priority", "status", "channel", "region"}
NO_EVIDENCE_PHRASES = ("no supporting evidence", "not found in available data")


@dataclass
class CaseResult:
    """Small, bounded outcome for one evaluation case."""

    case_id: str
    question: str
    case_type: str
    expected_tools: list[str]
    actual_tools: list[str]
    planner_correct: bool
    structured_applicable: bool
    structured_correct: bool
    relevant_ticket_count: int
    relevant_retrieved_ids: list[str]
    retrieved_ticket_ids: list[str]
    recall_at_5: float | None
    precision_at_5: float | None
    hallucination: bool
    grounded: bool
    latency_ms: float
    error: str | None = None

class EvaluationAnswerer:
    """Run evaluation answers with one lazy OpenAI/Chroma resource set."""

    def __init__(self) -> None:
        self._embedding_client: Any | None = None
        self._chroma_store: ChromaStore | None = None
        self._chroma_attempted = False
        if os.getenv("OPENAI_API_KEY", "").strip():
            try:
                from openai import OpenAI
                self._embedding_client = OpenAI(timeout=60, max_retries=0)
            except Exception:
                self._embedding_client = None

    def close(self) -> None:
        """Release shared evaluation resources."""
        self._chroma_store = None
        self._embedding_client = None

    def _store(self) -> ChromaStore | None:
        """Open Chroma at most once and only when semantic retrieval is available."""
        if self._chroma_attempted or self._embedding_client is None:
            return self._chroma_store
        self._chroma_attempted = True
        try:
            self._chroma_store = ChromaStore(CHROMA_PATH)
        except Exception:
            self._chroma_store = None
        return self._chroma_store

    def _semantic_retrieve(self, conn: sqlite3.Connection, query: str, k: int) -> list[dict[str, Any]] | None:
        """Retrieve only top-k rows using the shared embedding client/store."""
        store = self._store()
        if store is None or self._embedding_client is None:
            return None
        try:
            embedding = self._embedding_client.embeddings.create(
                model=os.getenv("FORGE_EMBED_MODEL", "text-embedding-3-large"), input=[query]
            ).data[0].embedding
            result = store.query(embedding, k)
            ids = list(result.get("ids", [[]])[0][:k])
            if not ids:
                return []
            placeholders = ",".join("?" for _ in ids)
            rows = conn.execute(
                f"SELECT {', '.join(PUBLIC_FIELDS)} FROM tickets WHERE ticket_id IN ({placeholders})", ids
            ).fetchall()
            by_id = {row["ticket_id"]: dict(row) for row in rows}
            distances = result.get("distances", [[]])[0][:k]
            tickets = []
            for ticket_id, distance in zip(ids, distances):
                if ticket_id in by_id:
                    ticket = by_id[ticket_id]
                    ticket["_retrieval_distance"] = distance
                    tickets.append(ticket)
            return tickets
        except Exception:
            return None

    @staticmethod
    def _lexical_retrieve(conn: sqlite3.Connection, query: str, k: int) -> list[dict[str, Any]]:
        """Use the bounded SQLite fallback without opening another vector client."""
        tokens = [token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) > 2 and token not in STOPWORDS][:8]
        columns = ", ".join(PUBLIC_FIELDS)
        if not tokens:
            rows = conn.execute(f"SELECT {columns} FROM tickets ORDER BY ticket_created_date DESC LIMIT ?", (k,)).fetchall()
        else:
            conditions = []
            params: list[str] = []
            for token in tokens:
                like = f"%{token}%"
                conditions.append("(issue_description LIKE ? OR resolution_notes LIKE ? OR category LIKE ? OR product LIKE ? OR priority LIKE ?)")
                params.extend([like] * 5)
            rows = conn.execute(f"SELECT {columns} FROM tickets WHERE {' OR '.join(conditions)} LIMIT 500", params).fetchall()
        result = [dict(row) for row in rows]
        token_set = set(tokens)
        for item in result:
            text = " ".join(str(item.get(field, "")) for field in PUBLIC_FIELDS).lower()
            item["_score"] = sum(text.count(token) for token in token_set)
        return sorted(result, key=lambda item: item.get("_score", 0), reverse=True)[:k]

    def _search_data(self, conn: sqlite3.Connection, query: str, k: int = 5) -> dict[str, Any]:
        """Mirror the existing search contract with shared retrieval resources."""
        retrieval_query = expand_query(query)
        tokens = set(re.findall(r"[a-z0-9]+", retrieval_query.lower()))
        if not tokens.intersection(SUPPORTED_QUERY_TERMS):
            return {"query": query, "tickets": [], "source_ticket_ids": [], "confidence": 0.0, "evidence_status": "unsupported_domain"}
        tickets = self._semantic_retrieve(conn, retrieval_query, max(k, 20))
        if tickets is None:
            tickets = self._lexical_retrieve(conn, retrieval_query, max(k, 20))
        tickets = rerank(retrieval_query, tickets, k)
        distances = [float(ticket.pop("_retrieval_distance")) for ticket in tickets if "_retrieval_distance" in ticket]
        scores = [float(ticket.pop("_score")) for ticket in tickets if "_score" in ticket]
        confidence = max(0.0, min(1.0, 1.0 - min(distances))) if distances else max(0.0, min(1.0, max(scores) / 2.0)) if scores else 0.0
        if confidence < MIN_EVIDENCE_CONFIDENCE:
            tickets = []
        return {
            "query": query,
            "tickets": tickets,
            "source_ticket_ids": [ticket["ticket_id"] for ticket in tickets],
            "confidence": round(confidence, 3),
            "evidence_status": "supported" if tickets else "insufficient_evidence",
        }

    def answer(self, conn: sqlite3.Connection, question: str) -> dict[str, Any]:
        """Execute one deterministic plan while retaining only its current case."""
        plan = plan_question(question)
        results: dict[int, dict[str, Any]] = {}
        retrieved: list[dict[str, Any]] = []
        confidence = 0.0
        tool_calls: list[str] = []
        for index, step in enumerate(plan.steps):
            tool_calls.append(step.tool)
            if step.tool == "query_structured":
                args = step.arguments
                results[index] = query_structured(conn, args["operation"], args["field"], args.get("filters"), args.get("date_range"), args.get("limit"))
            elif step.tool == "search_data":
                result = self._search_data(conn, step.arguments["query"], step.arguments.get("k", 5))
                results[index] = result
                retrieved.extend(result.get("tickets", []))
                confidence = max(confidence, float(result.get("confidence", 0.0)))
            elif step.tool == "summarize":
                source = results[step.arguments["source_step"]]
                results[index] = {"summary": summarize(source.get("tickets", []))}
            elif step.tool == "flag_anomaly":
                from forge.agent.tools import flag_anomaly
                date_range = tuple(step.arguments["date_range"]) if step.arguments.get("date_range") else None
                results[index] = flag_anomaly(conn, date_range)
            elif step.tool == "draft_report":
                from forge.agent.executor import weekly_report
                content, dates = weekly_report(conn)
                results[index] = {"report": content, "date_range": dates}
            else:
                results[index] = {"error": f"unsupported evaluation tool: {step.tool}"}
        final = results[len(plan.steps) - 1] if plan.steps else {}
        if plan.steps and plan.steps[-1].tool == "draft_report":
            answer = final["report"]
        elif plan.steps and plan.steps[0].tool == "query_structured":
            structured = final if plan.steps[-1].tool == "query_structured" else results[0]
            answer = f"Count: {structured['count']}." if structured.get("operation") == "count" else "\n".join(f"{row.get('value', row.get('period'))}: {row['count']}" for row in structured.get("results", [])[:10])
        elif plan.steps and plan.steps[-1].tool == "summarize":
            answer = final["summary"] if retrieved else "No supporting evidence found in indexed data."
        else:
            answer = summarize(retrieved) if retrieved else "No supporting evidence found in indexed data."
        source_ids = [ticket["ticket_id"] for ticket in retrieved]
        structured_evidence = results.get(0) if plan.steps and plan.steps[0].tool == "query_structured" else None
        return {"answer": answer, "evidence": retrieved or structured_evidence, "source_ticket_ids": source_ids, "sources": source_ids or (["query_structured"] if structured_evidence else []), "confidence": confidence, "tool_calls": tool_calls, "plan": plan.as_dict(), "tickets": retrieved, "structured": structured_evidence}


def load_dataset(path: str | Path) -> list[dict[str, Any]]:
    """Load and minimally validate an evaluation dataset."""
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("evaluation dataset must be a non-empty JSON list")
    for case in cases:
        if not case.get("id") or not case.get("question") or not case.get("expected_tools"):
            raise ValueError("each evaluation case requires id, question, and expected_tools")
    return cases


def _gold_statistics(conn: sqlite3.Connection, case: dict[str, Any], retrieved_ids: list[str]) -> tuple[int, list[str]]:
    """Return gold count and top-k gold hits without materializing the gold set."""
    top_ids = list(dict.fromkeys(retrieved_ids[:5]))
    if case.get("gold_ticket_ids") is not None:
        gold_ids = {str(ticket_id) for ticket_id in case["gold_ticket_ids"]}
        return len(gold_ids), [ticket_id for ticket_id in top_ids if ticket_id in gold_ids]
    filters = case.get("gold_filter") or {}
    if not filters:
        return 0, []
    if not set(filters).issubset(ALLOWED_GOLD_FIELDS):
        raise ValueError(f"unsupported gold filter field in case {case['id']}")
    where = " AND ".join(f"{field} = ?" for field in filters)
    values = [filters[field] for field in filters]
    total = int(conn.execute(f"SELECT COUNT(*) FROM tickets WHERE {where}", values).fetchone()[0])
    if not top_ids:
        return total, []
    placeholders = ",".join("?" for _ in top_ids)
    rows = conn.execute(f"SELECT ticket_id FROM tickets WHERE {where} AND ticket_id IN ({placeholders})", values + top_ids).fetchall()
    return total, [str(row[0]) for row in rows]


def _structured_match(plan: AgentPlan, case: dict[str, Any]) -> tuple[bool, bool]:
    """Compare the first structured planner step with a case expectation."""
    expected_operation = case.get("expected_operation")
    expected_field = case.get("expected_field")
    if not expected_operation and not expected_field:
        return False, False
    if not plan.steps or plan.tool_names[0] != "query_structured":
        return True, False
    arguments = plan.steps[0].arguments
    return True, arguments.get("operation") == expected_operation and arguments.get("field") == expected_field


def _is_hallucination(case: dict[str, Any], response: dict[str, Any], retrieved_ids: list[str]) -> bool:
    """Classify unsupported claims or unsupported evidence as hallucinations."""
    answer = str(response.get("answer") or "").lower()
    if case.get("unsupported"):
        return bool(retrieved_ids) or not any(phrase in answer for phrase in NO_EVIDENCE_PHRASES)
    has_evidence = bool(retrieved_ids or response.get("structured") or response.get("evidence"))
    return not has_evidence and not any(phrase in answer for phrase in NO_EVIDENCE_PHRASES)


def evaluate_case(conn: sqlite3.Connection, case: dict[str, Any], answer_fn: AnswerFunction | None = None) -> CaseResult:
    """Evaluate one case; only bounded top-k evidence survives this call."""
    started = time.perf_counter()
    plan = plan_question(case["question"])
    response: dict[str, Any] = {}
    error: str | None = None
    owned_answerer = None
    if answer_fn is None:
        owned_answerer = EvaluationAnswerer()
        answer_fn = owned_answerer.answer
    try:
        response = answer_fn(conn, case["question"])
    except Exception as exc:
        error = str(exc)
    finally:
        if owned_answerer is not None:
            owned_answerer.close()
    latency_ms = (time.perf_counter() - started) * 1000
    actual_tools = list(response.get("tool_calls", []))
    if actual_tools and isinstance(actual_tools[0], dict):
        actual_tools = [item.get("name", "") for item in actual_tools]
    expected_tools = list(case["expected_tools"])
    retrieved_ids = [str(ticket_id) for ticket_id in response.get("source_ticket_ids", [])][:5]
    relevant_count, relevant_retrieved_ids = _gold_statistics(conn, case, retrieved_ids)
    structured_applicable, structured_correct = _structured_match(plan, case)
    hallucination = bool(error) or _is_hallucination(case, response, retrieved_ids)
    return CaseResult(
        case_id=case["id"], question=case["question"], case_type=case.get("type", "unknown"),
        expected_tools=expected_tools, actual_tools=actual_tools, planner_correct=plan.tool_names == expected_tools,
        structured_applicable=structured_applicable, structured_correct=structured_correct,
        relevant_ticket_count=relevant_count, relevant_retrieved_ids=relevant_retrieved_ids,
        retrieved_ticket_ids=retrieved_ids,
        recall_at_5=len(relevant_retrieved_ids) / relevant_count if relevant_count else None,
        precision_at_5=precision_at_k(retrieved_ids, relevant_retrieved_ids) if relevant_count else None,
        hallucination=hallucination, grounded=not hallucination, latency_ms=latency_ms, error=error,
    )


def evaluate_dataset(conn: sqlite3.Connection, cases: list[dict[str, Any]], answer_fn: AnswerFunction | None = None) -> dict[str, Any]:
    """Evaluate cases one at a time while retaining only scalar aggregates by default."""
    answerer = None if answer_fn else EvaluationAnswerer()
    effective_answer_fn = answer_fn or answerer.answer
    retrieval_count = structured_count = 0
    recall_sum = precision_sum = planner_sum = structured_sum = grounded_sum = hallucination_sum = latency_sum = 0.0
    try:
        for case in cases:
            result = evaluate_case(conn, case, effective_answer_fn)
            retrieval_count += result.recall_at_5 is not None
            structured_count += result.structured_applicable
            recall_sum += result.recall_at_5 or 0.0
            precision_sum += result.precision_at_5 or 0.0
            planner_sum += result.planner_correct
            structured_sum += result.structured_correct
            grounded_sum += result.grounded
            hallucination_sum += result.hallucination
            latency_sum += result.latency_ms
    finally:
        if answerer is not None:
            answerer.close()
    count = len(cases)
    report = {
        "questions": count,
        "retrieval_cases": retrieval_count,
        "structured_cases": structured_count,
        "recall_at_5": recall_sum / retrieval_count if retrieval_count else 0.0,
        "precision_at_5": precision_sum / retrieval_count if retrieval_count else 0.0,
        "planner_accuracy": planner_sum / count if count else 0.0,
        "structured_query_accuracy": structured_sum / structured_count if structured_count else 0.0,
        "grounded_responses": grounded_sum / count if count else 0.0,
        "hallucination_rate": hallucination_sum / count if count else 0.0,
        "latency_ms": average_latency([latency_sum / count]) if count else 0.0,
    }
    return report
