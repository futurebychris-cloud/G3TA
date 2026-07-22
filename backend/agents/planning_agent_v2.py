"""Planning Agent v2 (Journey Editor).

Upgraded from LLM-only estimates:
1. Open-Meteo weather API (free, no key) for real forecast data
2. Enriched packing checklist with 5 categories (clothing/items/supportive/legal/devices)
3. Clothing recommendations by temperature range
4. Health advisory (sickness risks, pests, altitude)
5. Legal/doc requirements check (visa, passport, permits)
6. Shared_checklist database integration

Output: {"packing_list": [category items], "weather_summary": str, "pacing_notes": str, ...}
"""
from __future__ import annotations
import hashlib, json, re, urllib.request
from llm.easy_reading import easy_reading_enabled, with_easy_reading
from services.weather_service import get_weather

from .base import llm_reason, trip_days

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Geo-coordinates for city lookup (simplified; used as fallback)
CITY_COORDS = {
    "北京": (39.9042, 116.4074), "上海": (31.2304, 121.4737), "广州": (23.1291, 113.2644),
    "深圳": (22.5431, 114.0579), "杭州": (30.2741, 120.1551), "成都": (30.5728, 104.0668),
    "重庆": (29.4316, 106.9123), "西安": (34.3416, 108.9398), "南京": (32.0603, 118.7969),
    "武汉": (30.5928, 114.3055), "厦门": (24.4798, 118.0894), "昆明": (25.0389, 102.7183),
    "青岛": (36.0671, 120.3826), "大连": (38.9140, 121.6147), "苏州": (31.2990, 120.5853),
    "三亚": (18.2528, 109.5120), "天津": (39.3434, 117.3616), "长沙": (28.2282, 112.9388),
    "beijing": (39.9042, 116.4074), "shanghai": (31.2304, 121.4737),
    "guangzhou": (23.1291, 113.2644), "shenzhen": (22.5431, 114.0579),
    "hangzhou": (30.2741, 120.1551), "chengdu": (30.5728, 104.0668),
    "tokyo": (35.6762, 139.6503), "osaka": (34.6937, 135.5023),
    "kyoto": (35.0116, 135.7681), "seoul": (37.5665, 126.9780),
    "bangkok": (13.7563, 100.5018), "singapore": (1.3521, 103.8198),
    "paris": (48.8566, 2.3522), "london": (51.5074, -0.1278),
    "new york": (40.7128, -74.0060), "los angeles": (34.0522, -118.2437),
}

CLOTHING_BY_TEMP = [
    (35, "Hot weather: tank tops, shorts, sandals, UV-protective clothing, wide-brim hat"),
    (28, "Warm weather: light t-shirts, shorts/linen pants, sundress, sunscreen SPF50+"),
    (22, "Mild weather: short-sleeve shirts, light long pants, light jacket for evenings"),
    (16, "Cool weather: long-sleeve shirts, jeans, sweater or fleece, light scarf"),
    (10, "Cold weather: sweater, warm jacket, long pants, closed shoes, scarf, gloves"),
    (0, "Very cold: thermal base layer, heavy coat/down jacket, hat, gloves, warm boots"),
    (-99, "Extreme cold: full thermal layers, insulated boots, face covering, hand warmers"),
]

HEALTH_ADVISORIES = {
    "asia": "Check for recommended vaccinations (Hepatitis A, Typhoid). Bring mosquito repellent for tropical areas.",
    "southeast_asia": "Malaria/dengue risk in some areas. Use DEET repellent, sleep under mosquito nets. Bring oral rehydration salts.",
    "europe": "EHIC/GHIC card recommended for EU travel. Travel insurance mandatory.",
    "africa": "Yellow fever vaccination may be required. Malaria prophylaxis recommended. Drink bottled water only.",
    "south_america": "Altitude sickness possible above 2500m. Yellow fever vaccination for some countries. Bring water purification tablets.",
}

PACKING_CHECKLIST_PROMPT = (
    "You are the Planning Agent (Journey Editor). Given destination, dates, weather forecast, "
    "activity styles, and user preferences, produce a comprehensive packing checklist in "
    "5 categories: clothing, items, supportive, legal, devices. "
    "Return ONLY JSON: {checklist: [{category, items: [{name, quantity, reason}]}]}"
)


