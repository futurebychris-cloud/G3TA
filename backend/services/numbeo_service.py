"""Budget references from Numbeo web data plus labeled static estimates.

Numbeo provides: meal prices, hotel indices, local transport costs, etc.

Usage:
    from services.numbeo_service import get_cost_index
    index = get_cost_index("Shanghai", "USD")
    # Returns: {daily_index: {food, activity, housing, local_transport, shopping},
    #           flight_reference, cost_level, source: "numbeo", currency}
"""
from __future__ import annotations

import json
import math
import os
import re
import urllib.parse
import urllib.request
from functools import lru_cache

_NUMBEO_CITY_MAP: dict[str, str] = {
    # Chinese cities (Numbeo names)
    "shanghai": "Shanghai",
    "beijing": "Beijing",
    "guangzhou": "Guangzhou",
    "shenzhen": "Shenzhen",
    "hangzhou": "Hangzhou",
    "chengdu": "Chengdu",
    "chongqing": "Chongqing",
    "xian": "Xian",
    "xi'an": "Xian",
    "nanjing": "Nanjing",
    "wuhan": "Wuhan",
    "xiamen": "Xiamen",
    "kunming": "Kunming",
    "qingdao": "Qingdao",
    "dalian": "Dalian",
    "suzhou": "Suzhou",
    "sanya": "Sanya",
    "tianjin": "Tianjin",
    "changsha": "Changsha",
    "ningbo": "Ningbo",
    "guiyang": "Guiyang",
    "harbin": "Harbin",
    "shenyang": "Shenyang",
    "zhengzhou": "Zhengzhou",
    "jinan": "Jinan",
    "hefei": "Hefei",
    "fuzhou": "Fuzhou",
    "nanchang": "Nanchang",
    "taiyuan": "Taiyuan",
    "lhasa": "Lhasa",
    "urumqi": "Urumqi",
    # International cities
    "tokyo": "Tokyo",
    "osaka": "Osaka",
    "seoul": "Seoul",
    "bangkok": "Bangkok",
    "singapore": "Singapore",
    "hong kong": "Hong Kong",
    "hongkong": "Hong Kong",
    "paris": "Paris",
    "london": "London",
    "new york": "New York, NY",
    "los angeles": "Los Angeles, CA",
    "san francisco": "San Francisco, CA",
    "sydney": "Sydney",
    "dubai": "Dubai",
    "istanbul": "Istanbul",
    "rome": "Rome",
    "barcelona": "Barcelona",
    "berlin": "Berlin",
    "milan": "Milan",
    "amsterdam": "Amsterdam",
    "toronto": "Toronto",
    "vancouver": "Vancouver",
    "mumbai": "Mumbai",
    "delhi": "Delhi",
}

# Static reference estimates used only when the public page is unavailable.
# Values are in USD per day for a mid-range traveler
_COST_DATABASE: dict[str, dict] = {
    "Shanghai": {
        "meal_inexpensive": 4.5, "meal_mid_range_2": 28.0,
        "hotel_index": 85.0, "local_transport_ticket": 0.55,
        "taxi_km": 0.40, "attraction_avg": 12.0,
        "shopping_index": 55.0, "cost_level": "moderate",
    },
    "Beijing": {
        "meal_inexpensive": 4.0, "meal_mid_range_2": 25.0,
        "hotel_index": 78.0, "local_transport_ticket": 0.55,
        "taxi_km": 0.35, "attraction_avg": 10.0,
        "shopping_index": 50.0, "cost_level": "moderate",
    },
    "Tokyo": {
        "meal_inexpensive": 7.0, "meal_mid_range_2": 40.0,
        "hotel_index": 120.0, "local_transport_ticket": 1.50,
        "taxi_km": 2.80, "attraction_avg": 15.0,
        "shopping_index": 90.0, "cost_level": "expensive",
    },
    "Singapore": {
        "meal_inexpensive": 9.0, "meal_mid_range_2": 50.0,
        "hotel_index": 150.0, "local_transport_ticket": 1.50,
        "taxi_km": 1.20, "attraction_avg": 20.0,
        "shopping_index": 100.0, "cost_level": "very expensive",
    },
    "Bangkok": {
        "meal_inexpensive": 2.0, "meal_mid_range_2": 15.0,
        "hotel_index": 35.0, "local_transport_ticket": 0.50,
        "taxi_km": 0.30, "attraction_avg": 8.0,
        "shopping_index": 30.0, "cost_level": "cheap",
    },
    "Paris": {
        "meal_inexpensive": 16.0, "meal_mid_range_2": 65.0,
        "hotel_index": 160.0, "local_transport_ticket": 2.10,
        "taxi_km": 1.80, "attraction_avg": 18.0,
        "shopping_index": 110.0, "cost_level": "very expensive",
    },
    "New York, NY": {
        "meal_inexpensive": 18.0, "meal_mid_range_2": 80.0,
        "hotel_index": 220.0, "local_transport_ticket": 2.90,
        "taxi_km": 2.50, "attraction_avg": 30.0,
        "shopping_index": 120.0, "cost_level": "very expensive",
    },
}

# Default: moderate cost city (generic estimate)
_DEFAULT_COSTS = {
    "meal_inexpensive": 8.0, "meal_mid_range_2": 35.0,
    "hotel_index": 80.0, "local_transport_ticket": 1.20,
    "taxi_km": 0.80, "attraction_avg": 12.0,
    "shopping_index": 50.0, "cost_level": "moderate",
}


