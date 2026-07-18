import sqlite3

from forge.pipeline.clean import TICKET_FIELDS


TICKET_TYPES = {
    "ticket_id": "TEXT PRIMARY KEY", "customer_name": "TEXT", "customer_email": "TEXT",
    "product": "TEXT", "category": "TEXT", "issue_description": "TEXT",
    "resolution_notes": "TEXT", "priority": "TEXT", "status": "TEXT", "channel": "TEXT",
    "region": "TEXT", "customer_age": "INTEGER", "customer_gender": "TEXT",
    "subscription_type": "TEXT", "customer_tenure_months": "INTEGER", "previous_tickets": "INTEGER",
    "customer_satisfaction_score": "REAL", "first_response_time_hours": "REAL",
    "resolution_time_hours": "REAL", "ticket_created_date": "TEXT", "updated_date": "TEXT", "ticket_resolved_date": "TEXT",
    "escalated": "TEXT", "sla_breached": "TEXT", "operating_system": "TEXT", "browser": "TEXT",
    "payment_method": "TEXT", "language": "TEXT", "preferred_contact_time": "TEXT",
    "issue_complexity_score": "INTEGER", "customer_segment": "TEXT",
}


def init_db(conn: sqlite3.Connection) -> None:
    columns = ",\n".join(f"{name} {TICKET_TYPES[name]}" for name in TICKET_FIELDS)
    conn.executescript(f"""
    CREATE TABLE IF NOT EXISTS tickets (
        {columns},
        record_hash TEXT NOT NULL,
        retrieval_hash TEXT NOT NULL,
        embedding_status TEXT NOT NULL DEFAULT 'pending',
        ingested_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS ingest_runs (
        run_id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT NOT NULL,
        loaded INTEGER NOT NULL, new_count INTEGER NOT NULL, changed_count INTEGER NOT NULL,
        skipped_count INTEGER NOT NULL, embedding_candidates INTEGER NOT NULL, error_count INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_tickets_created ON tickets(ticket_created_date);
    CREATE INDEX IF NOT EXISTS idx_tickets_category ON tickets(category);
    CREATE INDEX IF NOT EXISTS idx_tickets_retrieval_hash ON tickets(retrieval_hash);
    """)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(tickets)")}
    if "updated_date" not in columns:
        conn.execute("ALTER TABLE tickets ADD COLUMN updated_date TEXT NOT NULL DEFAULT ''")
    conn.commit()
