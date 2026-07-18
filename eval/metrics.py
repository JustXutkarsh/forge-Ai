"""Pure metric functions for Forge evaluation."""

from __future__ import annotations

from statistics import mean
from typing import Iterable, Sequence


def recall_at_k(retrieved_ids: Sequence[str], relevant_ids: Iterable[str], k: int = 5) -> float:
    """Return the fraction of relevant IDs found in the first ``k`` results."""
    relevant = set(relevant_ids)
    if not relevant:
        return 0.0
    return len(set(retrieved_ids[:k]) & relevant) / len(relevant)


def precision_at_k(retrieved_ids: Sequence[str], relevant_ids: Iterable[str], k: int = 5) -> float:
    """Return the fraction of the first ``k`` results that are relevant."""
    retrieved = list(retrieved_ids[:k])
    if not retrieved:
        return 0.0
    return len(set(retrieved) & set(relevant_ids)) / len(retrieved)


def accuracy(values: Iterable[bool]) -> float:
    """Return the mean of boolean outcomes, or zero for no outcomes."""
    outcomes = [int(value) for value in values]
    return mean(outcomes) if outcomes else 0.0


def planner_accuracy(outcomes: Iterable[bool]) -> float:
    """Return the percentage of cases with an exactly matching tool chain."""
    return accuracy(outcomes)


def structured_query_accuracy(outcomes: Iterable[bool]) -> float:
    """Return accuracy for cases with structured operation/field expectations."""
    return accuracy(outcomes)


def hallucination_rate(outcomes: Iterable[bool]) -> float:
    """Return the percentage of evaluated responses classified as hallucinations."""
    return accuracy(outcomes)


def average_latency(latencies_ms: Iterable[float]) -> float:
    """Return average response latency in milliseconds."""
    values = list(latencies_ms)
    return mean(values) if values else 0.0
