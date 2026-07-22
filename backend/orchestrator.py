"""Orchestrator.

Runs the six specialist agents, reconciles their combined cost against the
traveler's total budget (re-querying the Budget Agent and downgrading lodging if
the plan overflows — the auditable trade-off from PRD §13), then makes one
DeepSeek call to synthesize a day-by-day itinerary.

Public API:
    run_single_agent(name, trip_input)   -> that agent's raw output
    reconcile_and_synthesize(trip_input, outputs) -> final itinerary object
    plan(trip_input)                     -> runs everything end to end
"""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from agents import (
    activity_agent,
    budget_agent,
    food_agent,
    housing_agent,
    planning_agent,
    transportation_agent,
)
from agents.base import trip_days
from llm.deepseek_client import chat_json
from llm.easy_reading import easy_reading_enabled, with_easy_reading
from services._geography import (
    coordinates_are_tokyo_endpoint,
    destination_allows_retired_tokyo_places,
    location_allows_tokyo_airport,
    retired_tokyo_record_field,
    tokyo_endpoint_marker,
)

_AGENTS = {
    "budget": budget_agent.run,
    "transportation": transportation_agent.run,
    "housing": housing_agent.run,
    "food": food_agent.run,
    "activity": activity_agent.run,
    "planning": planning_agent.run,
}

SYNTHESIS_PROMPT = (
    "You are the Orchestrator of a multi-agent trip planner. You are given the finalized "
    "outputs of six specialist agents (transportation, housing, food per day, activities, "
    "weather, pacing). Produce a coherent day-by-day itinerary for the EXACT destination supplied. "
    "Use ONLY the supplied lodging, meals, transportation, and activities; never invent or import "
    "places from another city/country. Never repeat an activity or venue while distinct supplied "
    "choices exist. Include every requested date exactly once and no other dates. "
    "Return ONLY a JSON object with keys: "
    "summary (2-3 sentence overview of the trip), and "
    "schedule (array, one object per day, each with: day (int, 1-based), date (YYYY-MM-DD), "
    "title (short theme for the day), and items (array of {time, type, title, detail})). "
    "type is one of: arrival, departure, lodging, meal, activity. Weave meals and activities "
    "into a natural daily flow and respect the arrival/departure days."
    " For activity, meal, and lodging items, copy the supplied name EXACTLY into title so "
    "verification labels are preserved. Use at most one supplied activity per day. Assign "
    "outdoor, nature, walking, cycling, hiking, and adventure activities to the clearest supplied "
    "weather days; prefer indoor activities on rainy, snowy, stormy, or very windy days."
)


def run_single_agent(name: str, trip_input: dict) -> dict:
    if name not in _AGENTS:
        raise KeyError(f"Unknown agent: {name}")
    return _AGENTS[name](trip_input)


def with_budget_guidance(trip_input: dict, budget_output: dict) -> dict:
    """Attach internal caps without changing the public trip-input contract."""
    return {
        **trip_input,
        "_budget_caps": dict(budget_output.get("daily_caps", {})),
    }


def _normalized_location(value) -> str:
    return str(value or "").strip().casefold()


def _expect_location(agent: str, path: str, value, expected: str, role: str, route: str) -> None:
    if _normalized_location(value) != _normalized_location(expected):
        raise ValueError(
            f"{agent} Agent returned '{value}' at {path}; expected {role} "
            f"'{expected}' for the '{route}' route."
        )


def _selected_place_guard(
    agent: str,
    path: str,
    record: dict,
    destination: str,
    route: str,
    *,
    include_name: bool = True,
) -> None:
    if "destination" in record:
        _expect_location(agent, f"{path}.destination", record["destination"], destination, "destination", route)
    if destination_allows_retired_tokyo_places(destination):
        return
    retired_field = retired_tokyo_record_field(record, include_name=include_name)
    if retired_field:
        field, value = retired_field
        raise ValueError(
            f"{agent} Agent selected retired Tokyo demo data '{value}' at {path}.{field} "
            f"for the '{route}' route."
        )


