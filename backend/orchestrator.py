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
import re
from concurrent.futures import ThreadPoolExecutor

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
from booking.shared_db import init_shared_db, save_trip

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
    """Inject budget agent's daily caps as guidance for other agents.

    Each agent reads `_budget_caps` to stay within its allocated daily limit.
    The budget_agent output may also contain neural_network allocations.
    """
    guided = dict(trip_input)
    daily_caps = budget_output.get("daily_caps", {})
    # Use neural network allocation if available, otherwise budget agent caps
    if "neural_allocation" in budget_output:
        neural = budget_output["neural_allocation"]
        daily_caps = neural.get("daily_caps", daily_caps)
    guided["_budget_caps"] = daily_caps
    guided["_budget_ratios"] = budget_output.get("ratios", {})
    guided["_cost_index"] = budget_output.get("cost_index", {})
    return guided


def prepare_trip_input(trip_input: dict) -> dict:
    """Create the stable trip id used by every agent and persist trip metadata."""
    import hashlib

    prepared = {**trip_input}
    trip_id = prepared.get("trip_id") or hashlib.sha256(
        f"{prepared['location']}{prepared['dates']['start']}{prepared.get('origin', '')}".encode()
    ).hexdigest()[:12]
    prepared["trip_id"] = trip_id
    init_shared_db()
    save_trip(
        trip_id=trip_id,
        location=prepared["location"],
        origin=prepared.get("origin", ""),
        start_date=prepared["dates"]["start"],
        end_date=prepared["dates"]["end"],
        total_budget=float(prepared["budget"]["total"]),
        currency=prepared["budget"].get("currency", "CNY"),
    )
    return prepared


LEGACY_TOKYO_MARKERS = {
    "tokyo", "asakusa", "shibuya", "ginza", "shinjuku", "akihabara",
    "senso-ji", "nrt", "haneda", "mt. fuji", "hakone", "teamlab planets",
}

# Only values in fields that actually describe geography belong in the legacy
# data guard. Preferences and prose may legitimately contain words such as
# "Japanese" or the name of a restaurant such as "Tokyo Sushi" in another city.
_GEOGRAPHY_FIELDS = {
    "airport",
    "arrival_airport",
    "departure_airport",
    "area",
    "city",
    "country",
    "destination",
    "from",
    "location",
    "origin",
    "to",
    "weather_location",
}


def _geography_values(value) -> list[str]:
    evidence: list[str] = []

    def collect(item, *, geographic: bool = False) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                collect(child, geographic=geographic or str(key).casefold() in _GEOGRAPHY_FIELDS)
        elif isinstance(item, list):
            for child in item:
                collect(child, geographic=geographic)
        elif geographic and item is not None:
            evidence.append(str(item))

    collect(value)
    return evidence


def _contains_marker(text: str, marker: str) -> bool:
    # Token boundaries are essential: "japan" must not match "Japanese".
    return re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", text, re.IGNORECASE) is not None


def _has_legacy_tokyo_content(value, destination: str) -> bool:
    destination_text = destination.casefold()
    if _contains_marker(destination_text, "tokyo") or _contains_marker(destination_text, "japan"):
        return False
    geographic_text = "\n".join(_geography_values(value)).casefold()
    return any(_contains_marker(geographic_text, marker) for marker in LEGACY_TOKYO_MARKERS)


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


