"""Transportation Agent.

Responsibility (PRD §7): recommend flight/train/car option(s) within budget.
Data source: flights_service.get_flight_options (mock_flights.json).
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
    "and activities."
)


def run(trip_input: dict) -> dict:
    origin = trip_input.get("origin", "New York")
    options = get_flight_options(origin, trip_input["location"], trip_input["dates"])

    payload = {
        "origin": origin,
        "destination": trip_input["location"],
        "total_budget": trip_input["budget"],
        "preferences": trip_input.get("preferences", {}),
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
    }
