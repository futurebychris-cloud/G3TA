"""Shared plumbing for the six specialist agents.

Each agent follows the same shape:
    shared trip input  ->  provider/estimate service  ->  DeepSeek reasoning  ->  structured output

`llm_reason` is the single reasoning call. It asks DeepSeek for a JSON object.
If the model is unreachable or returns non-JSON (a transient hiccup), it returns
None so the agent can fall back to a deterministic selection instead of crashing
the whole plan. A MISSING API KEY is NOT swallowed — it propagates, because this
build is configured to require a real DeepSeek key (see PRD decision).
"""
import json

from llm.deepseek_client import chat_json
from plan_runtime import raise_if_cancelled


def llm_reason(system_prompt: str, payload: dict, temperature: float = 0.4) -> dict | None:
    """Run one reasoning turn. Returns the parsed JSON dict, or None on a soft failure."""
    try:
        return chat_json(system_prompt, json.dumps(payload, ensure_ascii=False), temperature)
    except RuntimeError:
        # Missing/invalid API key — this build requires a key, so surface it loudly.
        raise
    except Exception:
        # Network blip, rate limit, or non-JSON reply: let the agent fall back.
        return None


def report_progress(trip_input: dict, detail: str) -> None:
    """Publish an internal sub-stage when the streaming endpoint supplied a callback."""
    raise_if_cancelled(trip_input)
    callback = trip_input.get("_progress_callback")
    if callable(callback):
        callback(str(detail))


def trip_days(trip_input: dict) -> list[str]:
    """Return the list of ISO date strings the trip spans (inclusive)."""
    from datetime import date, timedelta

    start = date.fromisoformat(trip_input["dates"]["start"])
    end = date.fromisoformat(trip_input["dates"]["end"])
    if end < start:
        start, end = end, start
    out = []
    cur = start
    while cur <= end:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out
