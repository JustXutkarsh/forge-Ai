import hashlib
import html
import json
import re
from typing import Any


TICKET_FIELDS = [
    "ticket_id", "customer_name", "customer_email", "product", "category",
    "issue_description", "resolution_notes", "priority", "status", "channel",
    "region", "customer_age", "customer_gender", "subscription_type",
    "customer_tenure_months", "previous_tickets", "customer_satisfaction_score",
    "first_response_time_hours", "resolution_time_hours", "ticket_created_date",
    "ticket_resolved_date", "escalated", "sla_breached", "operating_system",
    "browser", "payment_method", "language", "preferred_contact_time",
    "issue_complexity_score", "customer_segment",
]
RETRIEVAL_FIELDS = ["issue_description", "resolution_notes", "category", "product", "priority"]
INT_FIELDS = {"customer_age", "customer_tenure_months", "previous_tickets", "issue_complexity_score"}
FLOAT_FIELDS = {"customer_satisfaction_score", "first_response_time_hours", "resolution_time_hours"}


def clean_text(value: Any) -> str:
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[`*_>#]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _number(name: str, value: str) -> int | float | None:
    if not value:
        return None
    try:
        return int(float(value)) if name in INT_FIELDS else float(value)
    except ValueError:
        return None


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    result = {field: clean_text(row.get(field, "")) for field in TICKET_FIELDS}
    if not result["ticket_id"]:
        raise ValueError("missing ticket_id")
    for field in INT_FIELDS | FLOAT_FIELDS:
        result[field] = _number(field, result[field])
    return result


def retrieval_document(row: dict[str, Any]) -> str:
    text = "\n".join(f"{field}: {row.get(field, '')}" for field in RETRIEVAL_FIELDS)
    if row.get("customer_name"):
        text = text.replace(str(row["customer_name"]), "[REDACTED_NAME]")
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]", text)
    text = re.sub(r"(?<!\d)(?:\+?\d[\d ()-]{7,}\d)(?!\d)", "[REDACTED_PHONE]", text)
    return text


def hashes(row: dict[str, Any]) -> tuple[str, str]:
    canonical = json.dumps({k: row.get(k) for k in TICKET_FIELDS}, sort_keys=True, separators=(",", ":"), default=str)
    retrieval = json.dumps({k: row.get(k) for k in RETRIEVAL_FIELDS}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest(), hashlib.sha256(retrieval.encode()).hexdigest()
