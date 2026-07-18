import sqlite3
import re
from collections import Counter
from typing import Any

from forge.analytics.queries import query_structured
from forge.rag.retrieve import retrieve
from forge.rag.rerank import rerank
from forge.search.query_normalizer import expand_query


SUPPORTED_QUERY_TERMS = {
    "ticket", "tickets", "support", "issue", "issues", "complaint", "complaints", "customer", "customers",
    "user", "users", "unhappy", "satisfaction", "sla", "login", "payment", "refund", "subscription", "security",
    "performance", "bug", "account", "feature", "data", "sync", "web", "mobile", "portal", "billing", "category",
}
MIN_EVIDENCE_CONFIDENCE = 0.25


def _supports_ticket_domain(query: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    return bool(tokens & SUPPORTED_QUERY_TERMS)


def _calibrate_confidence(raw_confidence: float) -> float:
    """Map a supported retrieval score into weak or strong evidence bands."""
    return round(0.4 + (0.6 * max(0.0, min(1.0, raw_confidence))), 3)


def search_data(conn: sqlite3.Connection, query: str, k: int = 5) -> dict[str, Any]:
    retrieval_query = expand_query(query)
    if not _supports_ticket_domain(retrieval_query):
        return {"query": query, "tickets": [], "source_ticket_ids": [], "confidence": 0.0, "evidence_status": "unsupported_domain"}
    tickets = rerank(retrieval_query, retrieve(conn, retrieval_query, max(k, 20)), k)
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
        confidence = 0.0
    elif tickets:
        confidence = _calibrate_confidence(confidence)
    return {"query": query, "tickets": tickets, "source_ticket_ids": [ticket["ticket_id"] for ticket in tickets], "confidence": confidence, "evidence_status": "supported" if tickets else "insufficient_evidence"}


def summarize(tickets: list[dict]) -> str:
    if not tickets:
        return "No matching tickets found in available data."
    classified = [(_evidence_category(ticket), ticket) for ticket in tickets]
    categories = Counter(category for category, _ in classified)
    resolutions = Counter(ticket.get("resolution_notes", "No resolution recorded") for ticket in tickets)
    priorities = Counter(ticket.get("priority", "Unknown") for ticket in tickets)
    statuses = Counter(ticket.get("status", "Unknown") for ticket in tickets)
    top_count = max(categories.values())
    top_categories = sorted(category for category, count in categories.items() if count == top_count)
    category = top_categories[0]
    resolution, resolution_count = resolutions.most_common(1)[0]
    priority = priorities.most_common(1)[0][0]
    status = statuses.most_common(1)[0][0]
    relevant_issues = Counter(
        str(ticket.get("issue_description", "")).strip()
        for classified_category, ticket in classified
        if classified_category in top_categories and str(ticket.get("issue_description", "")).strip()
    )
    category_line = (
        f"Recurring pattern: {category} was the dominant category in {top_count} of {len(tickets)} retrieved tickets."
        if len(top_categories) == 1
        else f"Recurring patterns: {' and '.join(top_categories)} were tied at {top_count} of {len(tickets)} retrieved tickets."
    )
    lines = [
        category_line,
        f"Likely resolution: {resolution} ({resolution_count} tickets).",
        f"Important observations: {priority} was the most common priority and {status} was the most common status.",
    ]
    category_terms = {term for term in re.findall(r"[a-z0-9]+", " ".join(top_categories).lower()) if term != "issue"}
    repeated_issue = next(
        (issue for issue, count in relevant_issues.most_common() if count > 1 and category_terms.intersection(re.findall(r"[a-z0-9]+", issue.lower()))),
        None,
    )
    if repeated_issue:
        lines.append(f"Supporting context: {repeated_issue} (repeated in {relevant_issues[repeated_issue]} tickets).")
    return "\n".join(lines)


_CATEGORY_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Login Issue", ("login", "log in", "logging in", "sign in", "signin", "authentication", "credential", "password", "account access")),
    ("Payment Problem", ("payment", "billing", "refund")),
    ("Subscription Cancellation", ("subscription", "cancel", "cancellation")),
    ("Security Concern", ("security", "unauthorized", "hacked", "fraud")),
    ("Performance Issue", ("performance", "slow", "lag", "freeze", "freezing")),
    ("Bug Report", ("bug", "error", "failure", "crash", "broken")),
    ("Feature Request", ("feature request", "would like", "add support", "enhancement")),
)


def _evidence_category(ticket: dict) -> str:
    """Prefer category signals in ticket text over a noisy metadata label."""
    metadata_category = str(ticket.get("category") or "Unknown").strip() or "Unknown"
    text = " ".join(str(ticket.get(field) or "") for field in ("issue_description", "resolution_notes")).lower()
    scores = {
        category: sum(text.count(term) for term in terms)
        for category, terms in _CATEGORY_HINTS
    }
    best_score = max(scores.values(), default=0)
    if best_score <= 0:
        return metadata_category
    winners = sorted(category for category, score in scores.items() if score == best_score)
    return metadata_category if metadata_category in winners else winners[0]


def flag_anomaly(conn: sqlite3.Connection, date_range: tuple[str, str] | None = None) -> dict[str, Any]:
    result = query_structured(conn, "group_by", "category", date_range=date_range)
    rows = result["results"]
    return {"anomalies": rows[:1], "basis": "highest ticket volume by category in the selected period"}
