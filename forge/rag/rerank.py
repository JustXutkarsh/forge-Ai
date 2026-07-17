def rerank(query: str, tickets: list[dict], n: int = 5) -> list[dict]:
    # The local fallback is intentionally deterministic. A cross-encoder can replace this module later.
    words = set(query.lower().split())
    def score(ticket: dict) -> int:
        text = " ".join(str(v) for v in ticket.values()).lower()
        return sum(text.count(word) for word in words if len(word) > 2)
    return sorted(tickets, key=score, reverse=True)[:n]
