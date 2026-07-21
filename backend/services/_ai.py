"""Shared AI-backed data generation for services without live provider APIs.

DeepSeek-generated travel data is useful for planning but is not live inventory.
Every generated record is marked as an estimate and requires verification before
booking. Missing keys remain a hard error; transient model failures fall back to
destination-neutral estimates in each service, never to another city's dataset.
"""
import json
import math

from llm.deepseek_client import chat_json


ESTIMATE_NOTE = "AI-generated estimate; verify price, availability, hours, and location before booking."


def generate_json(system_prompt: str, payload: dict, temperature: float = 0.5) -> dict | None:
    try:
        return chat_json(system_prompt, json.dumps(payload, ensure_ascii=False), temperature)
    except RuntimeError:
        raise
    except Exception:
        return None


def number(value, default: float = 0.0, minimum: float = 0.0) -> float:
    try:
        parsed = float(value)
        if not math.isfinite(parsed):
            return default
        return max(parsed, minimum)
    except (TypeError, ValueError):
        return default


def integer(value, default: int = 0, minimum: int = 0) -> int:
    return int(number(value, default, minimum))


def text(value, default: str = "") -> str:
    cleaned = str(value or "").strip()
    return cleaned or default


def string_list(value, default: list[str] | None = None) -> list[str]:
    if not isinstance(value, list):
        return list(default or [])
    return [str(item).strip() for item in value if str(item).strip()]


def coordinates(item: dict) -> tuple[float | None, float | None]:
    try:
        lat = float(item.get("lat"))
        lng = float(item.get("lng"))
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            return lat, lng
    except (TypeError, ValueError):
        pass
    return None, None


def estimated_record(item: dict, destination: str) -> dict:
    return {
        **item,
        "destination": destination,
        "source": "deepseek_estimate",
        "verification_required": True,
        "estimate_note": ESTIMATE_NOTE,
    }
