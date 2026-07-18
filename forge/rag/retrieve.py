import re
import sqlite3

from forge.config import CHROMA_PATH
from forge.rag.embedding import get_embedding_service
from forge.rag.vectorstore import ChromaStore
from forge.profiling import note, stage
from forge.search.query_normalizer import expand_query


PUBLIC_FIELDS = ["ticket_id", "product", "category", "priority", "status", "channel", "region", "ticket_created_date", "issue_description", "resolution_notes"]
STOPWORDS = {"a", "an", "are", "be", "by", "did", "for", "how", "in", "is", "many", "of", "occurred", "please", "the", "to", "was", "what", "when", "where", "who", "why", "with", "user", "users"}


def retrieve(conn: sqlite3.Connection, query: str, k: int = 5) -> list[dict]:
    retrieval_query = expand_query(query)
    semantic = _semantic_retrieve(conn, retrieval_query, k)
    if semantic is not None:
        note(f"Retrieval strategy=semantic evidence_ids={[item.get('ticket_id') for item in semantic]}")
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
    result = sorted(result, key=lambda item: item.get("_score", 0), reverse=True)[:k]
    note(f"Retrieval strategy=sql_fallback evidence_ids={[item.get('ticket_id') for item in result]}")
    return result


def _semantic_retrieve(conn: sqlite3.Connection, query: str, k: int) -> list[dict] | None:
    try:
        with stage("Embedding request"):
            embedding = get_embedding_service().embed_query(query)
        result = ChromaStore(CHROMA_PATH).query(embedding, k)
        ids = result.get("ids", [[]])[0]
        note(f"Chroma query succeeded evidence_ids={ids}")
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
        note(f"SQL hydration ids={[ticket.get('ticket_id') for ticket in tickets]}")
        return tickets or None
    except Exception as exc:
        note(f"Chroma query failed; retrieval strategy=sql_fallback reason={type(exc).__name__}: {exc}")
        return None
