import json
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from forge.agent.tools import search_data, summarize
from forge.agent.planner import AgentPlan, plan_question
from forge.analytics.queries import query_structured
from forge.config import OUTPUTS, require_openai_api_key


def _log_agent_run(question: str, output: dict[str, Any], started: float) -> None:
    OUTPUTS.joinpath("logs").mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat() + "_agent.jsonl"
    calls = output.get("tool_calls", [])
    sequence = [call.get("name") if isinstance(call, dict) else call for call in calls]
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "selected_tools": sequence,
        "tool_sequence": sequence,
        "retrieved_ticket_ids": output.get("source_ticket_ids", []),
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "token_usage": output.get("token_usage", {}),
        "final_answer": output.get("answer", ""),
        "plan": output.get("plan"),
    }
    with (OUTPUTS / "logs" / stamp).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, default=str) + "\n")


def ask(conn: sqlite3.Connection, query: str) -> dict[str, Any]:
    started = time.perf_counter()
    require_openai_api_key()
    try:
        from forge.agent.planner import run_openai_agent
        model_output = run_openai_agent(conn, query)
    except Exception:
        model_output = None
    if model_output is not None:
        _log_agent_run(query, model_output, started)
        return model_output
    plan = plan_question(query)
    output = _execute_plan(conn, plan)
    _log_agent_run(query, output, started)
    return output


def _execute_plan(conn: sqlite3.Connection, plan: AgentPlan) -> dict[str, Any]:
    """Execute a deterministic plan while preserving intermediate tool results."""

    results: dict[int, dict[str, Any]] = {}
    retrieved: list[dict[str, Any]] = []
    retrieval_confidence = 0.0
    tool_calls: list[str] = []
    for index, step in enumerate(plan.steps):
        tool_calls.append(step.tool)
        if step.tool == "query_structured":
            args = step.arguments
            results[index] = query_structured(conn, args["operation"], args["field"], args.get("filters"), args.get("date_range"))
        elif step.tool == "search_data":
            result = search_data(conn, step.arguments["query"], step.arguments.get("k", 5))
            results[index] = result
            retrieved.extend(result.get("tickets", []))
            retrieval_confidence = max(retrieval_confidence, float(result.get("confidence", 0.0)))
        elif step.tool == "summarize":
            source = results[step.arguments["source_step"]]
            results[index] = {"summary": summarize(source.get("tickets", []))}
        elif step.tool == "draft_report":
            content, dates = weekly_report(conn)
            results[index] = {"report": content, "date_range": dates}
        else:
            raise ValueError(f"unsupported offline plan tool: {step.tool}")

    final = results[len(plan.steps) - 1] if plan.steps else {}
    if plan.steps and plan.steps[-1].tool == "draft_report":
        answer = final["report"]
    elif plan.steps and plan.steps[0].tool == "query_structured":
        structured = final if plan.steps[-1].tool == "query_structured" else results[0]
        if structured.get("operation") == "count":
            answer = f"Count: {structured['count']}."
        else:
            answer = "\n".join(f"{row.get('value', row.get('period'))}: {row['count']}" for row in structured.get("results", [])[:10])
    elif plan.steps and plan.steps[-1].tool == "summarize":
        answer = final["summary"] if retrieved else "No supporting evidence found in indexed data."
    else:
        answer = summarize(retrieved) if retrieved else "No supporting evidence found in indexed data."
    source_ids = [ticket["ticket_id"] for ticket in retrieved]
    structured_evidence = results.get(0) if plan.steps and plan.steps[0].tool == "query_structured" else None
    return {"answer": answer, "evidence": retrieved or structured_evidence, "source_ticket_ids": source_ids, "sources": source_ids or (["query_structured"] if structured_evidence else []), "confidence": retrieval_confidence, "tool_calls": tool_calls, "plan": plan.as_dict(), "tickets": retrieved, "structured": structured_evidence}


def latest_date_range(conn: sqlite3.Connection) -> tuple[str, str]:
    row = conn.execute("SELECT MAX(ticket_created_date) AS latest FROM tickets").fetchone()
    if not row or not row[0]:
        raise ValueError("no ticket dates available")
    end = date.fromisoformat(row[0])
    return (str(end - timedelta(days=6)), str(end))


def weekly_report(conn: sqlite3.Connection, start: str | None = None, end: str | None = None) -> tuple[str, tuple[str, str]]:
    date_range = (start, end) if start and end else latest_date_range(conn)
    totals = query_structured(conn, "count", "ticket_id", date_range=date_range)
    categories = query_structured(conn, "group_by", "category", date_range=date_range)
    priorities = query_structured(conn, "group_by", "priority", date_range=date_range)
    sla = query_structured(conn, "group_by", "sla_breached", date_range=date_range)
    lines = [f"# Support Ticket Summary: {date_range[0]} to {date_range[1]}", "", f"Tickets in period: {totals['count']}", "", "## Top categories"]
    lines.extend(f"- {row['value']}: {row['count']}" for row in categories["results"][:5])
    lines += ["", "## Priority distribution"]
    lines.extend(f"- {row['value']}: {row['count']}" for row in priorities["results"])
    lines += ["", "## SLA breach distribution"]
    lines.extend(f"- {row['value']}: {row['count']}" for row in sla["results"])
    lines += ["", "Generated from structured ticket metadata. Customer names and emails are excluded."]
    return "\n".join(lines), date_range