def _reconcile_budget(trip_input: dict, outputs: dict, log: list) -> dict:
    """Reconcile real agent costs into a unified budget breakdown.

    Key design decision (v2.1): The budget breakdown uses REAL costs from each
    specialist agent (transport, housing, food, activity), NOT the budget agent's
    theoretical allocations. The budget agent's pie_data is still used for the
    ring chart, and its allocations serve as a reference for overflow detection.

    Returns: {currency, total, budget, within_budget, breakdown, pie_data,
              allocations, expense_items}
    """
    num_days = len(trip_days(trip_input))
    total_budget = float(trip_input["budget"]["total"])
    currency = trip_input["budget"].get("currency", "USD")

    # ---- Step 0: Check for scraping failures ----
    transport_agent = outputs.get("transportation", {})
    scrape_status = transport_agent.get("scrape_status", "ok")
    transport_errors = transport_agent.get("errors", [])

    if scrape_status == "failed":
        log.append({
            "agent": "Transportation",
            "note": (
                f"⚠ ALL transport scraping FAILED. No real prices available. "
                f"Errors: {'; '.join(transport_errors[:3])}. "
                f"The cost breakdown EXCLUDES transportation — you MUST book "
                f"transport separately. Try again or check Ctrip/12306 manually."
            ),
        })
    elif scrape_status == "partial":
        log.append({
            "agent": "Transportation",
            "note": (
                f"⚠ Partial transport data: some sources failed. "
                f"{'; '.join(transport_errors[:2])}. "
                f"Prices shown are from the working source only."
            ),
        })

    # ---- Step 1: Extract REAL costs from each agent ----
    # Transport (intercity flights/trains)
    transport_cost = float(transport_agent.get("cost", 0) or 0)
    transport_recommended = transport_agent.get("recommended", {})

    # Fallback: if transport scraping failed, estimate from city distance
    if transport_cost <= 0:
        origin = trip_input.get("origin", "")
        dest = trip_input["location"]
        if origin and dest:
            try:
                from services.gaode_service import city_distance_km, CITY_COST_KM
                dist = city_distance_km(origin, dest)
                transport_cost = round(dist * CITY_COST_KM, 2)
                log.append({
                    "agent": "Transportation",
                    "note": (
                        f"Transport scraping unavailable — estimated {currency} {transport_cost:,.0f} "
                        f"based on ~{dist:.0f}km distance ({CITY_COST_KM} {currency}/km)."
                    ),
                })
            except Exception:
                # Hard fallback: 600 CNY for domestic China routes
                transport_cost = 600.0
                log.append({
                    "agent": "Transportation",
                    "note": "Transport cost estimated at 600 CNY (scraping unavailable).",
                })

    # Local transport
    local_transport = float(transport_agent.get("local_transport_cost", 0) or 0)
    if local_transport <= 0:
        # fallback: use budget agent's daily estimate OR tier-based
        index = outputs.get("budget", {}).get("cost_index", {})
        daily_idx = index.get("daily_index", {}) if index else {}
        local_transport = round(float(daily_idx.get("local_transport", 30)) * num_days, 2)
        if local_transport <= 0:
            local_transport = round(30.0 * num_days, 2)  # hard floor

    # Housing — use the REAL scraped price; only guard against absurd scraping
    # artifacts (>= 100k CNY/night) by swapping to the cheapest real-priced option.
    housing_agent = outputs.get("housing", {})
    housing_cost = housing_agent.get("cost")
    h_rec = housing_agent.get("recommended") or {}
    nights = max(num_days - 1, 1)

    _MAX_REALISTIC_PRICE_PER_NIGHT = 100000  # safety net for scraping artifacts only
    price_per = h_rec.get("price_per_night") if isinstance(h_rec, dict) else None
    if price_per and float(price_per) > _MAX_REALISTIC_PRICE_PER_NIGHT:
        log.append({
            "agent": "Orchestrator",
            "note": (
                f"Filtered an absurd Ctrip price for {h_rec.get('name', 'hotel')} "
                f"({currency} {float(price_per):,.0f}/night — clearly a scraping artifact). "
                f"Swapped to the cheapest real-priced option."
            ),
        })
        options = housing_agent.get("options", []) or []
        valid_opts = [
            o for o in options
            if o.get("price_per_night") and 0 < float(o["price_per_night"]) < _MAX_REALISTIC_PRICE_PER_NIGHT
        ]
        if valid_opts:
            h_rec = min(valid_opts, key=lambda o: o["price_per_night"])
            housing_agent["recommended"] = h_rec
            price_per = h_rec.get("price_per_night")

    if housing_cost is None or (isinstance(housing_cost, (int, float)) and housing_cost > _MAX_REALISTIC_PRICE_PER_NIGHT * nights):
        if price_per:
            housing_cost = float(price_per) * nights
        else:
            # No real price available — be honest, do NOT fabricate an estimate.
            housing_cost = 0.0
            log.append({
                "agent": "Orchestrator",
                "note": (
                    "未获取到真实房价，住宿费用暂不计入预算，请到携程平台核实真实价格后再预订。"
                ),
            })
    housing_cost = float(housing_cost)

    # Food
    food_agent_out = outputs.get("food", {})
    food_cost = float(food_agent_out.get("cost", 0) or 0)
    # If food cost is unreasonably high (>5000/day), cap it
    if food_cost > 5000 * num_days:
        food_cost = 500 * num_days  # reasonable CNY estimate
        log.append({
            "agent": "Orchestrator",
            "note": f"Food cost capped at {currency} 500/day (unrealistic input detected).",
        })

    # Activity
    activity_agent_out = outputs.get("activity", {})
    activity_cost = float(activity_agent_out.get("cost", 0) or 0)

    # Shopping — derived from Numbeo cost index (real data, not LLM)
    shopping_cost = 0.0
    budget_cost_idx = outputs.get("budget", {}).get("cost_index", {})
    shopping_daily_idx = budget_cost_idx.get("daily_index", {}) if budget_cost_idx else {}
    shopping_daily = float(shopping_daily_idx.get("shopping", 0) or 0)
    if shopping_daily > 0:
        shopping_cost = round(shopping_daily * num_days, 2)
    else:
        # Fallback: 10% of remaining daily budget
        remaining_daily = max(total_budget - transport_cost, 0) / max(num_days, 1)
        shopping_cost = round(remaining_daily * 0.10 * num_days, 2)

    # ---- Step 2: Build expense line items for frontend ----
    expense_items = []
    if transport_cost > 0:
        expense_items.append({
            "category": "transportation", "label": "Intercity transport",
            "detail": f"{transport_recommended.get('carrier', '')} "
                      f"{transport_recommended.get('flight_number', transport_recommended.get('train_number', ''))} "
                      f"{transport_recommended.get('from', '')} → {transport_recommended.get('to', '')}",
            "amount": round(transport_cost, 2), "currency": currency,
        })
    if housing_cost > 0:
        h_rec = housing_agent.get("recommended") or {}
        nights = max(num_days - 1, 1)
        expense_items.append({
            "category": "housing", "label": "Accommodation",
            "detail": f"{h_rec.get('name', 'Hotel')} × {nights} nights",
            "amount": round(housing_cost, 2), "currency": currency,
        })
    if food_cost > 0:
        expense_items.append({
            "category": "food", "label": "Food & dining",
            "detail": f"{num_days} days of meals",
            "amount": round(food_cost, 2), "currency": currency,
        })
    if activity_cost > 0:
        act_recs = activity_agent_out.get("recommended", [])
        act_names = ", ".join(a.get("name", "") for a in (act_recs or [])[:3])
        expense_items.append({
            "category": "activity", "label": "Activities & experiences",
            "detail": act_names if act_names else f"{len(act_recs or [])} activities",
            "amount": round(activity_cost, 2), "currency": currency,
        })
    if local_transport > 0:
        expense_items.append({
            "category": "local_transport", "label": "Local transport",
            "detail": f"{num_days} days (metro, taxi, bus)",
            "amount": round(local_transport, 2), "currency": currency,
        })
    if shopping_cost > 0:
        # Get shopping insights from cultural fashion service
        shop_detail = f"{num_days} days (souvenirs, markets, local shopping)"
        try:
            from services.numbeo_service import get_shopping_guide
            guide = get_shopping_guide(trip_input["location"])
            shop_detail = f"{num_days} days — {guide.get('note', 'souvenirs & local markets')}"
        except Exception:
            pass
        expense_items.append({
            "category": "shopping", "label": "Shopping & souvenirs",
            "detail": shop_detail,
            "amount": round(shopping_cost, 2), "currency": currency,
        })

    # ---- Step 3: Grand total & overflow check ----
    grand_total = transport_cost + housing_cost + food_cost + activity_cost + local_transport + shopping_cost

    if grand_total > total_budget:
        overflow = grand_total - total_budget
        log.append({
            "agent": "Orchestrator",
            "note": (
                f"Plan costs {currency} {grand_total:,.0f}, exceeding "
                f"{total_budget:,.0f} budget by {overflow:,.0f}. "
                f"Consider downgrading housing or reducing activities."
            ),
        })

        # Try to downgrade lodging
        nights = max(num_days - 1, 1)
        options = housing_agent.get("options", [])
        affordable = [
            o for o in options
            if o.get("price_per_night") is not None
            and (grand_total - housing_cost + o["price_per_night"] * nights) <= total_budget
        ]
        if affordable:
            substitute = max(affordable, key=lambda o: o["price_per_night"])
            original = housing_agent.get("recommended") or {}
            if original and substitute.get("id") != original.get("id"):
                housing_agent["recommended"] = substitute
                housing_cost = substitute["price_per_night"] * nights
                housing_agent["cost"] = housing_cost
                # Update expense item
                for item in expense_items:
                    if item["category"] == "housing":
                        item["amount"] = round(housing_cost, 2)
                        item["detail"] = f"{substitute.get('name', 'Hotel')} × {nights} nights"
                grand_total = transport_cost + housing_cost + food_cost + activity_cost + local_transport
                log.append({
                    "agent": "Orchestrator",
                    "note": (
                        f"Downgraded housing from '{original.get('name', 'unknown')}' "
                        f"to '{substitute['name']}' ({currency} {substitute['price_per_night']}/night) "
                        f"to fit budget."
                    ),
                })
        else:
            priced = [o for o in options if o.get("price_per_night") is not None]
            if priced:
                cheapest = min(priced, key=lambda o: o["price_per_night"])
                housing_agent["recommended"] = cheapest
                housing_cost = cheapest["price_per_night"] * nights
                housing_agent["cost"] = housing_cost
                grand_total = transport_cost + housing_cost + food_cost + activity_cost + local_transport
            log.append({
                "agent": "Orchestrator",
                "note": (
                    f"Plan still exceeds {total_budget:.0f} {currency} budget even with "
                    f"cheapest lodging. Consider raising budget or shortening trip."
                ),
            })

    # ---- Step 4: Build return value ----
    budget_agent_out = outputs.get("budget", {})
    budget_alloc = budget_agent_out.get("allocations", {})

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
            "local_transport": round(local_transport, 2),
            "shopping": round(shopping_cost, 2),
        },
        "pie_data": budget_agent_out.get("pie_data", []),
        "allocations": budget_alloc if budget_alloc else {},
        "expense_items": expense_items,
    }