def _scrape_numbeo_page(city_name: str) -> dict | None:
    """Attempt to scrape Numbeo cost-of-living page for a city."""
    try:
        encoded = urllib.parse.quote(city_name.replace(" ", "-"))
        url = f"https://www.numbeo.com/cost-of-living/in/{encoded}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        })
        with urllib.request.urlopen(req, timeout=12) as r:
            html = r.read().decode("utf-8", errors="ignore")

        # Extract meal prices
        meal_inexp = _extract_price(html, "Meal, Inexpensive Restaurant")
        meal_mid = _extract_price(html, "Meal for 2 People, Mid-range Restaurant")
        transport = _extract_price(html, "One-way Ticket \\(Local Transport\\)")
        taxi = _extract_price(html, "Taxi 1km")

        if meal_inexp or meal_mid:
            return {
                "meal_inexpensive": meal_inexp or 8.0,
                "meal_mid_range_2": meal_mid or 35.0,
                "local_transport_ticket": transport or 1.0,
                "taxi_km": taxi or 0.80,
                "source": "numbeo_scraped",
            }
    except Exception as e:
        print(f"[numbeo] scrape failed for {city_name}: {e}")
    return None


def _extract_price(html: str, label_pattern: str) -> float | None:
    """Extract a price value from Numbeo HTML near a label."""
    pattern = re.compile(
        rf'{label_pattern}.*?([\d,.]+)\s*(?:¥|CNY|\$|USD|€|£)',
        re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(html)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            pass

    # Also try USD pattern
    pattern_usd = re.compile(
        rf'{label_pattern}.*?\$\s*([\d,.]+)',
        re.DOTALL | re.IGNORECASE,
    )
    m = pattern_usd.search(html)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            pass
    return None


@lru_cache(maxsize=128)
def _get_city_data(city: str) -> dict:
    """Get cost data for a city, trying Numbeo scrape first, then DB, then defaults."""
    # Normalize city name
    key = city.lower().strip().split(",")[0].strip()
    numbeo_name = _NUMBEO_CITY_MAP.get(key, city)

    # Try scraping Numbeo
    scraped = _scrape_numbeo_page(numbeo_name)
    if scraped:
        # Merge with DB data for missing fields
        db_data = _COST_DATABASE.get(numbeo_name, _DEFAULT_COSTS)
        result = {**db_data, **scraped}
        result["source"] = "numbeo_scraped"
        return result

    # Fall back to database
    db_data = _COST_DATABASE.get(numbeo_name)
    if db_data:
        result = dict(db_data)
        result["source"] = "numbeo_database"
        return result

    # Default
    result = dict(_DEFAULT_COSTS)
    result["source"] = "numbeo_estimated"
    return result


def get_cost_index(
    destination: str,
    origin: str = "",
    dates: dict | None = None,
    currency: str = "USD",
) -> dict:
    """Return a labeled cost index for the destination.

    Returns: {
        currency, cost_level, daily_index: {food, activity, housing, local_transport, shopping},
        flight_reference, reasoning, destination, source, verification_required
    }
    """
    data = _get_city_data(destination)

    # Calculate daily index categories from Numbeo data
    meal_inexp = data.get("meal_inexpensive", 8.0)
    meal_mid = data.get("meal_mid_range_2", 35.0)

    # Food: 3 meals/day (mix of inexpensive + mid-range)
    food_daily = round((meal_inexp * 2 + meal_mid * 0.25), 2)

    # Housing: from hotel_index (mid-range hotel per night)
    hotel_index = data.get("hotel_index", 80.0)
    housing_daily = round(hotel_index * 0.85, 2)

    # Local transport: 4 rides/day
    ticket = data.get("local_transport_ticket", 1.0)
    taxi_km = data.get("taxi_km", 0.80)
    local_transport_daily = round(ticket * 4 + taxi_km * 5, 2)

    # Activity: average attraction entry
    activity_daily = round(data.get("attraction_avg", 12.0), 2)

    # Shopping: daily shopping budget (new!)
    shopping_index = data.get("shopping_index", 50.0)
    shopping_daily = round(shopping_index * 0.35, 2)

    # Flight reference: rough geographic estimate
    flight_ref = _estimate_flight_cost(origin, destination, currency)

    cost_level = data.get("cost_level", "moderate")
    is_real = data.get("source", "").startswith("numbeo")

    return {
        "currency": currency,
        "cost_level": cost_level,
        "daily_index": {
            "food": food_daily,
            "activity": activity_daily,
            "housing": housing_daily,
            "local_transport": local_transport_daily,
            "shopping": shopping_daily,
        },
        "flight_reference": flight_ref,
        "reasoning": (
            f"Real Numbeo cost data for {destination}: {cost_level} cost level. "
            f"Food ~{currency} {food_daily:.0f}/day, housing ~{housing_daily:.0f}/night."
            if is_real
            else f"Estimated costs for {destination} ({cost_level} level). Connect Numbeo API for live data."
        ),
        "destination": destination,
        "source": data.get("source", "numbeo_database"),
        "verification_required": not is_real,
    }


def _estimate_flight_cost(origin: str, destination: str, currency: str) -> float:
    """Estimate round-trip flight cost based on geographic distance.

    This is a fallback — replace with real flight API when available.
    """
    from services.gaode_service import city_distance_km, CITY_COST_KM
    if origin and destination:
        try:
            dist = city_distance_km(origin, destination)
            return round(dist * CITY_COST_KM, 2)
        except Exception:
            pass
    return 850.0  # default


def get_shopping_guide(destination: str) -> dict:
    """Get shopping-specific guidance for the destination."""
    data = _get_city_data(destination)
    return {
        "destination": destination,
        "shopping_index": data.get("shopping_index", 50),
        "daily_shopping_estimate": round(data.get("shopping_index", 50) * 0.35, 2),
        "cost_level": data.get("cost_level", "moderate"),
        "note": (
            "Shopping budget based on Numbeo consumer price index. "
            "Includes souvenirs, local markets, and casual shopping."
        ),
    }
