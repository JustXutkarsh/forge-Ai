import json
import os
import re
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from forge.agent.tools import flag_anomaly, search_data, summarize
from forge.analytics.queries import query_structured
from forge.profiling import stage


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
    mode: str = "standard"
    topics: tuple[str, ...] = ()

    @property
    def tool_names(self) -> list[str]:
        return [step.tool for step in self.steps]

    def as_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "steps": [asdict(step) for step in self.steps],
            "rationale": self.rationale,
            "mode": self.mode,
            "topics": list(self.topics),
        }


TOOL_NAMES = ("search_data", "query_structured", "summarize", "draft_report", "flag_anomaly")
TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "search_data", "description": "Use ONLY for semantic lookup, explanations, and finding related support tickets. Do not use for exact counts or group-by results.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "k": {"type": "integer", "default": 5}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "query_structured", "description": "Use ONLY for exact counts, aggregations, trends, group-bys, and allowlisted filters over SQLite metadata. Never use semantic similarity for these questions. Use limit for explicit top-N requests.", "parameters": {"type": "object", "properties": {"operation": {"type": "string", "enum": ["count", "group_by", "trend_over_time", "filter"]}, "field": {"type": "string"}, "filters": {"type": ["object", "null"]}, "date_range": {"type": ["array", "null"]}, "limit": {"type": ["integer", "null"]}}, "required": ["operation", "field"]}}},
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

_TOP_METADATA_TERMS = (
    "label", "labels", "category", "categories", "priority", "priorities",
    "product", "products", "region", "regions", "channel", "channels",
    "status", "statuses", "distribution", "breakdown",
)
_TOP_ISSUE_TERMS = (
    "issue", "issues", "problem", "problems", "bug", "bugs", "failure",
    "failures", "crash", "crashes", "authentication", "login", "sign in",
    "signin", "credential", "credentials", "payment", "billing", "refund",
    "performance", "slow", "lag", "freeze", "recurring",
)
_COMPARISON_MARKERS = ("compare", "versus", " vs ", "difference between", "against")
_EVIDENCE_EXPLANATION_MARKERS = (
    "why was this evidence",
    "why were these tickets",
    "why were the tickets",
    "why did you select",
    "explain the evidence",
    "why is this evidence",
)
_COMPOSITE_CONNECTORS = ("because", "due to", "caused by", "as a result of")


def _category_filter(question: str) -> dict[str, str] | None:
    lowered = question.lower()
    for phrase, category in sorted(_CATEGORY_SYNONYMS.items(), key=lambda item: -len(item[0])):
        if phrase in lowered:
            return {"category": category}
    return None


def _comparison_topics(question: str) -> tuple[str, ...]:
    """Extract two independently searchable topics from a comparison question."""
    lowered = question.lower().strip()
    if not any(marker in lowered for marker in _COMPARISON_MARKERS):
        return ()
    cleaned = re.sub(r"^\s*(?:compare|comparison of|difference between)\s+", "", lowered)
    cleaned = re.sub(r"\b(?:versus|vs\.?|against)\b", "and", cleaned)
    parts = [part.strip(" .,?") for part in re.split(r"\s+(?:and|&)\s+|,\s*", cleaned)]
    parts = [part for part in parts if part and any(term in part for term in _TOP_ISSUE_TERMS)]
    if len(parts) >= 2:
        return tuple(parts[:4])
    return ()


def _evidence_context(question: str) -> str | None:
    """Find a topic that can anchor an evidence-selection explanation."""
    lowered = question.lower()
    matches = [phrase for phrase in sorted(_CATEGORY_SYNONYMS, key=len, reverse=True) if phrase in lowered]
    if matches:
        return " ".join(dict.fromkeys(matches))
    matches = [term for term in _TOP_ISSUE_TERMS if term in lowered]
    return " ".join(dict.fromkeys(matches)) or None


def _is_evidence_explanation(question: str) -> bool:
    """Recognize follow-up requests that explain already retrieved evidence."""
    lowered = question.lower()
    return any(marker in lowered for marker in _EVIDENCE_EXPLANATION_MARKERS) or (
        "explain" in lowered and ("selected" in lowered or "ticket id" in lowered)
    )


def _composite_conditions(question: str) -> tuple[str, ...]:
    """Return the primary and causal conditions in a multi-condition claim."""
    lowered = question.lower().strip()
    if not any(marker in lowered for marker in _COMPOSITE_CONNECTORS):
        return ()
    if not any(term in lowered for term in ("how many", "count", "number of", "percentage", "rate")):
        return ()
    match = re.search(r"\b(?:because|due to|caused by|as a result of)\b", lowered)
    if not match:
        return ()
    primary = re.sub(r"\b(?:how many|number of|count of|percentage of|rate of)\b", "", lowered[:match.start()]).strip()
    secondary = lowered[match.end():].strip(" .?")
    return (primary, secondary) if primary and secondary else ()