def _legacy_local_transport(outputs: dict, num_days: int) -> float:
    index = outputs.get("budget", {}).get("cost_index", {})
    daily = index.get("daily_index", {}) if index else {}
    return round(daily.get("local_transport", 0) * num_days, 2)


def _map_points(outputs: dict, destination: str = "") -> list:
    points = []
    city = destination or outputs.get("activity", {}).get("destination", "")

    # Get city center coordinates first (fallback for any missing lat/lng)
    city_center = None
    if city:
        try:
            from services.gaode_service import geocode_city
            city_center = geocode_city(city)
        except Exception:
            pass

    # ---- Housing ----
    h = outputs["housing"].get("recommended", {})
    if h and h.get("name"):
        # If no lat/lng, try to geocode the hotel name
        if not ("lat" in h and h.get("lat") and "lng" in h and h.get("lng")):
            try:
                from services.gaode_service import geocode_poi
                coords = geocode_poi(h.get("name", ""), city)
                if coords:
                    h["lat"] = coords[0]
                    h["lng"] = coords[1]
                elif city_center:
                    h["lat"] = city_center[0]
                    h["lng"] = city_center[1]
            except Exception:
                if city_center:
                    h["lat"] = city_center[0]
                    h["lng"] = city_center[1]

        if "lat" in h and h.get("lat") and h.get("lng"):
            images = h.get("images", [])
            points.append({
                "label": h["name"], "type": "housing", "area": h.get("area", city),
                "lat": h["lat"], "lng": h["lng"],
                "image": images[0] if images else None,
                "description": h.get("description", ""),
                "star_rating": h.get("star_rating"),
                "url": h.get("url", ""),
            })

    # ---- Activities (geocode if needed) ----
    activities = outputs["activity"].get("recommended", [])
    if activities:
        try:
            from services.gaode_service import geocode_activities
            geocode_activities(activities, city)
        except Exception as e:
            print(f"[orchestrator] activity geocoding failed (non-fatal): {e}")

        for a in activities:
            # If still no lat/lng after geocoding, use city center
            if not ("lat" in a and a.get("lat") and "lng" in a and a.get("lng")):
                if city_center:
                    a["lat"] = city_center[0]
                    a["lng"] = city_center[1]
                else:
                    continue  # skip this activity entirely

            act_images = a.get("images", [])
            points.append({
                "label": a["name"], "type": "activity",
                "area": a.get("area", a.get("location", city)),
                "lat": a["lat"], "lng": a["lng"],
                "image": act_images[0] if act_images else (a.get("image_url") or None),
                "description": a.get("description", ""),
                "ticket_price": a.get("ticket_price"),
                "url": a.get("url", ""),
            })

    # ---- Transport (airport/station) ----
    transport_rec = outputs["transportation"].get("recommended", {})
    if transport_rec:
        from_loc = transport_rec.get("from", "")
        to_loc = transport_rec.get("to", "")
        for loc_name in [from_loc, to_loc]:
            if not loc_name:
                continue
            try:
                from services.gaode_service import geocode_city
                coords = geocode_city(loc_name)
                if coords:
                    points.append({
                        "label": f"{loc_name} (Station/Airport)",
                        "type": "transport",
                        "area": loc_name,
                        "lat": coords[0],
                        "lng": coords[1],
                        "description": f"{transport_rec.get('carrier', 'Transport')} {transport_rec.get('flight_number', transport_rec.get('train_number', ''))}",
                        "url": "",
                    })
            except Exception:
                pass

    # ---- Fallback: always show city center if no points at all ----
    if len(points) == 0 and city_center:
        points.append({
            "label": city, "type": "activity", "area": city,
            "lat": city_center[0], "lng": city_center[1],
            "description": "City center",
        })

    return points


