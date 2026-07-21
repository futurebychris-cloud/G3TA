"""Activity Agent.

Responsibility (PRD §7): recommend activities matching the traveler's style preference.
Data source: destination-aware AI activity estimates.
Output shape: {"recommended": [...], "cost": number} (+ reasoning).
"""
from services.activities_service import get_activity_options

from .base import llm_reason, trip_days

SYSTEM_PROMPT = (
    "You are the Activity Agent in a multi-agent trip planner. From the given activity options "
    "(already sorted so preferred styles come first), choose roughly one activity per trip day "
    "that matches the traveler's activity style and total budget, avoiding same-area repeats "
    "when possible. Every choice MUST be in the exact destination (or a clearly labeled realistic "
    "day trip from it). Never select another city/country and never repeat an activity. "
    "Return ONLY a JSON object with keys: recommended_ids (array of chosen activity ids, in a "
    "sensible order) and reasoning (one sentence)."
)


def run(trip_input: dict) -> dict:
    styles = trip_input.get("preferences", {}).get("activity_style", [])
    days = trip_days(trip_input)
    target = len(days)
    options = get_activity_options(
        trip_input["location"],
        styles,
        requested_count=target,
        budget=trip_input.get("budget", {}),
        time_constraints=trip_input.get("time_constraints", ""),
    )

    payload = {
        "destination": trip_input["location"],
        "activity_styles": styles,
        "num_days": len(days),
        "total_budget": trip_input["budget"],
        "dates": trip_input["dates"],
        "all_preferences": trip_input.get("preferences", {}),
        "time_constraints": trip_input.get("time_constraints", ""),
        "options": options,
    }
    result = llm_reason(SYSTEM_PROMPT, payload)

    recommended = []
    reasoning = None
    if result and result.get("recommended_ids"):
        by_id = {o["id"]: o for o in options}
        seen = set()
        recommended = []
        for option_id in result["recommended_ids"]:
            if option_id in by_id and option_id not in seen:
                recommended.append(by_id[option_id])
                seen.add(option_id)
        reasoning = result.get("reasoning")
    if len(recommended) < target:
        selected_ids = {option["id"] for option in recommended}
        recommended.extend(option for option in options if option["id"] not in selected_ids)
        recommended = recommended[:target]
    if not reasoning:
        reasoning = "Top style-matched activities selected (LLM reasoning unavailable)."

    cost = sum(a["price"] for a in recommended)
    return {
        "recommended": recommended,
        "cost": round(cost, 2),
        "reasoning": reasoning,
        "destination": trip_input["location"],
        "verification_required": True,
    }
