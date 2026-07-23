"""Planning Agent.

Responsibility (PRD §7): packing list + weather-driven adjustments + day pacing.
Data source: Open-Meteo forecasts with labeled AI seasonal estimates outside the forecast window.
v2: Adds cultural fashion recommendations beyond temperature-only packing.
Output shape: {"packing_list": [...], "weather_summary": str, "pacing_notes": str} (+ daily weather).
"""
from services.weather_service import get_weather
from llm.easy_reading import easy_reading_enabled, with_easy_reading

from .base import llm_reason, trip_days

SYSTEM_PROMPT = (
    "You are the Planning Agent in a multi-agent trip planner. Given a destination, the trip "
    "dates, a per-day weather forecast, and the traveler's activity style, produce practical "
    "trip logistics. "
    "Use the exact destination only and never mention weather or logistics for another city. "
    "Return ONLY a JSON object with keys: "
    "packing_list (array of concise item strings tailored to the weather and activities), and "
    "pacing_notes (2-3 sentences on how to pace the days given the weather and trip length). "
    "Name the best dates for outdoor plans when daily forecast data makes that possible, and "
    "distinguish live forecasts from seasonal estimates."
)


def _metric(weather: dict, key: str) -> list[float]:
    values = []
    for day in weather.get("daily", []):
        try:
            if day.get(key) is not None:
                values.append(float(day[key]))
        except (TypeError, ValueError):
            continue
    return values


def _fallback_packing(weather: dict, styles: list[str], destination: str = "") -> list[str]:
    items = ["Passport & travel documents", "Phone + charger / power bank", "Reusable water bottle"]
    highs = _metric(weather, "high_c")
    lows = _metric(weather, "low_c")
    snow = _metric(weather, "snowfall_cm")
    wind = _metric(weather, "wind_speed_max_kmh")
    uv = _metric(weather, "uv_index_max")
    if lows and min(lows) < 10:
        items += ["Warm jacket", "Layerable sweaters"]
    if lows and min(lows) <= 0:
        items += ["Thermal base layers", "Gloves, warm hat & scarf"]
    if highs and max(highs) > 26:
        items += ["Light breathable clothing", "Sun hat"]
    if any(d["rain_chance"] >= 0.4 for d in weather["daily"]):
        items += ["Compact umbrella", "Water-resistant shoes"]
    if snow and max(snow) > 0:
        items += ["Insulated waterproof boots", "Warm waterproof outer layer"]
    if wind and max(wind) >= 35:
        items.append("Windproof outer layer")
    if (uv and max(uv) >= 6) or (highs and max(highs) > 26):
        items += ["Broad-spectrum sunscreen", "Sunglasses"]
    normalized_styles = {str(style).strip().casefold() for style in styles}
    if "adventure" in normalized_styles:
        items += ["Comfortable hiking shoes", "Daypack"]
    if "cultural" in normalized_styles:
        items.append("Modest layer for temples/shrines")
    items += ["Comfortable walking shoes", "Transit/IC card", "Small first-aid kit"]

    # ---- Cultural fashion recommendations (v2) ----
    if destination:
        try:
            from services.cultural_fashion_service import get_clothing_recommendations
            cultural = get_clothing_recommendations(destination, weather)
            # Add cultural dress code items
            for dc in cultural.get("cultural_advice", {}).get("dress_codes", []):
                rule = dc.get("rule", "")
                if rule and "cover" in rule.lower():
                    items.append("Modest clothing for religious sites (cover shoulders/knees)")
                    break
            # Add traditional wear suggestion if available
            traditional = cultural.get("cultural_advice", {}).get("traditional_wear", "")
            if traditional:
                items.append(f"Option: {traditional}")
            # Add shopping fashion notes
            fashion = cultural.get("cultural_advice", {}).get("fashion_trends", "")
            if fashion:
                items.append(f"Style note: {fashion[:80]}")
        except Exception:
            pass  # Non-critical, skip cultural items if service fails

    return items


def _merge_packing(suggested, required: list[str]) -> list[str]:
    items = []
    seen = set()
    candidates = suggested if isinstance(suggested, list) else []
    for item in [*candidates, *required]:
        cleaned = str(item).strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            items.append(cleaned)
            seen.add(key)
    return items


def _clearest_dates(weather: dict, limit: int = 2) -> list[str]:
    def score(day: dict):
        return (
            float(day.get("rain_chance") or 0),
            float(day.get("precipitation_mm") or 0),
            float(day.get("snowfall_cm") or 0),
            float(day.get("wind_speed_max_kmh") or 0),
            day["date"],
        )

    live_days = [day for day in weather.get("daily", []) if day.get("source") == "open_meteo_forecast"]
    return [day["date"] for day in sorted(live_days, key=score)[:limit]]


def run(trip_input: dict) -> dict:
    styles = trip_input.get("preferences", {}).get("activity_style", [])
    weather = get_weather(trip_input["location"], trip_input["dates"])
    days = trip_days(trip_input)

    result = llm_reason(with_easy_reading(SYSTEM_PROMPT, easy_reading_enabled(trip_input)), {
        "destination": trip_input["location"],
        "num_days": len(days),
        "activity_styles": styles,
        "all_preferences": trip_input.get("preferences", {}),
        "time_constraints": trip_input.get("time_constraints", ""),
        "weather": weather,
    })

    required_packing = _fallback_packing(weather, styles, trip_input["location"])
    packing = _merge_packing((result or {}).get("packing_list"), required_packing)
    clearest_dates = _clearest_dates(weather)
    clear_date_note = (
        f" Favor {', '.join(clearest_dates)} for outdoor activities based on the current forecast."
        if clearest_dates else " Keep outdoor timing flexible because these dates use seasonal estimates."
    )
    pacing = (result or {}).get("pacing_notes") or (
        f"With {len(days)} day(s), keep one flexible afternoon in case of rain "
        f"({int(max((d['rain_chance'] for d in weather['daily']), default=0) * 100)}% chance on some "
        f"days).{clear_date_note}"
    )
    if clearest_dates and not any(value in pacing for value in clearest_dates):
        pacing = f"{pacing.rstrip()} {clear_date_note.strip()}"
    if not clearest_dates and weather["source"] == "deepseek_seasonal_estimate" and "seasonal" not in pacing.casefold():
        pacing = f"{pacing.rstrip()} These dates use seasonal estimates, so recheck conditions closer to departure."

    return {
        "packing_list": packing,
        "weather_summary": weather["summary"],
        "pacing_notes": pacing,
        "daily_weather": weather["daily"],
        "weather_source": weather["source"],
        "weather_location": weather.get("location"),
        "destination": trip_input["location"],
        "verification_required": weather.get("verification_required", True),
    }
