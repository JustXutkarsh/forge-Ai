import re
import sqlite3
import os

from forge.config import CHROMA_PATH
from forge.rag.vectorstore import ChromaStore
from forge.search.query_normalizer import expand_query


PUBLIC_FIELDS = ["ticket_id", "product", "category", "priority", "status", "channel", "region", "ticket_created_date", "issue_description", "resolution_notes"]
STOPWORDS = {"a", "an", "are", "be", "by", "did", "for", "how", "in", "is", "many", "of", "occurred", "please", "the", "to", "was", "what", "when", "where", "who", "why", "with", "user", "users"}


def retrieve(conn: sqlite3.Connection, query: str, k: int = 5) -> list[dict]:
    retrieval_query = expand_query(query)
    semantic = _semantic_retrieve(conn, retrieval_query, k)
    if semantic is not None:
        return semantic
    tokens = [t for t in re.findall(r"[a-z0-9]+", retrieval_query.lower()) if len(t) > 2 and t not in STOPWORDS][:8]
    columns = ", ".join(PUBLIC_FIELDS)
    if not tokens:
        rows = conn.execute(f"SELECT {columns} FROM tickets ORDER BY ticket_created_date DESC LIMIT ?", (k,)).fetchall()
    else:
        conditions = []
        params = []
        for token in tokens:
            like = f"%{token}%"
            conditions.append("(issue_description LIKE ? OR resolution_notes LIKE ? OR category LIKE ? OR product LIKE ? OR priority LIKE ?)")
            params.extend([like] * 5)
        rows = conn.execute(f"SELECT {columns} FROM tickets WHERE {' OR '.join(conditions)} LIMIT 500", params).fetchall()
    result = [dict(row) for row in rows]
    token_set = set(tokens)
    for item in result:
        text = " ".join(str(item.get(k, "")) for k in PUBLIC_FIELDS).lower()
        item["_score"] = sum(text.count(token) for token in token_set)
    return sorted(result, key=lambda item: item.get("_score", 0), reverse=True)[:k]


def _semantic_retrieve(conn: sqlite3.Connection, query: str, k: int) -> list[dict] | None:
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        from openai import OpenAI
        embedding = OpenAI(timeout=60, max_retries=0).embeddings.create(model=os.getenv("FORGE_EMBED_MODEL", "text-embedding-3-large"), input=[query]).data[0].embedding
        result = ChromaStore(CHROMA_PATH).query(embedding, k)
        ids = result.get("ids", [[]])[0]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        rows = conn.execute(f"SELECT {', '.join(PUBLIC_FIELDS)} FROM tickets WHERE ticket_id IN ({placeholders})", ids).fetchall()
        by_id = {row["ticket_id"]: dict(row) for row in rows}
        distances = result.get("distances", [[]])[0]
        tickets = []
        for ticket_id, distance in zip(ids, distances):
            if ticket_id in by_id:
                ticket = by_id[ticket_id]
                ticket["_retrieval_distance"] = distance
                tickets.append(ticket)
        return tickets
    except Exception:
        return None
