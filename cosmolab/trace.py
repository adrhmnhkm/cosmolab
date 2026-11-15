"""
cosmolab.trace
~~~~~~~~~~~~~~
Records what the source search did, step by step, for `cosmolab jejak`.

Off by default: add() does nothing until start() is called. The recorder is a
plain global, not a context variable, so steps taken in worker threads
(papers are searched in parallel) are recorded too. Only one recording runs at
a time; it is meant for the command line, not for the shared dashboard.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager

_LOCK = threading.Lock()
_EVENTS: list[dict] | None = None
_T0 = 0.0
_LISTENER = None


def active() -> bool:
    return _EVENTS is not None


def start(listener=None) -> None:
    """listener(event) is called as each step is recorded, e.g. to show progress."""
    global _EVENTS, _T0, _LISTENER
    with _LOCK:
        _EVENTS = []
        _T0 = time.monotonic()
        _LISTENER = listener


def stop() -> list[dict]:
    global _EVENTS, _LISTENER
    with _LOCK:
        events, _EVENTS, _LISTENER = _EVENTS or [], None, None
    return events


def add(stage: str, **data) -> None:
    """Record one step. Does nothing while no recording runs."""
    if _EVENTS is None:
        return
    with _LOCK:
        if _EVENTS is None:
            return
        event = {"stage": stage, "t": round(time.monotonic() - _T0, 2),
                 "thread": threading.current_thread().name, **data}
        _EVENTS.append(event)
        listener = _LISTENER
    if listener:
        try:
            listener(event)
        except Exception:
            pass


@contextmanager
def recording(listener=None):
    """with recording() as events: ... -- events is filled when the block ends."""
    events: list[dict] = []
    start(listener)
    try:
        yield events
    finally:
        events.extend(stop())


def short(text: str, n: int = 200) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 3] + "..."