def _validate_agent_geography(trip_input: dict, outputs: dict) -> None:
    destination = trip_input["location"].strip()
    origin = str(trip_input.get("origin", "")).strip()
    route = f"{origin} → {destination}"
    for agent, output in outputs.items():
        label = agent.replace("_", " ").title()
        if not isinstance(output, dict) or "destination" not in output:
            raise ValueError(
                f"{label} Agent response is missing its required destination for the "
                f"'{route}' route."
            )
        _expect_location(label, f"{agent}.destination", output["destination"], destination, "destination", route)

    transportation = outputs.get("transportation", {})
    for key in ("recommended", "route_summary"):
        record = transportation.get(key)
        if not isinstance(record, dict):
            continue
        path = f"transportation.{key}"
        if origin and "origin" in record:
            _expect_location("Transportation", f"{path}.origin", record["origin"], origin, "route origin", route)
        if "destination" in record:
            _expect_location(
                "Transportation", f"{path}.destination", record["destination"],
                destination, "destination", route,
            )
        for field, expected in (("departure_airport", origin), ("arrival_airport", destination)):
            marker = tokyo_endpoint_marker(record.get(field))
            if marker and not location_allows_tokyo_airport(expected):
                raise ValueError(
                    f"Transportation Agent returned Tokyo endpoint '{record.get(field)}' at "
                    f"{path}.{field} for the '{route}' route."
                )

    for index, point in enumerate(transportation.get("route_points", [])):
        if not isinstance(point, dict) or point.get("role") not in {"departure", "arrival"}:
            continue
        expected = origin if point["role"] == "departure" else destination
        path = f"transportation.route_points[{index}]"
        marker = tokyo_endpoint_marker(point.get("label"))
        if (
            marker
            or coordinates_are_tokyo_endpoint(point.get("lat"), point.get("lng"))
        ) and not location_allows_tokyo_airport(expected):
            raise ValueError(
                f"Transportation Agent returned a Tokyo {point['role']} point at {path} "
                f"for the '{route}' route."
            )

    housing = outputs.get("housing", {}).get("recommended")
    if isinstance(housing, dict):
        _selected_place_guard("Housing", "housing.recommended", housing, destination, route)

    for index, activity in enumerate(outputs.get("activity", {}).get("recommended", [])):
        if isinstance(activity, dict):
            _selected_place_guard(
                "Activity", f"activity.recommended[{index}]", activity, destination, route,
            )

    for day_index, day in enumerate(outputs.get("food", {}).get("daily_meals", [])):
        for meal_index, meal in enumerate(day.get("meals", []) if isinstance(day, dict) else []):
            if isinstance(meal, dict):
                _selected_place_guard(
                    "Food", f"food.daily_meals[{day_index}].meals[{meal_index}]",
                    meal, destination, route, include_name=False,
                )


def _local_transport_estimate(outputs: dict, num_days: int) -> float:
    index = outputs.get("budget", {}).get("cost_index", {})
    return round(index["daily_index"].get("local_transport", 0) * num_days, 2)


