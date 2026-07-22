"""Destination-aware weather from Open-Meteo with an honest seasonal fallback."""
import json
from datetime import date, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ._ai import ESTIMATE_NOTE, generate_json, number, text

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HTTP_TIMEOUT_SECONDS = 8

DAILY_FIELDS = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_probability_max",
    "precipitation_sum",
    "snowfall_sum",
    "wind_speed_10m_max",
    "uv_index_max",
)

SYSTEM_PROMPT = (
    "Create a seasonal weather planning outlook for the exact destination and requested dates. "
    "Never use another city's climate. This is not live forecast data. Return ONLY JSON: "
    "{summary, daily: [{date, condition, high_c, low_c, rain_chance}]}. Include every requested "
    "date exactly once. rain_chance is a decimal from 0 to 1. The summary must explicitly say "
    "'AI seasonal estimate'."
)

# WMO interpretation codes used by Open-Meteo.
WMO_CONDITIONS = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    56: "Light freezing drizzle",
    57: "Heavy freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light rain showers",
    81: "Rain showers",
    82: "Heavy rain showers",
    85: "Light snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorms",
    96: "Thunderstorms with light hail",
    99: "Thunderstorms with heavy hail",
}


def _days(dates: dict) -> list[str]:
    start = date.fromisoformat(dates["start"])
    end = date.fromisoformat(dates["end"])
    if end < start:
        start, end = end, start
    values = []
    while start <= end:
        values.append(start.isoformat())
        start += timedelta(days=1)
    return values


def _get_json(url: str, params: dict) -> dict:
    request = Request(
        f"{url}?{urlencode(params)}",
        headers={"Accept": "application/json", "User-Agent": "G3TA-trip-planner/0.1"},
    )
    with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310 - fixed HTTPS hosts
        payload = json.load(response)
    if not isinstance(payload, dict) or payload.get("error"):
        reason = payload.get("reason", "invalid response") if isinstance(payload, dict) else "invalid response"
        raise ValueError(f"Open-Meteo request failed: {reason}")
    return payload


def geocode_destination(destination: str) -> dict:
    """Resolve an arbitrary destination string to the best Open-Meteo location."""
    query = destination.strip()
    if not query:
        raise ValueError("Destination is required for weather lookup.")
    payload = _get_json(GEOCODING_URL, {"name": query, "count": 1, "language": "en", "format": "json"})
    results = payload.get("results") or []
    if not results:
        raise ValueError(f"Open-Meteo could not geocode '{query}'.")
    raw = results[0]
    latitude = float(raw["latitude"])
    longitude = float(raw["longitude"])
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Open-Meteo returned invalid coordinates.")

    name_parts = []
    for value in (raw.get("name"), raw.get("admin1"), raw.get("country")):
        cleaned = text(value)
        if cleaned and cleaned.casefold() not in {part.casefold() for part in name_parts}:
            name_parts.append(cleaned)
    return {
        "name": ", ".join(name_parts) or query,
        "latitude": latitude,
        "longitude": longitude,
        "timezone": text(raw.get("timezone"), "auto"),
        "country_code": text(raw.get("country_code")),
    }


def _optional_number(value, digits: int = 1) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return round(parsed, digits)


