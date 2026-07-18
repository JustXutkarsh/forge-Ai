import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from forge.analytics.schema import init_db
from forge.config import OUTPUTS
from forge.pipeline.clean import TICKET_FIELDS, hashes, normalize_row


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ingest_rows(rows: Iterable[tuple[int, dict[str, Any]]], source: str, db_path: str | Path) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    started = _now()
    stats = {"source": source, "loaded": 0, "new": 0, "changed": 0, "skipped": 0, "embedding_candidates": 0, "embedding_ticket_ids": [], "errors": 0}
    error_rows: list[dict[str, Any]] = []
    placeholders = ",".join("?" for _ in TICKET_FIELDS)
    update_fields = ",".join(f"{field} = excluded.{field}" for field in TICKET_FIELDS if field != "ticket_id")
    sql = f"""INSERT INTO tickets ({','.join(TICKET_FIELDS)},record_hash,retrieval_hash,embedding_status,ingested_at)
              VALUES ({placeholders},?,?,?,?)
              ON CONFLICT(ticket_id) DO UPDATE SET {update_fields}, record_hash=excluded.record_hash,
              retrieval_hash=excluded.retrieval_hash, embedding_status=excluded.embedding_status, ingested_at=excluded.ingested_at"""
    for line_number, raw in rows:
        try:
            row = normalize_row(raw)
            record_hash, retrieval_hash = hashes(row)
            old = conn.execute("SELECT record_hash,retrieval_hash,embedding_status FROM tickets WHERE ticket_id = ?", (row["ticket_id"],)).fetchone()
            stats["loaded"] += 1
            if old is None:
                stats["new"] += 1
                stats["embedding_candidates"] += 1
                stats["embedding_ticket_ids"].append(row["ticket_id"])
                embedding_status = "pending"
            elif old["record_hash"] == record_hash:
                stats["skipped"] += 1
                continue
            else:
                stats["changed"] += 1
                if old["retrieval_hash"] != retrieval_hash:
                    stats["embedding_candidates"] += 1
                    stats["embedding_ticket_ids"].append(row["ticket_id"])
                    embedding_status = "pending"
                else:
                    embedding_status = old["embedding_status"]
            values = [row[field] for field in TICKET_FIELDS] + [record_hash, retrieval_hash, embedding_status, _now()]
            conn.execute(sql, values)
        except Exception as exc:
            stats["errors"] += 1
            if len(error_rows) < 100:
                error_rows.append({"line": line_number, "error": str(exc)})
    finished = _now()
    conn.execute("INSERT INTO ingest_runs(source,started_at,finished_at,loaded,new_count,changed_count,skipped_count,embedding_candidates,error_count) VALUES (?,?,?,?,?,?,?,?,?)", (source, started, finished, stats["loaded"], stats["new"], stats["changed"], stats["skipped"], stats["embedding_candidates"], stats["errors"]))
    conn.commit()
    conn.close()
    stats["embedding_ticket_ids"] = list(dict.fromkeys(stats["embedding_ticket_ids"]))
    OUTPUTS.joinpath("logs").mkdir(parents=True, exist_ok=True)
    log_path = OUTPUTS / "logs" / f"ingest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    log_stats = {key: value for key, value in stats.items() if key != "embedding_ticket_ids"}
    log_path.write_text(json.dumps({**log_stats, "started_at": started, "finished_at": finished, "sample_errors": error_rows}, indent=2), encoding="utf-8")
    return stats


def ingest_csv(source: str | Path, db_path: str | Path) -> dict[str, Any]:
    source = str(source)
    with open(source, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = (set(TICKET_FIELDS) - {"updated_date"}) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV is missing required columns: {sorted(missing)}")
        return _ingest_rows(enumerate(reader, start=2), source, db_path)


def ingest_records(records: Iterable[dict[str, Any]], source: str, db_path: str | Path) -> dict[str, Any]:
    return _ingest_rows(enumerate(records, start=1), source, db_path)