def _reconcile_budget(trip_input: dict, outputs: dict, log: list) -> dict:
    """Ensure the combined plan fits the budget; downgrade lodging if not.

    Returns the cost breakdown and mutates `outputs['housing']` / appends to `log`
    when a substitution is made.
    """
    num_days = len(trip_days(trip_input))
    total_budget = float(trip_input["budget"]["total"])
    currency = trip_input["budget"].get("currency", "USD")

    transport_cost = outputs["transportation"]["cost"]
    food_cost = outputs["food"]["cost"]
    activity_cost = outputs["activity"]["cost"]
    local_transport = _local_transport_estimate(outputs, num_days)
    fixed = transport_cost + food_cost + activity_cost + local_transport

    housing = outputs["housing"]
    housing_cost = housing["cost"]
    grand_total = fixed + housing_cost

    if grand_total > total_budget:
        overflow = grand_total - total_budget
        # Re-query the Budget Agent for tightened caps (recorded for the UI).
        outputs["budget"] = budget_agent.run(trip_input, overflow=overflow)

        # Food used to be selected independently from the displayed daily cap.
        # Re-plan it against any tightened cap before attempting a lodging downgrade.
        previous_food_cost = food_cost
        outputs["food"] = food_agent.run(with_budget_guidance(trip_input, outputs["budget"]))
        food_cost = outputs["food"]["cost"]
        fixed = transport_cost + food_cost + activity_cost + local_transport
        grand_total = fixed + housing_cost
        if food_cost < previous_food_cost:
            log.append({
                "agent": "Orchestrator",
                "note": (
                    f"Food choices were reduced from {previous_food_cost:.0f} to {food_cost:.0f} "
                    f"{currency} to obey the revised daily food cap."
                ),
            })
        overflow = max(grand_total - total_budget, 0)

        # Try to downgrade lodging: the priciest hotel that still lets the plan fit.
        nights = housing.get("nights", max(num_days - 1, 1))
        affordable = [
            o for o in housing["options"]
            if fixed + o["price_per_night"] * nights <= total_budget
        ]
        original = housing["recommended"]
        if affordable:
            substitute = max(affordable, key=lambda o: o["price_per_night"])
            if substitute["id"] != original["id"]:
                housing["recommended"] = substitute
                housing["cost"] = substitute["price_per_night"] * nights
                housing_cost = housing["cost"]
                log.append({
                    "agent": "Orchestrator",
                    "note": (
                        f"Housing Agent's first pick '{original['name']}' "
                        f"(${original['price_per_night']}/night, ${original['price_per_night'] * nights} total) "
                        f"broke the budget by ${overflow:.0f}. Substituted '{substitute['name']}' "
                        f"(${substitute['price_per_night']}/night) to fit within {total_budget:.0f} {currency}."
                    ),
                })
        else:
            # Even the cheapest lodging can't close the gap — flag it honestly.
            cheapest = min(housing["options"], key=lambda o: o["price_per_night"])
            if cheapest["id"] != original["id"]:
                housing["recommended"] = cheapest
                housing["cost"] = cheapest["price_per_night"] * nights
                housing_cost = housing["cost"]
            log.append({
                "agent": "Orchestrator",
                "note": (
                    f"Plan still exceeds the {total_budget:.0f} {currency} budget even with the "
                    f"cheapest lodging. Consider raising the budget or shortening the trip."
                ),
            })
        grand_total = fixed + housing_cost

    return {
        "currency": currency,
        "total": round(grand_total, 2),
        "budget": total_budget,
        "within_budget": grand_total <= total_budget,
        "breakdown": {
            "transportation": round(transport_cost, 2),
            "housing": round(housing_cost, 2),
            "food": round(food_cost, 2),
            "activity": round(activity_cost, 2),
            "local_transport": local_transport,
        },
    }


def _map_points(outputs: dict) -> list:
    points = []
    h = outputs["housing"]["recommended"]
    if "lat" in h:
        points.append({"label": h["name"], "type": "housing", "area": h.get("area"),
                       "lat": h["lat"], "lng": h["lng"]})
    for a in outputs["activity"]["recommended"]:
        if "lat" in a:
            points.append({"label": a["name"], "type": "activity", "area": a.get("area"),
                           "lat": a["lat"], "lng": a["lng"]})
    return points


OUTDOOR_ACTIVITY_MARKERS = {
    "adventure", "bike", "cycling", "garden", "hike", "hiking", "nature", "outdoor",
    "park", "trail", "walking", "waterfront",
}


def _activity_is_outdoor(activity: dict) -> bool:
    values = [activity.get("name", ""), activity.get("style", ""), *(activity.get("tags") or [])]
    content = " ".join(str(value) for value in values).casefold()
    return any(marker in content for marker in OUTDOOR_ACTIVITY_MARKERS)


