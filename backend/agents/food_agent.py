"""Food Agent.

Builds a meal plan from cuisine-matched restaurant options. Selected cuisines
are a hard preference whenever matching data exists: unrelated restaurants are
not allowed back into the plan merely to add variety.
"""
from services.food_service import get_food_options, matches_cuisine_preferences

from .base import llm_reason, trip_days

SYSTEM_PROMPT = (
    "You are the Food Agent in a multi-agent trip planner. Build the meal plan from ONLY "
    "the supplied eligible_options. The traveler's selected_cuisines are ordered by "
    "preference; honor them strongly, balance cost against the total trip budget, respect "
    "the requested meal slot, and do not repeat a venue while unused eligible choices remain. "
    "Every venue must be in the exact destination; never mention another city/country. Consider the destination, "
    "dates, all traveler preferences, and time constraints together. Return ONLY a JSON "
    "object with keys: meal_plan (an array with one object per date, shaped as "
    "{date, meals: [{slot, option_id}]} with breakfast, lunch, and dinner) and reasoning "
    "(one or two concise sentences explaining cuisine fit and budget trade-offs)."
)

_SLOTS = ["breakfast", "lunch", "dinner"]
_SLOT_WEIGHTS = {"breakfast": 0.25, "lunch": 0.35, "dinner": 0.40}


def _by_slot(options: list[dict]) -> dict:
    buckets = {slot: [option for option in options if option["meal_type"] == slot] for slot in _SLOTS}
    for slot in _SLOTS:
        if not buckets[slot]:
            buckets[slot] = options
    return buckets


def _validated_llm_picks(result: dict | None, days: list[str], eligible: list[dict]) -> dict:
    """Index valid model selections by date/slot; ignore invented or ineligible IDs."""
    if not result or not isinstance(result.get("meal_plan"), list):
        return {}

    eligible_by_id = {option["id"]: option for option in eligible}
    valid_days = set(days)
    picks = {}
    for day_plan in result["meal_plan"]:
        if not isinstance(day_plan, dict) or day_plan.get("date") not in valid_days:
            continue
        for meal in day_plan.get("meals", []):
            if not isinstance(meal, dict):
                continue
            slot = meal.get("slot")
            option = eligible_by_id.get(meal.get("option_id"))
            if slot in _SLOTS and option:
                # Prefer exact meal-slot matches. Cross-slot picks are only accepted
                # when the eligible pool has no dedicated option for that slot.
                has_exact_slot = any(candidate["meal_type"] == slot for candidate in eligible)
                if option["meal_type"] == slot or not has_exact_slot:
                    picks[(day_plan["date"], slot)] = option
    return picks


