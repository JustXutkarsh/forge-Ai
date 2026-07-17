import sqlite3
import sys
import time
from pathlib import Path

from forge.config import CHROMA_PATH
from forge.pipeline.clean import retrieval_document
from forge.rag.vectorstore import ChromaStore


def embed_pending(db_path: str | Path, model: str = "text-embedding-3-large", batch_size: int = 250) -> int:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("OpenAI embeddings require the openai package and OPENAI_API_KEY") from exc
    client = OpenAI(timeout=60, max_retries=0)
    store = ChromaStore(CHROMA_PATH)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM tickets WHERE embedding_status = 'pending'").fetchall()
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
    conn.close()
    return count
