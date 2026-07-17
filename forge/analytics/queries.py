import sqlite3
from typing import Any, Literal


Operation = Literal["count", "group_by", "trend_over_time", "filter"]
ALLOWED_OPERATIONS = {"count", "group_by", "trend_over_time", "filter"}
ALLOWED_FIELDS = {
    "ticket_id", "product", "category", "priority", "status", "channel", "region",
    "customer_age", "customer_gender", "subscription_type", "customer_tenure_months",
    "previous_tickets", "customer_satisfaction_score", "first_response_time_hours",
    "resolution_time_hours", "ticket_created_date", "ticket_resolved_date", "escalated",
    "sla_breached", "operating_system", "browser", "payment_method", "language",
    "preferred_contact_time", "issue_complexity_score", "customer_segment",
}
SAFE_RESULT_FIELDS = ["ticket_id", "product", "category", "priority", "status", "channel", "region", "ticket_created_date", "issue_description", "resolution_notes"]


class StructuredQueryError(ValueError):
    pass


def _validate(operation: str, field: str, filters: dict[str, str] | None) -> None:
    if operation not in ALLOWED_OPERATIONS:
        raise StructuredQueryError(f"unsupported operation: {operation}")
    if field not in ALLOWED_FIELDS:
        raise StructuredQueryError(f"field is not allowlisted: {field}")
    if filters:
        invalid = set(filters) - ALLOWED_FIELDS
        if invalid:
            raise StructuredQueryError(f"filter field is not allowlisted: {sorted(invalid)[0]}")


def query_structured(
    conn: sqlite3.Connection,
    operation: Operation,
    field: str,
    filters: dict[str, str] | None = None,
    date_range: tuple[str, str] | None = None,
) -> dict[str, Any]:
    _validate(operation, field, filters)
    # Identifiers come only from the allowlist; values are always bound parameters.
    identifier = field
    where, params = [], []
    for key, value in (filters or {}).items():
        where.append(f"{key} = ?")
        params.append(value)
    if date_range:
        where.append("ticket_created_date BETWEEN ? AND ?")
        params.extend(date_range)
    clause = f" WHERE {' AND '.join(where)}" if where else ""

    if operation == "count":
        row = conn.execute(f"SELECT COUNT(*) AS count FROM tickets{clause}", params).fetchone()
        return {"operation": operation, "field": field, "count": row[0]}
    if operation == "group_by":
        rows = conn.execute(f"SELECT {identifier} AS value, COUNT(*) AS count FROM tickets{clause} GROUP BY {identifier} ORDER BY count DESC, value LIMIT 100", params).fetchall()
        return {"operation": operation, "field": field, "results": [dict(r) for r in rows]}
    if operation == "trend_over_time":
        rows = conn.execute(f"SELECT substr(ticket_created_date, 1, 7) AS period, COUNT(*) AS count FROM tickets{clause} GROUP BY period ORDER BY period", params).fetchall()
        return {"operation": operation, "field": field, "results": [dict(r) for r in rows]}
    columns = ", ".join(SAFE_RESULT_FIELDS)
    rows = conn.execute(f"SELECT {columns} FROM tickets{clause} ORDER BY ticket_created_date DESC LIMIT 100", params).fetchall()
    return {"operation": operation, "field": field, "results": [dict(r) for r in rows]}
