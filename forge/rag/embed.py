import sqlite3
import sys
import time
from pathlib import Path

from forge.config import CHROMA_PATH
from forge.pipeline.clean import retrieval_document
from forge.rag.embedding import get_embedding_service
from forge.rag.vectorstore import ChromaStore


def _openai_client():
    """Compatibility shim for older tests; production embeddings are local."""
    return get_embedding_service()


def _embed_rows(conn: sqlite3.Connection, rows: list[sqlite3.Row], client, store: ChromaStore, model: str, batch_size: int) -> int:
    count = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        docs = [retrieval_document(dict(row)) for row in batch]
        if hasattr(client, "embed_documents"):
            embeddings = client.embed_documents(docs, batch_size=min(batch_size, 32))
        else:
            response = None
            for attempt in range(4):
                try:
                    response = client.embeddings.create(model=model, input=docs)
                    break
                except Exception:
                    if attempt == 3:
                        raise
                    time.sleep(5 * (attempt + 1))
            embeddings = [item.embedding for item in response.data]
        store.upsert([row["ticket_id"] for row in batch], docs, embeddings, [{"category": row["category"], "product": row["product"], "priority": row["priority"]} for row in batch])
        conn.executemany("UPDATE tickets SET embedding_status='embedded' WHERE ticket_id=?", [(row["ticket_id"],) for row in batch])
        conn.commit()
        count += len(batch)
        print(f"Embedded {count}/{len(rows)} pending tickets", file=sys.stderr, flush=True)
    return count


def embed_pending(db_path: str | Path, model: str = "local", batch_size: int = 250, chroma_path: str | Path | None = None) -> int:
    client = _openai_client()
    store = ChromaStore(chroma_path or CHROMA_PATH)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM tickets WHERE embedding_status = 'pending'").fetchall()
    count = _embed_rows(conn, rows, client, store, model, batch_size)
    conn.close()
    return count


def embed_ticket_ids(db_path: str | Path, ticket_ids: list[str], model: str = "local", batch_size: int = 250, chroma_path: str | Path | None = None) -> int:
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
    count = _embed_rows(conn, rows, _openai_client(), ChromaStore(chroma_path or CHROMA_PATH), model, batch_size)
    conn.close()
    return count