def _geocode_city(city: str) -> tuple[float, float]:
    """Get lat/lng for a city. Uses city coords lookup + Open-Meteo geocoding fallback."""
    key = city.lower().strip()
    if key in CITY_COORDS:
        return CITY_COORDS[key]
    # Try Open-Meteo geocoding API
    try:
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.request.quote(city)}&count=1&language=en"
        req = urllib.request.Request(url, headers={"User-Agent": "G3TA/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        if data.get("results"):
            r = data["results"][0]
            return r["latitude"], r["longitude"]
    except Exception as exc:
        raise RuntimeError(f"Could not geocode planning destination '{city}'.") from exc
    raise RuntimeError(f"Could not geocode planning destination '{city}'.")


def _fetch_open_meteo_weather(lat: float, lng: float, start: str, end: str) -> dict:
    """Fetch real weather forecast from Open-Meteo (free, no API key).
    If dates are too far in the future (>14 days) or past, uses past-year climate normals
    from the historical archive API instead."""
    from datetime import date as _date, timedelta as _td
    try:
        start_date = _date.fromisoformat(start)
        end_date = _date.fromisoformat(end)
        today = _date.today()
        days_ahead_start = (start_date - today).days
        days_ahead_end = (end_date - today).days
    except Exception:
        days_ahead_start = days_ahead_end = 0

    # Open-Meteo free forecast API allows ~15-day forecast window and ~5-day past window.
    # The end_date is what the API validates, so we check *end_date* against the window.
    # If the trip end is beyond 14 days from now, use the historical archive API instead.
    use_historical = days_ahead_end > 14 or days_ahead_start < -5
    if use_historical:
        try:
            # Shift dates back one year for climate proxy (archive API has full history)
            start = str(_date(start_date.year - 1, start_date.month, start_date.day))
            end_adj = str(_date(end_date.year - 1, end_date.month, end_date.day))
        except Exception:
            end_adj = end
        print(f"[planning] dates out of forecast window (end {days_ahead_end}d ahead), using climate proxy {start}–{end_adj}")
    else:
        end_adj = end

    api_url = "https://archive-api.open-meteo.com/v1/archive" if use_historical else OPEN_METEO_URL

    # archive API does NOT support precipitation_probability_max — returns None
    daily_params = "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code"
    if not use_historical:
        daily_params = daily_params.replace("weather_code", "precipitation_probability_max,weather_code")

    try:
        params = {
            "latitude": lat, "longitude": lng, "start_date": start, "end_date": end_adj,
            "daily": daily_params,
            "timezone": "auto",
        }
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{api_url}?{qs}"
        print(f"[planning] fetching weather from {api_url.split('?')[0]}")
        req = urllib.request.Request(url, headers={"User-Agent": "G3TA/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())

        daily_data = data.get("daily", {})
        daily = []
        for i in range(len(daily_data.get("time", []))):
            code = daily_data.get("weather_code", [0]*10)[i] if i < len(daily_data.get("weather_code", [])) else 0

            # rain_chance: use precipitation_probability_max when avail (forecast API),
            # otherwise estimate from precipitation_sum > 0
            prob_max_list = daily_data.get("precipitation_probability_max", [])
            if prob_max_list and i < len(prob_max_list) and prob_max_list[i] is not None:
                rain_chance = prob_max_list[i] / 100.0
            else:
                precip = daily_data.get("precipitation_sum", [0])[i] if i < len(daily_data.get("precipitation_sum", [])) else 0
                rain_chance = 0.6 if (isinstance(precip, (int, float)) and precip > 1.0) else 0.15

            daily.append({
                "date": daily_data["time"][i],
                "high_c": daily_data.get("temperature_2m_max", [20])[i] if i < len(daily_data.get("temperature_2m_max", [])) else 20,
                "low_c": daily_data.get("temperature_2m_min", [10])[i] if i < len(daily_data.get("temperature_2m_min", [])) else 10,
                "rain_chance": rain_chance,
                "precipitation_mm": daily_data.get("precipitation_sum", [0])[i] if i < len(daily_data.get("precipitation_sum", [])) else 0,
                "weather_code": code,
                "condition": _weather_code_to_text(code),
                "source": "open-meteo",
            })

        highs = [d["high_c"] for d in daily]
        lows = [d["low_c"] for d in daily]
        rain_days = sum(1 for d in daily if d["rain_chance"] > 0.5)
        summary = (
            f"Open-Meteo real forecast: {min(lows) if lows else '?'}°C – {max(highs) if highs else '?'}°C, "
            f"{rain_days} rainy day(s) expected. "
        )
        return {"summary": summary, "daily": daily, "source": "open-meteo", "verification_required": True}
    except Exception as e:
        print(f"[planning] Open-Meteo fetch failed: {e}")
        return None


def _weather_code_to_text(code: int) -> str:
    map = {0: "Clear", 1: "Mostly Clear", 2: "Partly Cloudy", 3: "Overcast",
           45: "Fog", 48: "Rime Fog", 51: "Light Drizzle", 53: "Drizzle", 55: "Heavy Drizzle",
           61: "Light Rain", 63: "Rain", 65: "Heavy Rain", 71: "Light Snow", 73: "Snow",
           75: "Heavy Snow", 80: "Rain Showers", 95: "Thunderstorm", 96: "Thunderstorm+Hail"}
    return map.get(code, f"Code {code}")


def _clothing_by_temperature(high_c: float, low_c: float) -> list[str]:
    """Recommend clothing based on temperature range."""
    avg = (high_c + low_c) / 2
    recommendations = []
    for temp_threshold, advice in CLOTHING_BY_TEMP:
        if avg >= temp_threshold:
            recommendations.append(advice)
            break
    if low_c < 5:
        recommendations.append("Warm accessories: scarf, gloves, beanie")
    if high_c > 28:
        recommendations.append("Sun protection: SPF50+ sunscreen, sunglasses, UV umbrella")
    return recommendations


def _region_health_advice(destination: str) -> str:
    """Determine health advisory based on destination region."""
    d = destination.lower()
    if any(c in d for c in ["thailand", "vietnam", "indonesia", "philippines", "malaysia", "singapore", "cambodia"]):
        return HEALTH_ADVISORIES["southeast_asia"]
    if any(c in d for c in ["japan", "china", "korea", "taiwan", "india"]):
        return HEALTH_ADVISORIES["asia"]
    if any(c in d for c in ["france", "uk", "germany", "italy", "spain", "europe"]):
        return HEALTH_ADVISORIES["europe"]
    if any(c in d for c in ["brazil", "peru", "chile", "argentina"]):
        return HEALTH_ADVISORIES["south_america"]
    return "Check CDC/WHO travel advisories for your destination. Bring basic first-aid kit."


def _device_checklist() -> list[dict]:
    return [
        {"name": "Phone + charger + power bank", "quantity": 1, "reason": "Essential communication"},
        {"name": "Universal travel adapter", "quantity": 1, "reason": "For international plug compatibility"},
        {"name": "Portable Wi-Fi / local SIM card", "quantity": 1, "reason": "Stay connected"},
        {"name": "Camera + memory card", "quantity": 1, "reason": "Capture memories"},
        {"name": "Noise-canceling headphones", "quantity": 1, "reason": "For long flights/transit"},
        {"name": "E-reader / tablet", "quantity": 1, "reason": "Entertainment for downtime"},
    ]


def _legal_checklist(destination: str, origin: str) -> list[dict]:
    items = [
        {"name": "Passport (valid 6+ months)", "quantity": 1, "reason": "Required for international travel"},
        {"name": "Visa (check requirements)", "quantity": 1, "reason": f"Verify visa needs for {destination}"},
        {"name": "Travel insurance documents", "quantity": 1, "reason": "Medical + trip cancellation coverage"},
        {"name": "Flight/train booking confirmations", "quantity": 1, "reason": "Printed + digital copies"},
        {"name": "Hotel reservation confirmations", "quantity": 1, "reason": "Check-in requirements"},
        {"name": "Emergency contacts card", "quantity": 1, "reason": "Embassy, insurance, family contacts"},
    ]
    # Check if domestic travel
    if origin and destination:
        o = origin.lower().strip()
        d = destination.lower().strip()
        is_china_both = any(c in o for c in ["北京","上海","beijing","shanghai"]) and any(c in d for c in CITY_COORDS if CITY_COORDS[c][0] > 18 and CITY_COORDS[c][0] < 54)
        if is_china_both:
            items[0]["name"] = "身份证 (ID card)"
            items[0]["reason"] = "Required for domestic travel"
            items[1]["name"] = "学生证/优惠证件 (if applicable)"
            items[1]["reason"] = "For student/group discounts"
    return items


def _supportive_checklist(weather_daily: list[dict], activity_styles: list[str]) -> list[dict]:
    items = [
        {"name": "Small first-aid kit", "quantity": 1, "reason": "Band-aids, pain relievers, antiseptic"},
        {"name": "Prescription medications", "quantity": 1, "reason": "Bring enough for entire trip + 2 days extra"},
        {"name": "Reusable water bottle", "quantity": 1, "reason": "Stay hydrated, eco-friendly"},
        {"name": "Daypack / small backpack", "quantity": 1, "reason": "For daily excursions"},
        {"name": "Travel pillow + eye mask + earplugs", "quantity": 1, "reason": "Comfort during transit"},
    ]
    if weather_daily and any(d.get("rain_chance", 0) > 0.3 for d in weather_daily):
        items.append({"name": "Compact umbrella / rain jacket", "quantity": 1, "reason": "Rain expected"})
    if any(s in ["adventure", "hiking", "户外"] for s in activity_styles):
        items.extend([
            {"name": "Insect repellent (DEET)", "quantity": 1, "reason": "For outdoor activities"},
            {"name": "Water purification tablets", "quantity": 1, "reason": "For remote areas"},
        ])
    return items


def _metric(weather: dict, key: str) -> list[float]:
    values = []
    for day in weather.get("daily", []):
        try:
            if day.get(key) is not None:
                values.append(float(day[key]))
        except (TypeError, ValueError):
            continue
    return values


def _fallback_packing(weather: dict, styles: list[str]) -> list[str]:
    """Safety essentials that an LLM-generated checklist may not omit."""
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
    if any(float(day.get("rain_chance") or 0) >= 0.4 for day in weather.get("daily", [])):
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
    return items


def _merge_packing(*groups) -> list[str]:
    items = []
    seen = set()
    for group in groups:
        if not isinstance(group, list):
            continue
        for item in group:
            value = item.get("name", "") if isinstance(item, dict) else item
            cleaned = str(value).strip()
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
            day.get("date", ""),
        )

    live_days = [
        day for day in weather.get("daily", [])
        if day.get("source") == "open_meteo_forecast"
    ]
    return [day["date"] for day in sorted(live_days, key=score)[:limit]]


def run(trip_input: dict) -> dict:
    destination = trip_input["location"]
    origin = trip_input.get("origin", "")
    days = trip_days(trip_input)
    trip_id = trip_input.get("trip_id", hashlib.sha256(
        f"{destination}{trip_input['dates']['start']}".encode()
    ).hexdigest()[:12])
    preferences = trip_input.get("preferences", {})
    activity_styles = preferences.get("activity_style", [])

    # Use the normalized weather service so live forecasts and clearly labeled
    # seasonal fallbacks retain the same contract across v1 and v2.
    weather = get_weather(destination, trip_input["dates"])

    # ---- Build enriched packing checklist ----
    # Get LLM-generated packing list as baseline
    llm_result = llm_reason(with_easy_reading(
        PACKING_CHECKLIST_PROMPT,
        easy_reading_enabled(trip_input),
    ), {
        "destination": destination,
        "dates": trip_input["dates"],
        "num_days": len(days),
        "weather": weather,
        "activity_styles": activity_styles,
        "all_preferences": preferences,
    })

    # Build structured checklist
    weather_daily = weather.get("daily", [])
    highs = [d["high_c"] for d in weather_daily]
    lows = [d["low_c"] for d in weather_daily]
    avg_high = sum(highs) / len(highs) if highs else 22
    avg_low = sum(lows) / len(lows) if lows else 12

    clothing_items = [{"name": c, "quantity": 1, "reason": f"Temperature: {avg_low:.0f}–{avg_high:.0f}°C"}
                      for c in _clothing_by_temperature(avg_high, avg_low)]

    packing_checklist = {
        "clothing": clothing_items,
        "item": _supportive_checklist(weather_daily, activity_styles),
        "supportive": [],
        "legal": _legal_checklist(destination, origin),
        "device": _device_checklist(),
    }

    if llm_result and llm_result.get("checklist"):
        # Enrich with LLM suggestions
        for cat in llm_result["checklist"]:
            cat_name = cat.get("category", "")
            if cat_name in packing_checklist:
                for item in cat.get("items", []):
                    if isinstance(item, dict):
                        packing_checklist[cat_name].append({
                            "name": item.get("name", ""),
                            "quantity": item.get("quantity", 1),
                            "reason": item.get("reason", ""),
                        })

    # ---- Health advisory ----
    health_advice = _region_health_advice(destination)

    # ---- Pacing notes ----
    rain_days = sum(1 for d in weather_daily if d.get("rain_chance", 0) > 0.5)
    clearest_dates = _clearest_dates(weather)
    clear_date_note = (
        f" Favor {', '.join(clearest_dates)} for outdoor activities based on the current forecast."
        if clearest_dates else
        " Keep outdoor timing flexible because these dates use seasonal estimates."
    )
    pacing = (llm_result or {}).get("pacing_notes") or (
        f"{len(days)} day(s) in {destination}. "
        f"{f'{rain_days} day(s) with significant rain chance — plan indoor activities on those days. ' if rain_days else ''}"
        f"Temperature range: {avg_low:.0f}–{avg_high:.0f}°C. "
        f"Front-load outdoor activities on clearer days.{clear_date_note}"
    )
    if clearest_dates and not any(value in pacing for value in clearest_dates):
        pacing = f"{pacing.rstrip()} {clear_date_note.strip()}"
    if not clearest_dates and "seasonal" not in pacing.casefold():
        pacing = f"{pacing.rstrip()} {clear_date_note.strip()}"

    # ---- Store to shared database ----
    try:
        from booking.shared_db import save_checklist_item
        for cat_name, items in packing_checklist.items():
            for item in items:
                if isinstance(item, dict) and item.get("name"):
                    save_checklist_item(
                        trip_id=trip_id, category=cat_name,
                        item_name=item["name"],
                        quantity=item.get("quantity", 1),
                        weather_note=f"{avg_low:.0f}-{avg_high:.0f}°C",
                        suggestion_reason=item.get("reason", ""),
                    )
        print(f"[planning] saved packing checklist to shared DB")
    except Exception as e:
        print(f"[planning] DB save failed (non-fatal): {e}")

    # Weather summary
    weather_summary = weather.get("summary",
        f"Seasonal estimate for {destination}: {avg_low:.0f}–{avg_high:.0f}°C. Verify closer to departure.")

    # ---- Flat packing list for orchestrator/frontend compatibility ----
    # Keep model suggestions first, then append non-negotiable weather essentials
    # and the richer structured v2 recommendations without duplicates.
    structured_names = [
        item
        for items in packing_checklist.values()
        for item in items
    ]
    flat_list = _merge_packing(
        (llm_result or {}).get("packing_list", []),
        _fallback_packing(weather, activity_styles),
        structured_names,
    )

    return {
        "packing_list": flat_list,
        "packing_checklist": packing_checklist,
        "weather_summary": weather_summary,
        "daily_weather": weather_daily,
        "pacing_notes": pacing,
        "health_advice": health_advice,
        "destination": destination,
        "verification_required": True,
        "trip_id": trip_id,
        "weather_source": weather.get("source", "llm_estimate"),
        "weather_location": weather.get("location"),
    }
