"""Turn a natural-language trip description into a safe, reviewable draft.

The model is only allowed to extract details the traveler supplied.  The
frontend always presents this draft for review before it can reach the planner.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from llm.deepseek_client import chat_json
from services.weather_service import geocode_destination


INTAKE_PROMPT = """You extract travel details for an accessible trip-planning form.
Return one JSON object with exactly these keys:
origin, location, start_date, end_date, budget_total, currency, num_people,
cuisines, transportation, activity_styles, time_constraints, must_go_sites,
uncertain_fields, confirmation.

Rules:
- Extract only information stated or unambiguously implied by the traveler.
- Never invent a city, date, budget, currency, preference, or number of people.
- Use null for an unknown scalar and [] for an unknown list.
- Dates must be ISO YYYY-MM-DD. Resolve relative dates using the supplied current_date.
- location must be a searchable place in "City, Country" order when both are known.
  For example, "Italy and Milan" means "Milan, Italy", not "Italy and Milan".
- currency must be a three-letter ISO-style code such as USD, EUR, GBP, JPY, or CNY.
- transportation values must be flight, train, or car.
- activity_styles values must be cultural, adventure, or relaxed.
- uncertain_fields may contain only: origin, location, start_date, end_date,
  budget_total, currency, num_people, cuisines, transportation,
  activity_styles, time_constraints, must_go_sites.
- confirmation is one short, plain-language sentence describing only extracted facts.
- Do not start planning and do not provide recommendations.
"""

ALLOWED_TRANSPORT = {"flight", "train", "car"}
ALLOWED_STYLES = {"cultural", "adventure", "relaxed"}
FIELD_NAMES = {
    "origin",
    "location",
    "start_date",
    "end_date",
    "budget_total",
    "currency",
    "num_people",
    "cuisines",
    "transportation",
    "activity_styles",
    "time_constraints",
    "must_go_sites",
}


def _text(value: Any) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None


def _date(value: Any) -> str | None:
    cleaned = _text(value)
    if not cleaned:
        return None
    try:
        return date.fromisoformat(cleaned).isoformat()
    except ValueError:
        return None


def _positive_number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if 0 < parsed < 100_000_000 else None


def _people(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if 1 <= parsed <= 100 else None


def _list(value: Any, *, limit: int = 12) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        cleaned = str(item or "").strip()
        if cleaned and cleaned.casefold() not in {entry.casefold() for entry in result}:
            result.append(cleaned)
        if len(result) >= limit:
            break
    return result


def _free_text(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(_list(value))
    return _text(value) or ""


def _canonicalize_spoken_location(value: Any) -> str | None:
    """Turn a spoken country/city pair into a provider-searchable destination.

    We only rewrite conjunctions after the geocoder confirms that one named
    place belongs to the other. If lookup is unavailable, the reviewable model
    value is preserved instead of guessing.
    """
    location = _text(value)
    if not location:
        return None
    parts = [part.strip(" ,") for part in re.split(r"\s+(?:and|&)\s+", location, flags=re.IGNORECASE)]
    if len(parts) != 2 or not all(parts):
        return location

    for city, country in ((parts[1], parts[0]), (parts[0], parts[1])):
        try:
            resolved = geocode_destination(city)
        except Exception:
            continue
        resolved_name = _text(resolved.get("name")) if isinstance(resolved, dict) else None
        if resolved_name and _contains_place_name(resolved_name, country):
            canonical_city = resolved_name.split(",", 1)[0].strip()
            return f"{canonical_city}, {country}"
    return location


def _contains_place_name(resolved_name: str, requested_name: str) -> bool:
    return re.search(
        rf"(?<!\w){re.escape(requested_name.strip())}(?!\w)",
        resolved_name,
        re.IGNORECASE,
    ) is not None


def normalize_intake(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate model output and return the frontend's structured draft contract."""
    origin = _text(raw.get("origin"))
    location = _canonicalize_spoken_location(raw.get("location"))
    start = _date(raw.get("start_date"))
    end = _date(raw.get("end_date"))
    if start and end and end < start:
        end = None

    total = _positive_number(raw.get("budget_total"))
    currency = (_text(raw.get("currency")) or "").upper()
    if len(currency) != 3 or not currency.isalpha():
        currency = None

    people = _people(raw.get("num_people"))
    cuisines = _list(raw.get("cuisines"))
    transportation = [
        value.casefold() for value in _list(raw.get("transportation"))
        if value.casefold() in ALLOWED_TRANSPORT
    ]
    activity_styles = [
        value.casefold() for value in _list(raw.get("activity_styles"))
        if value.casefold() in ALLOWED_STYLES
    ]
    must_go_sites = _list(raw.get("must_go_sites"), limit=10)
    time_constraints = _free_text(raw.get("time_constraints"))

    required = {
        "origin": origin,
        "location": location,
        "start_date": start,
        "end_date": end,
        "budget_total": total,
        "currency": currency,
    }
    missing = [name for name, value in required.items() if value in (None, "")]
    uncertain = [
        value for value in _list(raw.get("uncertain_fields"))
        if value in FIELD_NAMES and value not in missing
    ]

    confirmation = _text(raw.get("confirmation"))
    if not confirmation:
        facts = []
        if origin and location:
            facts.append(f"from {origin} to {location}")
        elif location:
            facts.append(f"to {location}")
        if start and end:
            facts.append(f"from {start} to {end}")
        if total and currency:
            facts.append(f"with a {currency} {total:g} budget")
        confirmation = "I created a draft " + ", ".join(facts) + "." if facts else "I created a partial trip draft."

    return {
        "draft": {
            "origin": origin,
            "location": location,
            "dates": {"start": start, "end": end},
            "budget": {"total": total, "currency": currency},
            "preferences": {
                "bites": cuisines,
                "transportation_type": transportation,
                "activity_style": activity_styles,
            },
            "time_constraints": time_constraints,
            "must_go_sites": must_go_sites,
            "num_people": people,
        },
        "missing": missing,
        "uncertain": uncertain,
        "summary": confirmation,
    }


def parse_intake(description: str, current_date: date | None = None) -> dict[str, Any]:
    payload = {
        "current_date": (current_date or date.today()).isoformat(),
        "traveler_description": description.strip(),
    }
    raw = chat_json(INTAKE_PROMPT, json.dumps(payload, ensure_ascii=False), temperature=0.1)
    if not isinstance(raw, dict):
        raw = {}
    return normalize_intake(raw)
