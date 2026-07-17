import sqlite3
import re
from collections import Counter
from typing import Any

from forge.analytics.queries import query_structured
from forge.rag.retrieve import retrieve
from forge.rag.rerank import rerank


SUPPORTED_QUERY_TERMS = {
    "ticket", "tickets", "support", "issue", "issues", "complaint", "complaints", "customer", "customers",
    "user", "users", "unhappy", "satisfaction", "sla", "login", "payment", "refund", "subscription", "security",
    "performance", "bug", "account", "feature", "data", "sync", "web", "mobile", "portal", "billing", "category",
}
MIN_EVIDENCE_CONFIDENCE = 0.25


def _supports_ticket_domain(query: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    return bool(tokens & SUPPORTED_QUERY_TERMS)


def search_data(conn: sqlite3.Connection, query: str, k: int = 5) -> dict[str, Any]:
    if not _supports_ticket_domain(query):
        return {"query": query, "tickets": [], "source_ticket_ids": [], "confidence": 0.0, "evidence_status": "unsupported_domain"}
    tickets = rerank(query, retrieve(conn, query, max(k, 20)), k)
    distances = [float(ticket.pop("_retrieval_distance")) for ticket in tickets if "_retrieval_distance" in ticket]
    scores = [float(ticket.pop("_score")) for ticket in tickets if "_score" in ticket]
    if distances:
        confidence = max(0.0, min(1.0, 1.0 - min(distances)))
    elif scores:
        confidence = max(0.0, min(1.0, max(scores) / 2.0))
    else:
        confidence = 0.0
    if confidence < MIN_EVIDENCE_CONFIDENCE:
        tickets = []
    return {"query": query, "tickets": tickets, "source_ticket_ids": [ticket["ticket_id"] for ticket in tickets], "confidence": round(confidence, 3), "evidence_status": "supported" if tickets else "insufficient_evidence"}


def summarize(tickets: list[dict]) -> str:
    if not tickets:
        return "No matching tickets found in available data."
    categories = Counter(ticket.get("category", "Unknown") for ticket in tickets)
    resolutions = Counter(ticket.get("resolution_notes", "No resolution recorded") for ticket in tickets)
    priorities = Counter(ticket.get("priority", "Unknown") for ticket in tickets)
    statuses = Counter(ticket.get("status", "Unknown") for ticket in tickets)
    category, category_count = categories.most_common(1)[0]
    resolution, resolution_count = resolutions.most_common(1)[0]
    priority = priorities.most_common(1)[0][0]
    status = statuses.most_common(1)[0][0]
    relevant_issues = Counter(
        str(ticket.get("issue_description", "")).strip()
        for ticket in tickets
        if ticket.get("category") == category and str(ticket.get("issue_description", "")).strip()
    )
    lines = [
        f"Recurring pattern: {category} was the dominant category in {category_count} of {len(tickets)} retrieved tickets.",
        f"Likely resolution: {resolution} ({resolution_count} tickets).",
        f"Important observations: {priority} was the most common priority and {status} was the most common status.",
    ]
    category_terms = {term for term in re.findall(r"[a-z0-9]+", category.lower()) if term != "issue"}
    repeated_issue = next(
        (issue for issue, count in relevant_issues.most_common() if count > 1 and category_terms.intersection(re.findall(r"[a-z0-9]+", issue.lower()))),
        None,
    )
    if repeated_issue:
        lines.append(f"Supporting context: {repeated_issue} (repeated in {relevant_issues[repeated_issue]} tickets).")
    return "\n".join(lines)


def flag_anomaly(conn: sqlite3.Connection, date_range: tuple[str, str] | None = None) -> dict[str, Any]:
    result = query_structured(conn, "group_by", "category", date_range=date_range)
    rows = result["results"]
    return {"anomalies": rows[:1], "basis": "highest ticket volume by category in the selected period"}