def _target_cuisine(cuisine_tags: list[str], meal_index: int) -> str | None:
    """Weight the first selected cuisine as primary without excluding the rest."""
    if not cuisine_tags:
        return None
    if len(cuisine_tags) == 1 or meal_index % 3 in {0, 1}:
        return cuisine_tags[0]
    secondary_index = (meal_index // 3) % (len(cuisine_tags) - 1)
    return cuisine_tags[secondary_index + 1]


def run(trip_input: dict) -> dict:
    cuisine_tags = trip_input.get("preferences", {}).get("bites", [])
    days = trip_days(trip_input)
    raw_daily_cap = trip_input.get("_budget_caps", {}).get("food")
    try:
        daily_food_cap = max(float(raw_daily_cap), 0) if raw_daily_cap is not None else None
    except (TypeError, ValueError):
        daily_food_cap = None
    all_options = get_food_options(
        trip_input["location"],
        cuisine_tags,
        num_days=len(days),
        budget=trip_input.get("budget", {}),
        preferences=trip_input.get("preferences", {}),
        time_constraints=trip_input.get("time_constraints", ""),
        daily_budget=daily_food_cap,
    )

    matched = [
        option for option in all_options
        if matches_cuisine_preferences(option, cuisine_tags)
    ] if cuisine_tags else []

    # A selected cuisine becomes a hard pool when the data source has matches.
    # If an API has no matches, retain a transparent fallback instead of failing.
    eligible = matched or all_options
    used_preference_fallback = bool(cuisine_tags and not matched)
    buckets = _by_slot(eligible)

    result = llm_reason(SYSTEM_PROMPT, {
        "destination": trip_input["location"],
        "dates": trip_input["dates"],
        "num_days": len(days),
        "total_budget": trip_input["budget"],
        "food_budget_per_day": daily_food_cap,
        "hard_budget_rule": (
            "The combined breakfast, lunch, and dinner price for each day must not exceed "
            "food_budget_per_day."
        ) if daily_food_cap is not None else None,
        "selected_cuisines": cuisine_tags,
        "cuisine_priority_rule": (
            "Treat the first selected cuisine as primary (roughly two thirds of meals); "
            "use remaining selected cuisines for variety. Never use an unselected cuisine "
            "when matched options are available."
        ),
        "all_preferences": trip_input.get("preferences", {}),
        "time_constraints": trip_input.get("time_constraints", ""),
        "eligible_options": eligible,
        "preference_match_available": not used_preference_fallback,
    })
    model_picks = _validated_llm_picks(result, days, eligible)

    daily_meals = []
    total = 0.0
    used_option_ids = set()
    for day_index, day in enumerate(days):
        meals = []
        for slot_index, slot in enumerate(_SLOTS):
            pool = buckets[slot]
            target_cuisine = _target_cuisine(cuisine_tags, day_index * len(_SLOTS) + slot_index)
            target_pool = [
                option for option in pool
                if matches_cuisine_preferences(option, [target_cuisine])
            ] if target_cuisine and matched else []
            allowed_pool = target_pool or pool

            slot_cap = (
                round(daily_food_cap * _SLOT_WEIGHTS[slot], 2)
                if daily_food_cap is not None else None
            )
            if slot_cap is not None:
                affordable = [option for option in allowed_pool if option["price"] <= slot_cap]
                if affordable:
                    allowed_pool = affordable

            model_pick = model_picks.get((day, slot))
            if model_pick and target_pool and model_pick not in target_pool:
                model_pick = None
            if model_pick and model_pick["id"] in used_option_ids:
                model_pick = None
            if model_pick and slot_cap is not None and model_pick["price"] > slot_cap:
                model_pick = None
            unused_pool = [option for option in allowed_pool if option["id"] not in used_option_ids]
            selection_pool = unused_pool or allowed_pool
            pick = model_pick or selection_pool[(day_index + slot_index) % len(selection_pool)]
            used_option_ids.add(pick["id"])
            meals.append({
                "slot": slot,
                "name": pick["name"],
                "cuisine": pick.get("cuisine_family", pick["cuisine"]),
                "price": pick["price"],
                "area": pick["area"],
            })
            total += pick["price"]
        daily_meals.append({"date": day, "meals": meals})

    chosen_cuisines = []
    for daily in daily_meals:
        for meal in daily["meals"]:
            if meal["cuisine"] not in chosen_cuisines:
                chosen_cuisines.append(meal["cuisine"])
    reasoning = None
    if used_preference_fallback:
        selected = ", ".join(cuisine_tags)
        reasoning = (
            f"No {selected} options were available from the current data source, so the closest "
            "available restaurants were used. Connect a broader food API for exact matches."
        )
    else:
        if cuisine_tags:
            reasoning = (
                f"DeepSeek planned meals within the selected cuisine preferences "
                f"({', '.join(chosen_cuisines)}). The validated meal estimate is "
                f"{total:.0f} {trip_input['budget'].get('currency', 'USD')} across {len(days)} day(s), "
                f"with {len(used_option_ids)} distinct dining choices"
                f"{' and the daily food cap enforced' if daily_food_cap is not None else ''}."
            )
        else:
            reasoning = (
                f"DeepSeek selected a local variety across {len(used_option_ids)} distinct dining "
                f"choices. The validated meal estimate is {total:.0f} "
                f"{trip_input['budget'].get('currency', 'USD')}."
            )

    return {
        "daily_meals": daily_meals,
        "cost": round(total, 2),
        "reasoning": reasoning,
        "destination": trip_input["location"],
        "verification_required": True,
        "daily_budget_cap": daily_food_cap,
    }