def _forecast(location: dict) -> tuple[dict[str, dict], str]:
    payload = _get_json(FORECAST_URL, {
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "daily": ",".join(DAILY_FIELDS),
        "timezone": "auto",
        "forecast_days": 16,
    })
    raw_daily = payload.get("daily") or {}
    times = raw_daily.get("time") or []
    forecast = {}
    for index, forecast_date in enumerate(times):
        def at(field):
            values = raw_daily.get(field) or []
            return values[index] if index < len(values) else None

        code_value = at("weather_code")
        try:
            code = int(code_value)
        except (TypeError, ValueError):
            code = None
        high = _optional_number(at("temperature_2m_max"))
        low = _optional_number(at("temperature_2m_min"))
        rain_percent = _optional_number(at("precipitation_probability_max"))
        if high is None or low is None:
            continue
        forecast[str(forecast_date)] = {
            "date": str(forecast_date),
            "condition": WMO_CONDITIONS.get(code, "Forecast conditions"),
            "weather_code": code,
            "high_c": high,
            "low_c": min(low, high),
            "rain_chance": round(max(0.0, min(rain_percent or 0.0, 100.0)) / 100, 2),
            "precipitation_mm": _optional_number(at("precipitation_sum")),
            "snowfall_cm": _optional_number(at("snowfall_sum")),
            "wind_speed_max_kmh": _optional_number(at("wind_speed_10m_max")),
            "uv_index_max": _optional_number(at("uv_index_max")),
            "source": "open_meteo_forecast",
        }
    return forecast, text(payload.get("timezone"), location.get("timezone", "auto"))


def _seasonal_estimate(destination: str, dates: dict, requested_days: list[str]) -> dict:
    result = generate_json(SYSTEM_PROMPT, {
        "destination": destination,
        "dates": dates,
        "requested_dates": requested_days,
        "truthfulness_requirement": ESTIMATE_NOTE,
    }, temperature=0.35)
    raw_by_date = {
        item.get("date"): item
        for item in (result or {}).get("daily", [])
        if isinstance(item, dict) and item.get("date") in requested_days
    }
    daily = []
    for requested_date in requested_days:
        raw = raw_by_date.get(requested_date, {})
        high = number(raw.get("high_c"), 20, minimum=-60)
        low = number(raw.get("low_c"), 12, minimum=-70)
        daily.append({
            "date": requested_date,
            "condition": text(raw.get("condition"), "Seasonal conditions — verify"),
            "weather_code": None,
            "high_c": round(high, 1),
            "low_c": round(min(low, high), 1),
            "rain_chance": min(number(raw.get("rain_chance"), 0.3), 1.0),
            "precipitation_mm": None,
            "snowfall_cm": None,
            "wind_speed_max_kmh": None,
            "uv_index_max": None,
            "source": "deepseek_seasonal_estimate",
        })
    summary = text((result or {}).get("summary"), f"{destination}: AI seasonal estimate; verify closer to departure.")
    if "ai seasonal estimate" not in summary.lower():
        summary = f"AI seasonal estimate for {destination}: {summary} Verify closer to departure."
    return {"summary": summary, "daily": daily}


def get_weather(destination: str, dates: dict) -> dict:
    """Return live forecast dates and seasonal estimates for any uncovered dates."""
    requested_days = _days(dates)
    location = None
    forecast_by_date = {}
    timezone = None
    try:
        location = geocode_destination(destination)
        forecast_by_date, timezone = _forecast(location)
    except Exception:  # Open-Meteo is optional; retain the existing planning fallback.
        forecast_by_date = {}

    live_days = [day for day in requested_days if day in forecast_by_date]
    estimate_days = [day for day in requested_days if day not in forecast_by_date]
    estimates = _seasonal_estimate(destination, dates, estimate_days) if estimate_days else {"summary": "", "daily": []}
    estimate_by_date = {item["date"]: item for item in estimates["daily"]}
    daily = [forecast_by_date.get(day) or estimate_by_date[day] for day in requested_days]

    if live_days:
        resolved_name = location["name"] if location else destination
        summary = (
            f"Open-Meteo forecast for {resolved_name}: {live_days[0]} through {live_days[-1]} "
            f"({timezone or 'local time'})."
        )
        if estimate_days:
            summary += f" {len(estimate_days)} date(s) outside the live forecast are AI seasonal estimates."
    else:
        summary = estimates["summary"]

    source = "mixed" if live_days and estimate_days else (
        "open_meteo_forecast" if live_days else "deepseek_seasonal_estimate"
    )
    return {
        "summary": summary,
        "daily": daily,
        "source": source,
        "location": location,
        "verification_required": bool(estimate_days),
        "estimate_note": ESTIMATE_NOTE if estimate_days else None,
    }
