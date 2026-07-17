import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from forge.agent.tools import flag_anomaly, search_data, summarize
from forge.analytics.queries import query_structured


@dataclass(frozen=True)
class PlanStep:
    """One validated tool invocation in an agent plan."""

    tool: str
    arguments: dict[str, Any]
    depends_on: tuple[int, ...] = ()


@dataclass(frozen=True)
class AgentPlan:
    """A deterministic, inspectable plan produced before tool execution."""

    question: str
    steps: tuple[PlanStep, ...]
    rationale: str

    @property
    def tool_names(self) -> list[str]:
        return [step.tool for step in self.steps]

    def as_dict(self) -> dict[str, Any]:
        return {"question": self.question, "steps": [asdict(step) for step in self.steps], "rationale": self.rationale}


TOOL_NAMES = ("search_data", "query_structured", "summarize", "draft_report", "flag_anomaly")
TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "search_data", "description": "Use ONLY for semantic lookup, explanations, and finding related support tickets. Do not use for exact counts or group-by results.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "k": {"type": "integer", "default": 5}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "query_structured", "description": "Use ONLY for exact counts, aggregations, trends, group-bys, and allowlisted filters over SQLite metadata. Never use semantic similarity for these questions.", "parameters": {"type": "object", "properties": {"operation": {"type": "string", "enum": ["count", "group_by", "trend_over_time", "filter"]}, "field": {"type": "string"}, "filters": {"type": ["object", "null"]}, "date_range": {"type": ["array", "null"]}}, "required": ["operation", "field"]}}},
    {"type": "function", "function": {"name": "summarize", "description": "Use ONLY after search_data returns tickets. Summarize only the supplied evidence and do not add facts.", "parameters": {"type": "object", "properties": {"tickets": {"type": "array"}}, "required": ["tickets"]}}},
    {"type": "function", "function": {"name": "draft_report", "description": "Use ONLY after structured analytics and retrieval/summarization have completed. Draft a cited report from those results.", "parameters": {"type": "object", "properties": {"topic": {"type": "string"}, "timeframe": {"type": "string"}}, "required": ["topic", "timeframe"]}}},
    {"type": "function", "function": {"name": "flag_anomaly", "description": "Use ONLY to detect unusual spikes or patterns in a selected period; do not use it for ordinary counts.", "parameters": {"type": "object", "properties": {"date_range": {"type": ["array", "null"]}}}}},
]


_CATEGORY_SYNONYMS = {
    "payment": "Payment Problem",
    "payments": "Payment Problem",
    "login": "Login Issue",
    "logins": "Login Issue",
    "account access": "Login Issue",
    "refund": "Refund Request",
    "refunds": "Refund Request",
    "subscription": "Subscription Cancellation",
    "security": "Security Concern",
    "performance": "Performance Issue",
    "bug": "Bug Report",
    "bugs": "Bug Report",
}


def _category_filter(question: str) -> dict[str, str] | None:
    lowered = question.lower()
    for phrase, category in sorted(_CATEGORY_SYNONYMS.items(), key=lambda item: -len(item[0])):
        if phrase in lowered:
            return {"category": category}
    return None


def _structured_step(question: str) -> PlanStep | None:
    lowered = question.lower()
    filters = _category_filter(question)
    if any(word in lowered for word in ("top", "most common", "breakdown", "distribution")):
        field = "product" if "product" in lowered else "region" if "region" in lowered else "priority" if "priority" in lowered else "category"
        return PlanStep("query_structured", {"operation": "group_by", "field": field, "filters": filters})
    if any(word in lowered for word in ("trend", "over time", "monthly", "by month")):
        return PlanStep("query_structured", {"operation": "trend_over_time", "field": "ticket_created_date", "filters": filters})
    if any(word in lowered for word in ("how many", "count", "number of", "rate", "percentage")):
        return PlanStep("query_structured", {"operation": "count", "field": "ticket_id", "filters": filters})
    return None


def plan_question(question: str) -> AgentPlan:
    """Route a question into a small, testable tool chain without executing tools."""

    lowered = question.lower().strip()
    if any(phrase in lowered for phrase in ("weekly report", "weekly summary", "generate report", "draft report")):
        steps = (
            PlanStep("query_structured", {"operation": "group_by", "field": "category"}),
            PlanStep("search_data", {"query": question, "k": 5}, (0,)),
            PlanStep("summarize", {"source_step": 1}, (1,)),
            PlanStep("draft_report", {"topic": "support tickets", "timeframe": "latest week"}, (0, 2)),
        )
        return AgentPlan(question, steps, "Reports require exact aggregates, supporting ticket evidence, a summary, and then drafting.")

    structured = _structured_step(question)
    if structured is not None:
        return AgentPlan(question, (structured,), "The question requests an exact structured result.")

    if any(word in lowered for word in ("summarize", "summary", "recurring", "themes", "login issues")):
        search_query = _CATEGORY_SYNONYMS.get("login", "Login Issue") if "login" in lowered else question
        steps = (PlanStep("search_data", {"query": search_query, "k": 5}), PlanStep("summarize", {"source_step": 0}, (0,)))
        return AgentPlan(question, steps, "The question asks for a qualitative summary grounded in retrieved tickets.")

    return AgentPlan(question, (PlanStep("search_data", {"query": question, "k": 5}),), "The question requires semantic evidence before an answer can be attempted.")