def _weather_score(day: dict) -> tuple:
    """Lower values indicate a better day for an outdoor activity."""
    condition = str(day.get("condition", "")).casefold()
    severity = 1 if any(
        marker in condition for marker in ("thunder", "hail", "heavy", "freezing")
    ) else 0
    return (
        severity,
        float(day.get("rain_chance") or 0),
        float(day.get("precipitation_mm") or 0),
        float(day.get("snowfall_cm") or 0),
        float(day.get("wind_speed_max_kmh") or 0),
        day.get("date", ""),
    )


def _weather_activity_assignment(days: list[str], activities: list[dict], weather: list[dict]) -> dict:
    """Map outdoor activities to the best weather dates and indoor activities to the rest."""
    activities = activities[:len(days)]
    weather_by_date = {day.get("date"): day for day in weather}
    ranked_days = sorted(days, key=lambda value: _weather_score(weather_by_date.get(value, {"date": value})))
    outdoor = [activity for activity in activities if _activity_is_outdoor(activity)]
    indoor = [activity for activity in activities if not _activity_is_outdoor(activity)]

    assignment = {}
    for activity, activity_date in zip(outdoor, ranked_days):
        assignment[activity_date] = activity
    remaining_days = [value for value in days if value not in assignment]
    for activity, activity_date in zip(indoor, remaining_days):
        assignment[activity_date] = activity
    return assignment


def _weather_detail(day: dict | None) -> str:
    if not day:
        return ""
    try:
        rain = f"{round(float(day.get('rain_chance', 0)) * 100):.0f}% rain"
        temperatures = f"{day['low_c']:.0f}–{day['high_c']:.0f}°C"
    except (KeyError, TypeError, ValueError):
        return ""
    label = "seasonal estimate" if day.get("source") == "deepseek_seasonal_estimate" else "forecast"
    return f"Weather ({label}): {day.get('condition', 'conditions vary')}, {temperatures}, {rain}."


def _apply_weather_activity_order(synth: dict, trip_input: dict, outputs: dict) -> None:
    """Enforce weather-aware activity placement for both LLM and fallback schedules."""
    days = trip_days(trip_input)
    activities = outputs["activity"]["recommended"]
    weather = outputs["planning"].get("daily_weather", [])
    assignment = _weather_activity_assignment(days, activities, weather)
    activity_records = {activity["name"].strip().casefold(): activity for activity in activities}
    weather_by_date = {day.get("date"): day for day in weather}

    existing_items = {}
    slots = {}
    for day in synth["schedule"]:
        retained = []
        for item in day.get("items", []):
            if item.get("type") == "activity":
                existing_items[item.get("title", "").strip().casefold()] = item
                slots.setdefault(day.get("date"), len(retained))
            else:
                retained.append(item)
        day["items"] = retained

    for day in synth["schedule"]:
        activity = assignment.get(day.get("date"))
        if not activity:
            continue
        key = activity["name"].strip().casefold()
        item = dict(existing_items.get(key) or {
            "time": "10:30",
            "type": "activity",
            "title": activity["name"],
            "detail": f"{activity.get('style', 'activity')} · {activity.get('duration', '')} · "
                      f"{activity.get('area', '')}",
        })
        # Preserve the exact supplied name even if the synthesizer changed capitalization.
        item["title"] = activity_records[key]["name"]
        weather_note = _weather_detail(weather_by_date.get(day.get("date")))
        if weather_note and "Weather (" not in str(item.get("detail", "")):
            item["detail"] = f"{str(item.get('detail', '')).strip()} {weather_note}".strip()
        slot = min(slots.get(day.get("date"), len(day["items"])), len(day["items"]))
        day["items"].insert(slot, item)


