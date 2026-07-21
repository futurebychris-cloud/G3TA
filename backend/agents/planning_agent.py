"""Planning Agent.

Responsibility (PRD §7): packing list + weather-driven adjustments + day pacing.
Data source: weather_service.get_weather (mock_weather.json).
Output shape: {"packing_list": [...], "weather_summary": str, "pacing_notes": str} (+ daily weather).
"""
from services.weather_service import get_weather

from .base import llm_reason, trip_days

SYSTEM_PROMPT = (
    "You are the Planning Agent in a multi-agent trip planner. Given a destination, the trip "
    "dates, a per-day weather forecast, and the traveler's activity style, produce practical "
    "trip logistics. "
    "Return ONLY a JSON object with keys: "
    "packing_list (array of concise item strings tailored to the weather and activities), and "
    "pacing_notes (2-3 sentences on how to pace the days given the weather and trip length)."
)


def _fallback_packing(weather: dict, styles: list[str]) -> list[str]:
    items = ["Passport & travel documents", "Phone + charger / power bank", "Reusable water bottle"]
    highs = [d["high_c"] for d in weather["daily"]]
    lows = [d["low_c"] for d in weather["daily"]]
    if lows and min(lows) < 10:
        items += ["Warm jacket", "Layerable sweaters"]
    if highs and max(highs) > 26:
        items += ["Light breathable clothing", "Sunscreen & hat"]
    if any(d["rain_chance"] >= 0.4 for d in weather["daily"]):
        items += ["Compact umbrella", "Water-resistant shoes"]
    if any(s in {"adventure"} for s in styles):
        items += ["Comfortable hiking shoes", "Daypack"]
    if any(s in {"cultural"} for s in styles):
        items.append("Modest layer for temples/shrines")
    items += ["Comfortable walking shoes", "Transit/IC card", "Small first-aid kit"]
    return items


def run(trip_input: dict) -> dict:
    styles = trip_input.get("preferences", {}).get("activity_style", [])
    weather = get_weather(trip_input["location"], trip_input["dates"])
    days = trip_days(trip_input)

    result = llm_reason(SYSTEM_PROMPT, {
        "destination": trip_input["location"],
        "num_days": len(days),
        "activity_styles": styles,
        "weather": weather,
    })

    packing = (result or {}).get("packing_list") or _fallback_packing(weather, styles)
    pacing = (result or {}).get("pacing_notes") or (
        f"With {len(days)} day(s), keep one flexible afternoon in case of rain "
        f"({int(max((d['rain_chance'] for d in weather['daily']), default=0) * 100)}% chance on some "
        f"days). Front-load outdoor plans on clearer days."
    )

    return {
        "packing_list": packing,
        "weather_summary": weather["summary"],
        "pacing_notes": pacing,
        "daily_weather": weather["daily"],
    }
