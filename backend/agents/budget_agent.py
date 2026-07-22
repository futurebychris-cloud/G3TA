"""Budget Agent.

Responsibility (PRD §7): track running total, flag overspend, allocate per-category caps.
Data source: destination-aware AI cost estimates.
Output shape: {"daily_caps": {...}, "warnings": [...]} (+ reasoning & context fields).
"""
import math

from services.budget_service import get_cost_index

from .base import llm_reason, trip_days

SYSTEM_PROMPT = (
    "You are the Budget Agent in a multi-agent trip planner. You allocate a traveler's "
    "total budget into sensible per-category DAILY caps and flag risks. "
    "You are given: total budget, currency, number of days, an estimated round-trip flight "
    "cost, and a per-day cost index for the destination. "
    "Return ONLY a JSON object with keys: "
    "daily_caps (object with numeric keys food, activity, housing, local_transport), "
    "warnings (array of short strings), and reasoning (one or two sentences explaining the split). "
    "Caps are per day and must be realistic for the destination and budget. If the budget is too "
    "low to cover flights plus a reasonable daily spend, say so clearly in warnings."
)

_CAP_KEYS = ("food", "activity", "housing", "local_transport")


def _deterministic_caps(total: float, num_days: int, index: dict) -> dict:
    """Proportional fallback split used if the LLM reply is unavailable."""
    flight_ref = index.get("flight_reference", 0)
    daily_index = index["daily_index"]
    remaining = max(total - flight_ref, 0)
    per_day = remaining / num_days if num_days else 0
    weight_total = sum(daily_index.values()) or 1
    caps = {k: round(per_day * (v / weight_total), 2) for k, v in daily_index.items()}
    warnings = []
    baseline_daily = sum(daily_index.values())
    if per_day < baseline_daily * 0.7:
        warnings.append(
            f"Budget is tight: ~{per_day:.0f}/day available after flights vs. a typical "
            f"{baseline_daily:.0f}/day for this destination. Expect trade-offs."
        )
    if total <= flight_ref:
        warnings.append("Total budget barely covers (or is below) estimated flight cost.")
    return {"daily_caps": caps, "warnings": warnings}


def _normalize_caps(
    result: dict,
    fallback: dict,
    total: float,
    num_days: int,
    index: dict,
) -> dict:
    """Validate and bound model caps against the actual trip budget.

    The model may choose the category mix, but it cannot allocate more per day
    than remains after the flight estimate or turn food into a disproportionate
    share of the ground budget.
    """
    raw_caps = result.get("daily_caps")
    if not isinstance(raw_caps, dict):
        return fallback

    caps = {}
    for key in _CAP_KEYS:
        try:
            value = float(raw_caps.get(key))
        except (TypeError, ValueError):
            return fallback
        if not math.isfinite(value) or value < 0:
            return fallback
        caps[key] = round(value, 2)

    flight_reference = max(float(index.get("flight_reference", 0)), 0)
    available_per_day = max(total - flight_reference, 0) / max(num_days, 1)
    raw_total = sum(caps.values())
    adjusted = False
    if raw_total > available_per_day and raw_total > 0:
        scale = available_per_day / raw_total
        caps = {key: round(value * scale, 2) for key, value in caps.items()}
        adjusted = True

    typical_food = max(float(index.get("daily_index", {}).get("food", 0)), 0)
    food_ceiling = min(available_per_day * 0.35, typical_food * 1.75)
    if caps["food"] > food_ceiling:
        caps["food"] = round(food_ceiling, 2)
        adjusted = True

    if adjusted:
        warnings = result.setdefault("warnings", [])
        warnings.append(
            "Daily caps were normalized against the post-flight budget so food and other "
            "categories remain proportionate to the trip."
        )
    result["daily_caps"] = caps
    return result


def run(trip_input: dict, overflow: float | None = None) -> dict:
    days = trip_days(trip_input)
    num_days = len(days)
    total = float(trip_input["budget"]["total"])
    currency = trip_input["budget"].get("currency", "USD")
    index = get_cost_index(
        trip_input["location"],
        trip_input.get("origin", ""),
        trip_input.get("dates", {}),
        currency,
    )

    payload = {
        "total_budget": total,
        "currency": currency,
        "num_days": num_days,
        "estimated_flight_cost": index.get("flight_reference"),
        "destination_daily_cost_index": index["daily_index"],
        "cost_level": index.get("cost_level"),
        "destination": trip_input["location"],
        "origin": trip_input.get("origin", ""),
        "dates": trip_input["dates"],
        "all_preferences": trip_input.get("preferences", {}),
        "time_constraints": trip_input.get("time_constraints", ""),
    }
    if overflow:
        payload["overflow_to_trim"] = overflow
        payload["instruction"] = (
            "The current plan is OVER budget by the overflow_to_trim amount. Tighten the "
            "daily caps so the trip fits, and add a warning naming what had to give."
        )

    result = llm_reason(SYSTEM_PROMPT, payload)
    fallback = _deterministic_caps(total, num_days, index)
    if not result:
        result = fallback
        result["reasoning"] = "Deterministic proportional split (LLM reasoning unavailable)."
    else:
        result = _normalize_caps(result, fallback, total, num_days, index)
        result.setdefault("reasoning", "Daily category limits calculated from the total trip budget.")

    result.setdefault("warnings", [])
    if overflow and not any("trim" in w.lower() or "over" in w.lower() for w in result["warnings"]):
        result["warnings"].append(
            f"Plan was over budget by {overflow:.0f} {currency}; caps tightened to fit."
        )

    result["num_days"] = num_days
    result["total_budget"] = total
    result["currency"] = currency
    result["destination"] = trip_input["location"]
    result["cost_index"] = index
    return result