def _fallback_schedule(trip_input: dict, outputs: dict) -> dict:
    days = trip_days(trip_input)
    activities = outputs["activity"]["recommended"]
    activity_by_date = _weather_activity_assignment(
        days, activities, outputs["planning"].get("daily_weather", [])
    )
    meals_by_day = {d["date"]: d for d in outputs["food"]["daily_meals"]}
    housing = outputs["housing"]["recommended"]
    transport = outputs["transportation"]["recommended"]

    schedule = []
    for i, date in enumerate(days):
        items = []
        if i == 0:
            items.append({"time": "Morning", "type": "arrival",
                          "title": f"Arrive via {transport['carrier']}",
                          "detail": f"Land at {transport.get('arrival_airport', 'the airport')}, "
                                    f"check in at {housing['name']} ({housing.get('area', '')})."})
        day_meals = meals_by_day.get(date, {}).get("meals", [])
        act = activity_by_date.get(date)
        if day_meals:
            items.append({"time": "08:30", "type": "meal", "title": day_meals[0]["name"],
                          "detail": f"{day_meals[0]['cuisine']} in {day_meals[0]['area']}"})
        if act:
            items.append({"time": "10:30", "type": "activity", "title": act["name"],
                          "detail": f"{act['style']} · {act.get('duration', '')} · {act.get('area', '')}"})
        if len(day_meals) > 1:
            items.append({"time": "13:00", "type": "meal", "title": day_meals[1]["name"],
                          "detail": f"{day_meals[1]['cuisine']} in {day_meals[1]['area']}"})
        if len(day_meals) > 2:
            items.append({"time": "19:00", "type": "meal", "title": day_meals[2]["name"],
                          "detail": f"{day_meals[2]['cuisine']} in {day_meals[2]['area']}"})
        if i == len(days) - 1:
            items.append({"time": "Evening", "type": "departure",
                          "title": f"Depart via {transport['carrier']}",
                          "detail": "Head to the airport for your return flight."})
        schedule.append({"day": i + 1, "date": date,
                         "title": act["name"] if act else "Explore", "items": items})

    return {
        "summary": (
            f"A {len(days)}-day trip to {trip_input['location']} staying at {housing['name']}, "
            f"balancing {outputs['planning']['weather_summary']}"
        ),
        "schedule": schedule,
    }


def _valid_synthesis(trip_input: dict, synth: dict | None, outputs: dict) -> bool:
    if not isinstance(synth, dict) or not isinstance(synth.get("schedule"), list):
        return False
    days = trip_days(trip_input)
    schedule = synth["schedule"]
    if len(schedule) != len(days):
        return False
    if [day.get("date") for day in schedule] != days:
        return False
    allowed_activities = {
        activity["name"].strip().casefold()
        for activity in outputs["activity"]["recommended"]
    }
    allowed_meals = {
        meal["name"].strip().casefold()
        for daily in outputs["food"]["daily_meals"]
        for meal in daily["meals"]
    }
    allowed_lodging = outputs["housing"]["recommended"]["name"].strip().casefold()
    activity_titles = []
    lodging_titles = []
    allowed_item_types = {"arrival", "departure", "lodging", "meal", "activity"}
    for day in schedule:
        if not isinstance(day.get("items"), list):
            return False
        for item in day["items"]:
            item_type = item.get("type")
            if item_type not in allowed_item_types:
                return False
            if (
                not destination_allows_retired_tokyo_places(trip_input["location"])
                and retired_tokyo_record_field({"name": item.get("title")})
            ):
                return False
            if item_type == "activity":
                title = str(item.get("title", "")).strip().casefold()
                if not title or title not in allowed_activities:
                    return False
                activity_titles.append(title)
            if item_type == "meal":
                title = str(item.get("title", "")).strip().casefold()
                if not title or title not in allowed_meals:
                    return False
            if item_type == "lodging":
                title = str(item.get("title", "")).strip().casefold()
                if not title or title != allowed_lodging:
                    return False
                lodging_titles.append(title)
    if len(activity_titles) != min(len(days), len(allowed_activities)):
        return False
    if len(activity_titles) != len(set(activity_titles)):
        return False
    if not lodging_titles:
        return False
    return True


