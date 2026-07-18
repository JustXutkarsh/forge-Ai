"""Opt-in timing helpers for diagnosing Forge command latency."""

from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator, TypeVar


PROCESS_START = time.perf_counter()
ENABLED = os.getenv("FORGE_PROFILE", "").strip().lower() in {"1", "true", "yes", "on"}
_TIMINGS: dict[str, float] = {}
_CAPTURE: ContextVar[dict[str, Any] | None] = ContextVar("forge_profile_capture", default=None)
T = TypeVar("T")


def add(name: str, elapsed: float) -> None:
    """Accumulate elapsed time for a named profiling stage when enabled."""
    if ENABLED:
        _TIMINGS[name] = _TIMINGS.get(name, 0.0) + elapsed
    capture = _CAPTURE.get()
    if capture is not None:
        timings = capture["timings"]
        timings[name] = timings.get(name, 0.0) + elapsed


@contextmanager
def capture() -> Iterator[dict[str, Any]]:
    """Capture stage timings and diagnostic notes for one request."""
    result: dict[str, Any] = {"timings": {}, "notes": []}
    token = _CAPTURE.set(result)
    try:
        yield result
    finally:
        _CAPTURE.reset(token)


@contextmanager
def stage(name: str) -> Iterator[None]:
    """Measure one stage without changing its return value or exceptions."""
    started = time.perf_counter()
    try:
        yield
    finally:
        add(name, time.perf_counter() - started)


def report() -> None:
    """Print collected timings to stderr for an opted-in diagnostic run."""
    if not ENABLED:
        return
    print("Forge profiling", file=sys.stderr)
    for name, elapsed in _TIMINGS.items():
        print(f"{name}: {elapsed:.2f}s", file=sys.stderr)


def note(message: str) -> None:
    """Print a diagnostic note only during an opted-in profiling run."""
    capture = _CAPTURE.get()
    if capture is not None:
        capture["notes"].append(message)
    if ENABLED:
        print(f"[profile] {message}", file=sys.stderr)


def chroma_call(name: str, function: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Trace one Chroma API call, including its failure boundary."""
    if ENABLED:
        print(f"[chroma] before {name}", file=sys.stderr)
    started = time.perf_counter()
    try:
        result = function(*args, **kwargs)
    except Exception as exc:
        elapsed = time.perf_counter() - started
        if ENABLED:
            print(f"[chroma] failed {name}: {elapsed:.2f}s: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
    elapsed = time.perf_counter() - started
    if ENABLED:
        print(f"[chroma] after {name}: {elapsed:.2f}s", file=sys.stderr)
    return result
