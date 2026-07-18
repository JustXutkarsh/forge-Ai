import sqlite3
import sys
import time
from pathlib import Path

from forge.config import CHROMA_PATH, OpenAIConfigurationError, require_openai_api_key
from forge.pipeline.clean import retrieval_document
from forge.rag.vectorstore import ChromaStore


def _openai_client():
    require_openai_api_key()
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise OpenAIConfigurationError("OpenAI package is not installed. Install the project dependencies and try again.") from exc
    return OpenAI(timeout=60, max_retries=0)


def _embed_rows(conn: sqlite3.Connection, rows: list[sqlite3.Row], client, store: ChromaStore, model: str, batch_size: int) -> int:
    count = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        docs = [retrieval_document(dict(row)) for row in batch]
        response = None
        for attempt in range(4):
            try:
                response = client.embeddings.create(model=model, input=docs)
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(5 * (attempt + 1))
        store.upsert([row["ticket_id"] for row in batch], docs, [item.embedding for item in response.data], [{"category": row["category"], "product": row["product"], "priority": row["priority"]} for row in batch])
        conn.executemany("UPDATE tickets SET embedding_status='embedded' WHERE ticket_id=?", [(row["ticket_id"],) for row in batch])
        conn.commit()
        count += len(batch)
        print(f"Embedded {count}/{len(rows)} pending tickets", file=sys.stderr, flush=True)
    return count


def embed_pending(db_path: str | Path, model: str = "text-embedding-3-large", batch_size: int = 250) -> int:
    client = _openai_client()
    store = ChromaStore(CHROMA_PATH)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM tickets WHERE embedding_status = 'pending'").fetchall()
    count = _embed_rows(conn, rows, client, store, model, batch_size)
    conn.close()
    return count


def embed_ticket_ids(db_path: str | Path, ticket_ids: list[str], model: str = "text-embedding-3-large", batch_size: int = 250) -> int:
    """Embed only pending tickets selected by the current ingestion run."""
    ids = list(dict.fromkeys(ticket_ids))
    if not ids:
        return 0
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows: list[sqlite3.Row] = []
    for start in range(0, len(ids), 900):
        batch_ids = ids[start:start + 900]
        placeholders = ",".join("?" for _ in batch_ids)
        rows.extend(conn.execute(f"SELECT * FROM tickets WHERE embedding_status = 'pending' AND ticket_id IN ({placeholders})", batch_ids).fetchall())
    if not rows:
        conn.close()
        return 0
    count = _embed_rows(conn, rows, _openai_client(), ChromaStore(CHROMA_PATH), model, batch_size)
    conn.close()
    return count
