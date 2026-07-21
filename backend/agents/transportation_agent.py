"""Transportation Agent.

Responsibility (PRD §7): recommend flight/train/car option(s) within budget.
Data source: destination-aware AI transportation estimates.
Output shape: {"options": [...], "recommended": {...}, "cost": number} (+ reasoning).
"""
from services.flights_service import get_flight_options

from .base import llm_reason

SYSTEM_PROMPT = (
    "You are the Transportation Agent in a multi-agent trip planner. From the given flight "
    "options, pick the single best one for the traveler, balancing price, duration, and number "
    "of stops against their total budget and preferences. "
    "Return ONLY a JSON object with keys: recommended_id (the id of your pick), and reasoning "
    "(one sentence on why). Choose an option that leaves room in the budget for lodging, food, "
    "and activities. The route MUST start at the supplied origin and end at the supplied exact "
    "destination; reject anything for another city or country. Treat schedules and prices as "
    "estimates requiring verification."
)


def run(trip_input: dict) -> dict:
    origin = trip_input.get("origin", "New York")
    transport_types = trip_input.get("preferences", {}).get("transportation_type", [])
    options = get_flight_options(
        origin,
        trip_input["location"],
        trip_input["dates"],
        trip_input.get("budget", {}),
        transport_types,
    )

    payload = {
        "origin": origin,
        "destination": trip_input["location"],
        "total_budget": trip_input["budget"],
        "preferences": trip_input.get("preferences", {}),
        "dates": trip_input["dates"],
        "time_constraints": trip_input.get("time_constraints", ""),
        "options": options,
    }
    result = llm_reason(SYSTEM_PROMPT, payload)

    recommended = None
    reasoning = None
    if result and result.get("recommended_id"):
        recommended = next((o for o in options if o["id"] == result["recommended_id"]), None)
        reasoning = result.get("reasoning")
    if recommended is None:
        # Fallback: cheapest non-stop if available, else cheapest overall.
        nonstop = [o for o in options if o.get("stops", 0) == 0]
        pool = nonstop or options
        recommended = min(pool, key=lambda o: o["price"])
        reasoning = "Cheapest suitable option selected (LLM reasoning unavailable)."

    return {
        "options": options,
        "recommended": recommended,
        "cost": recommended["price"],
        "reasoning": reasoning,
        "destination": trip_input["location"],
        "verification_required": True,
    }