def _meal_title(meal: dict) -> str:
    """v1 uses 'name' for restaurant; v2 uses 'name' for dish + 'restaurant' for venue."""
    return meal.get("restaurant", meal.get("name", ""))

def _meal_area(meal: dict) -> str:
    return meal.get("area", meal.get("restaurant_location", ""))

def _meal_detail(meal: dict) -> str:
    dish = meal.get("dish_category", "") or meal.get("name", "")
    cuisine = meal.get("cuisine", "")
    area = _meal_area(meal)
    return f"{cuisine} {dish} in {area}".strip()


OUTDOOR_ACTIVITY_MARKERS = {
    "adventure", "bike", "cycling", "garden", "hike", "hiking", "nature", "outdoor",
    "park", "trail", "walking", "waterfront",
}


def _activity_is_outdoor(activity: dict) -> bool:
    values = [activity.get("name", ""), activity.get("style", activity.get("type", "")),
              *(activity.get("tags") or [])]
    content = " ".join(str(value) for value in values).casefold()
    return any(marker in content for marker in OUTDOOR_ACTIVITY_MARKERS)


def _weather_score(day: dict) -> tuple:
    """Lower values indicate a safer day for an outdoor activity."""
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
    """Place outdoor activities on the clearest available dates."""
    activities = activities[:len(days)]
    weather_by_date = {day.get("date"): day for day in weather}
    ranked_days = sorted(
        days,
        key=lambda value: _weather_score(weather_by_date.get(value, {"date": value})),
    )
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
        temperatures = f"{float(day['low_c']):.0f}–{float(day['high_c']):.0f}°C"
    except (KeyError, TypeError, ValueError):
        return ""
    label = "seasonal estimate" if day.get("source") == "deepseek_seasonal_estimate" else "forecast"
    return f"Weather ({label}): {day.get('condition', 'conditions vary')}, {temperatures}, {rain}."


