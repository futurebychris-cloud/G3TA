"""In-process lifecycle controls for streamed planning requests."""
from __future__ import annotations

import threading


class PlanningCancelled(RuntimeError):
    """Raised when the traveler cancels an active planning request."""


_LOCK = threading.RLock()
_CANCELLATIONS: dict[str, threading.Event] = {}


def register_plan(request_id: str) -> threading.Event:
    event = threading.Event()
    with _LOCK:
        _CANCELLATIONS[request_id] = event
    return event


def cancel_plan(request_id: str) -> bool:
    with _LOCK:
        event = _CANCELLATIONS.get(request_id)
    if event is None:
        return False
    event.set()
    return True


def finish_plan(request_id: str) -> None:
    with _LOCK:
        _CANCELLATIONS.pop(request_id, None)


def raise_if_cancelled(trip_input: dict) -> None:
    event = trip_input.get("_cancel_event")
    if event is not None and event.is_set():
        raise PlanningCancelled("Trip planning was cancelled.")
