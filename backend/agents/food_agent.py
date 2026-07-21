"""Food Agent.

Responsibility (PRD §7): recommend meals/restaurants matching cuisine preferences.
Data source: food_service.get_food_options (mock_food.json).
Output shape: {"daily_meals": [...], "cost": number} (+ reasoning).
"""
from services.food_service import get_food_options

from .base import llm_reason, trip_days

SYSTEM_PROMPT = (
    "You are the Food Agent in a multi-agent trip planner. You are given restaurant options "
    "(already sorted so preferred cuisines come first) and the traveler's cuisine tags. "
    "Return ONLY a JSON object with a single key: reasoning — one sentence describing how the "
    "day-to-day meal plan reflects the traveler's cuisine preferences and budget."
)

_SLOTS = ["breakfast", "lunch", "dinner"]


def _by_slot(options: list[dict]) -> dict:
    buckets = {s: [o for o in options if o["meal_type"] == s] for s in _SLOTS}
    # Any slot with no dedicated option falls back to the full list so no meal is empty.
    for s in _SLOTS:
        if not buckets[s]:
            buckets[s] = options
    return buckets


def run(trip_input: dict) -> dict:
    cuisine_tags = trip_input.get("preferences", {}).get("bites", [])
    options = get_food_options(trip_input["location"], cuisine_tags)
    days = trip_days(trip_input)
    buckets = _by_slot(options)

    daily_meals = []
    total = 0.0
    for i, day in enumerate(days):
        meals = []
        for s in _SLOTS:
            pool = buckets[s]
            pick = pool[i % len(pool)]
            meals.append({
                "slot": s,
                "name": pick["name"],
                "cuisine": pick["cuisine"],
                "price": pick["price"],
                "area": pick["area"],
            })
            total += pick["price"]
        daily_meals.append({"date": day, "meals": meals})

    result = llm_reason(SYSTEM_PROMPT, {
        "cuisine_tags": cuisine_tags,
        "options": options,
        "num_days": len(days),
    })
    reasoning = (result or {}).get("reasoning") or (
        f"Meals rotate through {len(options)} spots, leading with preferred cuisines "
        f"({', '.join(cuisine_tags) or 'no specific tags'})."
    )

    return {"daily_meals": daily_meals, "cost": round(total, 2), "reasoning": reasoning}
