"""Housing Agent.

Responsibility (PRD §7): recommend lodging within budget, near the planned activity zone.
Data source: hotels_service.get_hotel_options (mock_hotels.json).
Output shape: {"options": [...], "recommended": {...}, "cost": number} (+ reasoning, nights).

Note: this agent recommends its *preferred* lodging. Whole-trip budget reconciliation
(and any forced downgrade) happens in the Orchestrator, which is where the auditable
"first pick rejected because it broke the budget cap" trade-off is recorded.
"""
from services.hotels_service import get_hotel_options

from .base import llm_reason, trip_days

SYSTEM_PROMPT = (
    "You are the Housing Agent in a multi-agent trip planner. From the given lodging options, "
    "pick the best single place to stay for the whole trip, weighing rating, price per night, "
    "area convenience, and how it matches the traveler's activity style. "
    "Return ONLY a JSON object with keys: recommended_id (the id of your pick) and reasoning "
    "(one sentence)."
)


def run(trip_input: dict) -> dict:
    nights = max(len(trip_days(trip_input)) - 1, 1)
    options = get_hotel_options(trip_input["location"], trip_input["dates"])

    payload = {
        "destination": trip_input["location"],
        "nights": nights,
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
        # Fallback: best rating-per-dollar.
        recommended = max(options, key=lambda o: o["rating"] / max(o["price_per_night"], 1))
        reasoning = "Best rating-for-price selected (LLM reasoning unavailable)."

    return {
        "options": options,
        "recommended": recommended,
        "nights": nights,
        "cost": recommended["price_per_night"] * nights,
        "reasoning": reasoning,
    }
