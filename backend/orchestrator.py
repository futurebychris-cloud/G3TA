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
    "verification labels are preserved. Use at most one supplied activity per day."
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


LEGACY_TOKYO_MARKERS = {
    "tokyo", "asakusa", "shibuya", "ginza", "shinjuku", "akihabara",
    "senso-ji", "nrt", "haneda", "mt. fuji", "hakone", "teamlab planets",
}


def _has_legacy_tokyo_content(value, destination: str) -> bool:
    destination_text = destination.casefold()
    if "tokyo" in destination_text or "japan" in destination_text:
        return False
    serialized = json.dumps(value, ensure_ascii=False).casefold()
    return any(marker in serialized for marker in LEGACY_TOKYO_MARKERS)


def _validate_agent_geography(trip_input: dict, outputs: dict) -> None:
    destination = trip_input["location"].strip()
    for agent, output in outputs.items():
        output_destination = str(output.get("destination", destination)).strip()
        if output_destination.casefold() != destination.casefold():
            raise ValueError(
                f"{agent.title()} Agent returned data for '{output_destination}' instead of '{destination}'."
            )
    if _has_legacy_tokyo_content(outputs, destination):
        raise ValueError(
            f"Geography guard rejected stale Tokyo/Japan data for a {destination} trip. Please retry."
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


def _fallback_schedule(trip_input: dict, outputs: dict) -> dict:
    days = trip_days(trip_input)
    activities = outputs["activity"]["recommended"]
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
        act = activities[i] if i < len(activities) else None
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
    activity_titles = []
    for day in schedule:
        if not isinstance(day.get("items"), list):
            return False
        for item in day["items"]:
            if item.get("type") == "activity":
                title = str(item.get("title", "")).strip().casefold()
                if not title or title not in allowed_activities:
                    return False
                activity_titles.append(title)
            if item.get("type") == "meal":
                title = str(item.get("title", "")).strip().casefold()
                if not title or title not in allowed_meals:
                    return False
    if len(activity_titles) != min(len(days), len(allowed_activities)):
        return False
    if len(activity_titles) != len(set(activity_titles)):
        return False
    return not _has_legacy_tokyo_content(synth, trip_input["location"])


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
        synth = chat_json(SYNTHESIS_PROMPT, json.dumps(payload, ensure_ascii=False), temperature=0.5)
        if not _valid_synthesis(trip_input, synth, outputs):
            synth = None
    except Exception:
        synth = None
    if synth is None:
        synth = _fallback_schedule(trip_input, outputs)

    return {
        "destination": trip_input["location"],
        "dates": trip_input["dates"],
        "summary": synth.get("summary", ""),
        "schedule": synth["schedule"],
        "cost": cost,
        "map_points": _map_points(outputs),
        "packing_list": outputs["planning"]["packing_list"],
        "weather_summary": outputs["planning"]["weather_summary"],
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