def reconcile_and_synthesize(trip_input: dict, outputs: dict) -> dict:
    _validate_agent_geography(trip_input, outputs)
    reasoning_log = []
    # Capture each agent's own reasoning for the audit trail.
    label = {"budget": "Budget", "transportation": "Transportation", "housing": "Housing",
             "food": "Food", "activity": "Activity", "planning": "Planning"}
    for key, name in label.items():
        note = outputs.get(key, {}).get("reasoning")
        if note:
            reasoning_log.append({"agent": name, "note": note})
    for w in outputs.get("budget", {}).get("warnings", []):
        reasoning_log.append({"agent": "Budget", "note": f"⚠ {w}"})

    cost = _reconcile_budget(trip_input, outputs, reasoning_log)
    # Budget reconciliation can regenerate Budget/Food output, so validate the
    # final set rather than relying only on the pre-reconciliation check.
    _validate_agent_geography(trip_input, outputs)
    for warning in outputs.get("budget", {}).get("warnings", []):
        entry = {"agent": "Budget", "note": f"⚠ {warning}"}
        if entry not in reasoning_log:
            reasoning_log.append(entry)

    # One DeepSeek synthesis call for the day-by-day schedule (with deterministic fallback).
    synth = None
    try:
        payload = {
            "destination": trip_input["location"],
            "strict_destination_rule": (
                f"Every place must be in {trip_input['location']} or a clearly identified day trip "
                f"departing from {trip_input['location']}. Do not use any other destination's data."
            ),
            "dates": trip_input["dates"],
            "arrival": outputs["transportation"]["recommended"],
            "lodging": outputs["housing"]["recommended"],
            "daily_meals": outputs["food"]["daily_meals"],
            "activities": outputs["activity"]["recommended"],
            "daily_weather": outputs["planning"].get("daily_weather", []),
            "pacing_notes": outputs["planning"]["pacing_notes"],
        }
        synthesis_prompt = with_easy_reading(SYNTHESIS_PROMPT, easy_reading_enabled(trip_input))
        synth = chat_json(synthesis_prompt, json.dumps(payload, ensure_ascii=False), temperature=0.5)
        if not _valid_synthesis(trip_input, synth, outputs):
            synth = None
    except Exception:
        synth = None
    if synth is None:
        synth = _fallback_schedule(trip_input, outputs)
    _apply_weather_activity_order(synth, trip_input, outputs)

    return {
        "destination": trip_input["location"],
        "dates": trip_input["dates"],
        "summary": synth.get("summary", ""),
        "schedule": synth["schedule"],
        "cost": cost,
        "map_points": _map_points(outputs),
        "packing_list": outputs["planning"]["packing_list"],
        "weather_summary": outputs["planning"]["weather_summary"],
        "daily_weather": outputs["planning"].get("daily_weather", []),
        "pacing_notes": outputs["planning"]["pacing_notes"],
        "weather_source": outputs["planning"].get("weather_source"),
        "weather_location": outputs["planning"].get("weather_location"),
        "reasoning_log": reasoning_log,
        "agent_outputs": outputs,
        "verification_notice": (
            "Travel data is AI-generated planning guidance, not live inventory. Verify prices, "
            "availability, opening hours, visas, transport schedules, and bookings before travel."
        ),
    }


def plan(trip_input: dict) -> dict:
    """Set budget caps first, then run the five recommendation agents concurrently."""
    outputs = {"budget": budget_agent.run(trip_input)}
    guided_input = with_budget_guidance(trip_input, outputs["budget"])
    remaining_agents = {name: agent for name, agent in _AGENTS.items() if name != "budget"}
    with ThreadPoolExecutor(max_workers=len(remaining_agents)) as executor:
        futures = {
            executor.submit(agent, guided_input): name
            for name, agent in remaining_agents.items()
        }
        for future in as_completed(futures):
            outputs[futures[future]] = future.result()
    return reconcile_and_synthesize(trip_input, outputs)
