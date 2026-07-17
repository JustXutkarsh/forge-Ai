import csv
import json
from collections import Counter
from pathlib import Path

from forge.pipeline.clean import TICKET_FIELDS


def profile_csv(source: str | Path) -> dict:
    rows = 0
    ids: set[str] = set()
    unique_text = {"issue_description": set(), "resolution_notes": set()}
    missing = Counter()
    dates: list[str] = []
    with open(source, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows += 1
            ids.add(row.get("ticket_id", ""))
            for field in TICKET_FIELDS:
                if not str(row.get(field, "")).strip():
                    missing[field] += 1
            for field in unique_text:
                unique_text[field].add(row.get(field, ""))
            if row.get("ticket_created_date"):
                dates.append(row["ticket_created_date"])
    return {
        "rows": rows,
        "columns": len(TICKET_FIELDS),
        "duplicate_ticket_ids": rows - len(ids),
        "missing_values": dict(missing),
        "unique_text_values": {k: len(v) for k, v in unique_text.items()},
        "date_range": [min(dates), max(dates)] if dates else [],
        "pii_fields": ["customer_name", "customer_email"],
    }


def write_profile(source: str | Path, output: str | Path) -> dict:
    result = profile_csv(source)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