def _special_plan(question: str) -> AgentPlan | None:
    """Build deterministic plans for intents requiring complete grounding."""
    lowered = question.lower().strip()
    if _is_evidence_explanation(question):
        context = _evidence_context(question)
        steps = (PlanStep("search_data", {"query": context, "k": 5}),) if context else ()
        return AgentPlan(
            question,
            steps,
            "Evidence explanations require an explicit investigation topic and per-ticket retrieval reasons.",
            "evidence_explanation",
            (context,) if context else (),
        )
    topics = _comparison_topics(question)
    if topics:
        steps: list[PlanStep] = []
        for topic in topics:
            search_index = len(steps)
            steps.append(PlanStep("search_data", {"query": topic, "k": 5}))
            steps.append(PlanStep("summarize", {"source_step": search_index}, (search_index,)))
        return AgentPlan(
            question,
            tuple(steps),
            "Comparison questions require independent retrieval and summaries for each requested topic.",
            "comparison",
            topics,
        )
    conditions = _composite_conditions(question)
    if conditions:
        return AgentPlan(
            question,
            (PlanStep("search_data", {"query": question, "k": 20}),),
            "Composite claims require every factual condition to be supported before reporting a count.",
            "composite_claim",
            conditions,
        )
    return None


def _structured_step(question: str) -> PlanStep | None:
    lowered = question.lower()
    filters = _category_filter(question)
    top_match = re.search(r"\btop\s+(\d+)\b", lowered)
    limit = int(top_match.group(1)) if top_match else None
    top_request = any(word in lowered for word in ("top", "most common", "breakdown", "distribution"))
    metadata_top_request = any(term in lowered for term in _TOP_METADATA_TERMS)
    issue_top_request = any(term in lowered for term in _TOP_ISSUE_TERMS)
    if top_request and metadata_top_request and not issue_top_request:
        field = "product" if "product" in lowered else "region" if "region" in lowered else "priority" if "priority" in lowered else "category"
        arguments = {"operation": "group_by", "field": field, "filters": filters}
        if limit is not None:
            arguments["limit"] = limit
        return PlanStep("query_structured", arguments)
    if any(word in lowered for word in ("trend", "over time", "monthly", "by month")):
        return PlanStep("query_structured", {"operation": "trend_over_time", "field": "ticket_created_date", "filters": filters})
    if any(word in lowered for word in ("how many", "count", "number of", "rate", "percentage")):
        return PlanStep("query_structured", {"operation": "count", "field": "ticket_id", "filters": filters})
    return None


def plan_question(question: str) -> AgentPlan:
    """Route a question into a small, testable tool chain without executing tools."""

    lowered = question.lower().strip()
    special = _special_plan(question)
    if special is not None:
        return special
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
        return query_structured(conn, arguments["operation"], arguments["field"], arguments.get("filters"), date_range, arguments.get("limit"))
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
    with stage("OpenAI initialization"):
        client = OpenAI(timeout=10, max_retries=0)
    messages = [
        {"role": "system", "content": "Answer only from tool results. Never expose customer names or emails. Cite ticket IDs or query_structured as sources. If the tools do not provide an answer, say not found in available data."},
        {"role": "user", "content": question},
    ]
    calls = []
    completed: set[str] = set()
    retrieved_ticket_ids: list[str] = []
    ticket_evidence: list[dict[str, Any]] = []
    structured_evidence: list[dict[str, Any]] = []
    evidence_confidence = 0.0
    token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for _ in range(5):
        with stage("OpenAI request"):
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
            return {"answer": answer, "evidence": {"tickets": ticket_evidence, "structured": structured_evidence}, "tool_calls": calls, "sources": [call["name"] for call in calls], "source_ticket_ids": retrieved_ticket_ids, "confidence": evidence_confidence if has_evidence else 0.0, "token_usage": token_usage}
        messages.append(message.model_dump(exclude_none=True))
        for tool_call in message.tool_calls:
            arguments = json.loads(tool_call.function.arguments or "{}")
            result = _dispatch(conn, tool_call.function.name, arguments, completed)
            calls.append({"name": tool_call.function.name, "arguments": arguments})
            completed.add(tool_call.function.name)
            if isinstance(result, dict):
                evidence_confidence = max(evidence_confidence, float(result.get("confidence", 0.0)))
                retrieved_ticket_ids.extend(result.get("source_ticket_ids", []))
                ticket_evidence.extend(result.get("tickets", []))
                if result.get("operation"):
                    evidence_confidence = max(evidence_confidence, 1.0 if result["operation"] == "filter" else 0.95)
                    structured_evidence.append(result)
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(result, default=str)})
    return {"answer": "The agent exceeded its tool-call limit.", "evidence": {"tickets": ticket_evidence, "structured": structured_evidence}, "tool_calls": calls, "sources": [call["name"] for call in calls], "source_ticket_ids": retrieved_ticket_ids, "confidence": evidence_confidence if retrieved_ticket_ids or structured_evidence else 0.0, "token_usage": token_usage}
