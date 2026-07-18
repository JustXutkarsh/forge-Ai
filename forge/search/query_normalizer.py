"""Configurable, additive query expansion for support-ticket retrieval."""

from __future__ import annotations

import re


# Add a trigger or expansion term here when a new support vocabulary is needed.
SYNONYM_GROUPS: dict[str, dict[str, tuple[str, ...]]] = {
    "login": {
        "triggers": ("login", "log in", "logging in", "sign in", "signin", "sign-in", "authentication", "authenticate", "authenticated", "auth", "credentials", "credential", "password", "account access", "login failure"),
        "expansions": ("login", "login issue", "authentication", "sign in", "signin", "credential", "password"),
    },
    "payment": {
        "triggers": ("payment", "payments", "billing", "refund", "refunds"),
        "expansions": ("payment", "billing", "refund"),
    },
    "performance": {
        "triggers": ("performance", "slow", "lag", "freeze", "freezing"),
        "expansions": ("performance", "slow", "lag", "freeze"),
    },
    "sync": {
        "triggers": ("sync", "synchronization", "synchronise", "synchronize"),
        "expansions": ("sync", "synchronization"),
    },
    "crash": {
        "triggers": ("crash", "crashes", "crashed", "failure", "failures", "failed"),
        "expansions": ("crash", "failure"),
    },
    "browser": {
        "triggers": ("browser", "chrome", "firefox", "safari"),
        "expansions": ("browser", "chrome", "firefox", "safari"),
    },
}


def _contains_phrase(query: str, phrase: str) -> bool:
    """Match a term without matching it inside a larger word."""
    return re.search(rf"(?<!\w){re.escape(phrase.lower())}(?!\w)", query) is not None


def expand_query(query: str) -> str:
    """Return the original query followed by relevant synonym terms."""
    original = str(query or "").strip()
    if not original:
        return original
    lowered = original.lower()
    additions: list[str] = []
    seen = {token.lower() for token in re.findall(r"[^\s]+", original)}
    for group in SYNONYM_GROUPS.values():
        if not any(_contains_phrase(lowered, trigger) for trigger in group["triggers"]):
            continue
        for term in group["expansions"]:
            if term.lower() not in seen:
                additions.append(term)
                seen.add(term.lower())
    return " ".join([original, *additions])