def _apply_weather_activity_order(synth: dict, trip_input: dict, outputs: dict) -> None:
    """Enforce weather-aware activity placement for LLM and fallback schedules."""
    days = trip_days(trip_input)
    activities = outputs.get("activity", {}).get("recommended", [])
    weather = outputs.get("planning", {}).get("daily_weather", [])
    assignment = _weather_activity_assignment(days, activities, weather)
    activity_records = {
        activity["name"].strip().casefold(): activity
        for activity in activities
        if activity.get("name")
    }
    weather_by_date = {day.get("date"): day for day in weather}

    existing_items = {}
    slots = {}
    for day in synth.get("schedule", []):
        retained = []
        for item in day.get("items", []):
            if item.get("type") == "activity":
                existing_items[str(item.get("title", "")).strip().casefold()] = item
                slots.setdefault(day.get("date"), len(retained))
            else:
                retained.append(item)
        day["items"] = retained

    for day in synth.get("schedule", []):
        activity = assignment.get(day.get("date"))
        if not activity:
            continue
        key = activity["name"].strip().casefold()
        item = dict(existing_items.get(key) or {
            "time": activity.get("start_time", "10:30"),
            "type": "activity",
            "title": activity["name"],
            "detail": (
                f"{activity.get('style', activity.get('type', 'activity'))} · "
                f"{activity.get('duration', '')} · "
                f"{activity.get('area', activity.get('location', ''))}"
            ).strip(" ·"),
        })
        item["title"] = activity_records[key]["name"]
        weather_note = _weather_detail(weather_by_date.get(day.get("date")))
        if weather_note and "Weather (" not in str(item.get("detail", "")):
            item["detail"] = f"{str(item.get('detail', '')).strip()} {weather_note}".strip()
        slot = min(slots.get(day.get("date"), len(day["items"])), len(day["items"]))
        day["items"].insert(slot, item)


