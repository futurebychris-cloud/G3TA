"""Activity Agent.

Responsibility (PRD §7): recommend activities matching the traveler's style preference.
Data source: activities_service.get_activity_options (mock_activities.json).
Output shape: {"recommended": [...], "cost": number} (+ reasoning).
"""
from services.activities_service import get_activity_options

from .base import llm_reason, trip_days

SYSTEM_PROMPT = (
    "You are the Activity Agent in a multi-agent trip planner. From the given activity options "
    "(already sorted so preferred styles come first), choose roughly one activity per trip day "
    "that matches the traveler's activity style and total budget, avoiding same-area repeats "
    "when possible. "
    "Return ONLY a JSON object with keys: recommended_ids (array of chosen activity ids, in a "
    "sensible order) and reasoning (one sentence)."
)


def run(trip_input: dict) -> dict:
    styles = trip_input.get("preferences", {}).get("activity_style", [])
    options = get_activity_options(trip_input["location"], styles)
    days = trip_days(trip_input)
    target = len(days)

    payload = {
        "destination": trip_input["location"],
        "activity_styles": styles,
        "num_days": len(days),
        "total_budget": trip_input["budget"],
        "options": options,
    }
    result = llm_reason(SYSTEM_PROMPT, payload)

    recommended = []
    reasoning = None
    if result and result.get("recommended_ids"):
        by_id = {o["id"]: o for o in options}
        recommended = [by_id[i] for i in result["recommended_ids"] if i in by_id]
        reasoning = result.get("reasoning")
    if not recommended:
        # Fallback: take the first `target` options (preferred styles already lead the list).
        recommended = options[:target]
        reasoning = "Top style-matched activities selected (LLM reasoning unavailable)."

    cost = sum(a["price"] for a in recommended)
    return {"recommended": recommended, "cost": round(cost, 2), "reasoning": reasoning}