def _dispatch(conn: sqlite3.Connection, name: str, arguments: dict[str, Any], completed: set[str]) -> Any:
    if name == "search_data":
        return search_data(conn, arguments["query"], int(arguments.get("k", 5)))
    if name == "query_structured":
        date_range = tuple(arguments["date_range"]) if arguments.get("date_range") else None
        return query_structured(conn, arguments["operation"], arguments["field"], arguments.get("filters"), date_range)
    if name == "summarize":
        if "search_data" not in completed:
            return {"error": "summarize requires search_data to run first"}
        return {"summary": summarize(arguments.get("tickets", []))}
    if name == "flag_anomaly":
        date_range = tuple(arguments["date_range"]) if arguments.get("date_range") else None
        return flag_anomaly(conn, date_range)
    if name == "draft_report":
        if not {"query_structured", "search_data", "summarize"}.issubset(completed):
            return {"error": "draft_report requires query_structured, search_data, and summarize first"}
        from forge.agent.executor import weekly_report
        content, date_range = weekly_report(conn)
        return {"date_range": date_range, "report": content}
    raise ValueError(f"unknown tool: {name}")


def run_openai_agent(conn: sqlite3.Connection, question: str) -> dict[str, Any] | None:
    try:
        from openai import OpenAI
    except ImportError:
        return None
    if not os.getenv("OPENAI_API_KEY"):
        return None
    client = OpenAI()
    messages = [
        {"role": "system", "content": "Answer only from tool results. Never expose customer names or emails. Cite ticket IDs or query_structured as sources. If the tools do not provide an answer, say not found in available data."},
        {"role": "user", "content": question},
    ]
    calls = []
    completed: set[str] = set()
    retrieved_ticket_ids: list[str] = []
    ticket_evidence: list[dict[str, Any]] = []
    structured_evidence: list[dict[str, Any]] = []
    token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for _ in range(5):
        response = client.chat.completions.create(model=os.getenv("FORGE_MODEL", "gpt-4o"), temperature=0.1, messages=messages, tools=TOOL_SCHEMAS, tool_choice="auto")
        usage = getattr(response, "usage", None)
        if usage:
            token_usage["prompt_tokens"] += int(getattr(usage, "prompt_tokens", 0) or 0)
            token_usage["completion_tokens"] += int(getattr(usage, "completion_tokens", 0) or 0)
            token_usage["total_tokens"] += int(getattr(usage, "total_tokens", 0) or 0)
        message = response.choices[0].message
        if not message.tool_calls:
            has_structured_evidence = any(item.get("count", 0) or item.get("results") for item in structured_evidence)
            has_evidence = bool(retrieved_ticket_ids) or has_structured_evidence
            answer = message.content or "No supporting evidence found in indexed data."
            if not has_evidence:
                answer = "No supporting evidence found in indexed data."
            return {"answer": answer, "evidence": {"tickets": ticket_evidence, "structured": structured_evidence}, "tool_calls": calls, "sources": [call["name"] for call in calls], "source_ticket_ids": retrieved_ticket_ids, "confidence": 1.0 if has_evidence else 0.0, "token_usage": token_usage}
        messages.append(message.model_dump(exclude_none=True))
        for tool_call in message.tool_calls:
            arguments = json.loads(tool_call.function.arguments or "{}")
            result = _dispatch(conn, tool_call.function.name, arguments, completed)
            calls.append({"name": tool_call.function.name, "arguments": arguments})
            completed.add(tool_call.function.name)
            if isinstance(result, dict):
                retrieved_ticket_ids.extend(result.get("source_ticket_ids", []))
                ticket_evidence.extend(result.get("tickets", []))
                if result.get("operation"):
                    structured_evidence.append(result)
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(result, default=str)})
    return {"answer": "The agent exceeded its tool-call limit.", "evidence": {"tickets": ticket_evidence, "structured": structured_evidence}, "tool_calls": calls, "sources": [call["name"] for call in calls], "source_ticket_ids": retrieved_ticket_ids, "confidence": 1.0 if retrieved_ticket_ids or structured_evidence else 0.0, "token_usage": token_usage}