def _fallback_schedule(trip_input: dict, outputs: dict) -> dict:
    days = trip_days(trip_input)
    activities = outputs["activity"]["recommended"]
    meals_by_day = {d["date"]: d for d in outputs["food"]["daily_meals"]}
    housing = outputs["housing"]["recommended"]
    transport = outputs["transportation"]["recommended"] or {}

    schedule = []
    for i, date in enumerate(days):
        items = []
        if i == 0:
            carrier = transport.get("carrier", "Flight")
            from_loc = transport.get("from", trip_input.get("origin", ""))
            hotel_name = housing.get("name", "your hotel") if housing else "your hotel"
            items.append({"time": "Morning", "type": "arrival",
                          "title": f"Arrive via {carrier}",
                          "detail": f"{f'From {from_loc}. ' if from_loc else ''}"
                                    f"Check in at {hotel_name}."})
        day_meals = meals_by_day.get(date, {}).get("meals", [])
        act = activities[i] if i < len(activities) else None
        if day_meals:
            items.append({"time": "08:30", "type": "meal", "title": _meal_title(day_meals[0]),
                          "detail": _meal_detail(day_meals[0])})
        if act:
            act_style = act.get("style", act.get("type", ""))
            act_area = act.get("area", act.get("location", ""))
            items.append({"time": "10:30", "type": "activity", "title": act["name"],
                          "detail": f"{act_style} · {act.get('duration', '')} · {act_area}".strip(" ·")})
        if len(day_meals) > 1:
            items.append({"time": "13:00", "type": "meal", "title": _meal_title(day_meals[1]),
                          "detail": _meal_detail(day_meals[1])})
        if len(day_meals) > 2:
            items.append({"time": "19:00", "type": "meal", "title": _meal_title(day_meals[2]),
                          "detail": _meal_detail(day_meals[2])})
        if i == len(days) - 1:
            items.append({"time": "Evening", "type": "departure",
                          "title": f"Depart via {carrier}",
                          "detail": "Head to the airport for your return flight."})
        schedule.append({"day": i + 1, "date": date,
                         "title": act["name"] if act else "Explore", "items": items})

    return {
        "summary": (
            f"A {len(days)}-day trip to {trip_input['location']} staying at {hotel_name}, "
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
        _meal_title(meal).strip().casefold()
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

    _apply_weather_activity_order(synth, trip_input, outputs)

    return {
        "destination": trip_input["location"],
        "dates": trip_input["dates"],
        "summary": synth.get("summary", ""),
        "schedule": synth["schedule"],
        "cost": cost,
        "map_points": _map_points(outputs, trip_input["location"]),
        "packing_list": outputs["planning"]["packing_list"],
        "weather_summary": outputs["planning"]["weather_summary"],
        "weather_source": outputs["planning"].get("weather_source", "unknown"),
        "weather_location": outputs["planning"].get("weather_location"),
        "reasoning_log": reasoning_log,
        "agent_outputs": outputs,
        "transport_scrape_status": outputs.get("transportation", {}).get("scrape_status", "ok"),
        "transport_errors": outputs.get("transportation", {}).get("errors", []),
        "verification_notice": (
            "Live provider data is used when available. Clearly labeled estimates and "
            "fallbacks may be included when a provider is unavailable; verify every price, "
            "schedule, availability, and reservation before purchase."
        ),
    }


def plan(trip_input: dict) -> dict:
    """Run the six specialist agents in the spec-mandated dependency order,
    injecting each agent's real outputs into a shared ``trip_input`` so
    downstream agents consume genuine cross-agent data:

        1. Transportation  — ALWAYS first (real flight/train price)
        2. Budget          — transport-first allocation grounded in real cost
        3. Activity        — discovery + scheduling -> meal-slot handoff
           Housing         — independent, run in parallel with Activity
        4. Food            — consumes meal slots + budget caps
        5. Planning        — consumes activity outputs + budget alloc + hotel

    This replaces the previous fire-all-concurrently approach, which never
    delivered the cross-agent handoffs the design requires.
    """
    prepared_input = prepare_trip_input(trip_input)
    trip_id = prepared_input["trip_id"]

    # Mutable working copy shared across agents — the handoff channel.
    shared = dict(prepared_input)

    # ---- 1. TRANSPORTATION FIRST (always) ----
    transport_out = run_single_agent("transportation", shared)
    shared["_transport_cost"] = float(transport_out.get("cost", 0) or 0)
    shared["_transport_scope"] = transport_out.get("scope", "national")

    # ---- 2. BUDGET (transport-first, grounded in real transport cost) ----
    budget_out = run_single_agent("budget", shared)
    shared = with_budget_guidance(shared, budget_out)  # -> _budget_caps/_budget_ratios/_cost_index
    shared["_budget_allocations"] = budget_out.get("allocations", {})

    # ---- 3. ACTIVITY + HOUSING (independent, parallel) ----
    with ThreadPoolExecutor(max_workers=2) as executor:
        act_f = executor.submit(run_single_agent, "activity", shared)
        house_f = executor.submit(run_single_agent, "housing", shared)
        activity_out = act_f.result()
        housing_out = house_f.result()

    # Inject Activity -> Food / Planning handoff
    shared["_activity_meal_slots"] = activity_out.get("meal_slot_handoff", {})
    shared["_activity_outputs"] = activity_out.get("recommended", [])
    # Inject Housing -> Planning handoff
    h_rec = housing_out.get("recommended") or {}
    shared["_hotel_name"] = h_rec.get("name", "")
    shared["_housing_data"] = housing_out

    # ---- 4. FOOD (consumes meal slots + budget caps) ----
    food_out = run_single_agent("food", shared)

    # ---- 5. PLANNING (consumes activity outputs + budget alloc + hotel) ----
    planning_out = run_single_agent("planning", shared)

    outputs = {
        "transportation": transport_out,
        "budget": budget_out,
        "activity": activity_out,
        "housing": housing_out,
        "food": food_out,
        "planning": planning_out,
    }
    result = reconcile_and_synthesize(shared, outputs)
    result["trip_id"] = trip_id
    return result
