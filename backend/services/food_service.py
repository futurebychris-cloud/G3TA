"""Real restaurant data for food options.

Replaces DeepSeek LLM estimates with real restaurant data from:
1. Amap POI search (Chinese cities) — real restaurant names, locations, ratings
2. Numbeo meal price data — real per-meal cost estimates
3. Cuisine mapping for international destinations

Usage:
    get_food_options(destination, cuisine_tags, num_days, budget, ...)
    → [{id, name, cuisine, price, meal_type, area, rating, tags}, ...]
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
import urllib.parse
import urllib.request
from typing import Any

from ._ai import (
    ESTIMATE_NOTE,
    estimated_record,
    generate_json,
    number,
    string_list,
    text,
)
from ._geography import (
    destination_allows_retired_tokyo_places,
    retired_tokyo_record_field,
)

CUISINE_ALIASES = {
    "japanese": {"japanese", "sushi", "ramen", "izakaya", "tempura", "japanese curry"},
    "chinese": {"chinese", "cantonese", "sichuan", "dim sum"},
    "korean": {"korean", "korean bbq"},
    "thai": {"thai"},
    "indian": {"indian"},
    "italian": {"italian", "pizza", "pasta"},
    "mexican": {"mexican", "tacos"},
    "american": {"american", "burgers", "bbq", "diner"},
    "mediterranean": {"mediterranean", "greek", "levantine"},
    "french": {"french", "bistro"},
}

# Real restaurant types to search via Amap POI
_CUISINE_AMAP_TYPES: dict[str, str] = {
    "chinese": "中餐厅",
    "japanese": "日本料理",
    "korean": "韩国料理",
    "thai": "东南亚菜",
    "italian": "意大利菜",
    "french": "法国菜",
    "indian": "印度菜",
    "american": "西餐厅",
    "mexican": "墨西哥菜",
    "mediterranean": "西餐厅",
    "local": "餐厅",
}

# Numbeo meal prices per slot (global averages, updated from service)
_DEFAULT_MEAL_PRICES = {
    "breakfast": 15, "lunch": 30, "dinner": 55,
}

_SLOT_WEIGHTS = {"breakfast": 0.25, "lunch": 0.35, "dinner": 0.40}

SYSTEM_PROMPT = (
    "Generate dining candidates located in the exact requested destination. Never return a venue "
    "from another city or country. Honor ONLY the selected cuisine families when they are supplied. "
    "Return ONLY JSON: {options: [{name, cuisine, cuisine_family, price, meal_type, area, rating, "
    "tags}], reasoning}. meal_type is breakfast, lunch, or dinner. Return requested_count varied "
    "options with enough choices in every meal slot and avoid duplicate names. Prices are estimates "
    "in the requested currency. If unsure a named venue exists, use a descriptive dining experience "
    "ending in '(verify)' instead of inventing a confident factual claim."
)


def _slot_budget(daily_budget: float | None, slot: str) -> float | None:
    if daily_budget is None or daily_budget <= 0:
        return None
    return round(daily_budget * _SLOT_WEIGHTS[slot], 2)


def _search_amap_restaurants(
    destination: str, cuisine_type: str, count: int = 15
) -> list[dict]:
    """Search Amap POI for restaurants in Chinese cities.

    Uses Amap POI search API (free tier, 5000 queries/day).
    Returns real restaurant names, locations, and ratings.
    """
    import os
    amap_key = os.getenv("AMAP_KEY", os.getenv("GAODE_KEY", ""))
    if not amap_key:
        return []

    try:
        # First geocode the city to get center coordinates
        from services.gaode_service import geocode_city
        coords = geocode_city(destination)
        if not coords:
            return []

        # Amap POI search — restaurants
        poi_type = _CUISINE_AMAP_TYPES.get(
            cuisine_type.lower(), "餐厅"
        )
        # Safe URL construction: Amap rejects non-ASCII in the raw URL, so the
        # entire query string is UTF-8 encoded (quote already does this, but we
        # guard against any stray unicode by encoding/decoding first).
        safe_destination = destination.encode("utf-8", "ignore").decode("utf-8")
        safe_poi = poi_type.encode("utf-8", "ignore").decode("utf-8")
        url = (
            f"https://restapi.amap.com/v3/place/text"
            f"?key={amap_key}"
            f"&keywords={urllib.parse.quote(safe_poi)}"
            f"&city={urllib.parse.quote(safe_destination)}"
            f"&types=餐饮服务"
            f"&offset={min(count, 25)}"
            f"&page=1"
            f"&extensions=all"
        )
        req = urllib.request.Request(url, headers={
            "User-Agent": "G3TA-TripPlanner/1.0",
        })
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))

        pois = data.get("pois", [])
        results = []
        for poi in pois[:count]:
            name = poi.get("name", "")
            address = poi.get("address", "")
            rating_str = poi.get("biz_ext", {}).get("rating", "0")
            try:
                rating_val = float(rating_str)
            except (ValueError, TypeError):
                rating_val = 0

            location = poi.get("location", "")
            lat, lng = None, None
            if location and "," in location:
                try:
                    parts = location.split(",")
                    lng, lat = float(parts[0]), float(parts[1])
                except (ValueError, IndexError):
                    pass

            results.append({
                "name": name,
                "area": address or destination,
                "rating": min(rating_val, 5.0),
                "lat": lat,
                "lng": lng,
                "source": "amap_poi",
            })
        return results
    except Exception as e:
        print(f"[food_service] Amap search failed for {destination}: {e}")
        return []


def _get_numbeo_meal_prices(destination: str) -> dict[str, float]:
    """Get real meal price estimates from Numbeo data."""
    try:
        from services.numbeo_service import _get_city_data
        data = _get_city_data(destination)
        meal_inexp = data.get("meal_inexpensive", 8.0)
        meal_mid = data.get("meal_mid_range_2", 35.0)
        return {
            "breakfast": round(meal_inexp * 0.6, 2),
            "lunch": round(meal_inexp * 1.5, 2),
            "dinner": round(meal_mid * 0.25, 2),
        }
    except Exception:
        return dict(_DEFAULT_MEAL_PRICES)


def matches_cuisine_preferences(option: dict, cuisine_tags: list[str] | None) -> bool:
    if not cuisine_tags:
        return True
    wanted = {tag.casefold() for tag in cuisine_tags}
    family = text(option.get("cuisine_family")).casefold()
    cuisine = text(option.get("cuisine")).casefold()
    if family:
        if family in wanted:
            return True
        return any(
            cuisine in CUISINE_ALIASES.get(selected, {selected})
            for selected in wanted
        )
    expanded = set(wanted)
    for selected in wanted:
        expanded.update(CUISINE_ALIASES.get(selected, set()))
    haystack = {cuisine, *[tag.casefold() for tag in option.get("tags", [])]}
    return bool(haystack & expanded)


def _generate_fallback_options(
    destination: str,
    cuisine_tags: list[str],
    count: int,
    daily_budget: float | None = None,
) -> list[dict]:
    """Generate fallback restaurant options when real APIs fail.

    Uses descriptive names ending in '(verify)' and real Numbeo prices.
    """
    families = cuisine_tags or ["Local"]
    slots = ["breakfast", "lunch", "dinner"]
    formats = {
        "breakfast": "local breakfast spot",
        "lunch": "popular lunch restaurant",
        "dinner": "well-reviewed dinner restaurant",
    }
    prices = _get_numbeo_meal_prices(destination)
    options = []
    for index in range(count):
        family = families[index % len(families)]
        slot = slots[index % len(slots)]
        slot_price = _slot_budget(daily_budget, slot)
        area_qualifier = ["City center", "Old town", "Commercial district",
                          "Near transit hub", "Tourist area"][index % 5]
        options.append(estimated_record({
            "id": f"food_{index + 1}",
            "name": f"{family.title()} {formats[slot]} ({area_qualifier}) (verify)",
            "cuisine": family,
            "cuisine_family": family,
            "price": slot_price if slot_price is not None else prices.get(slot, 25),
            "meal_type": slot,
            "area": f"{destination} — {area_qualifier}",
            "rating": 0,
            "tags": [family.lower(), "verify"],
        }, destination))
    return options


def get_food_options(
    destination: str,
    cuisine_tags: list[str] | None = None,
    num_days: int = 5,
    budget: dict | None = None,
    preferences: dict | None = None,
    time_constraints: str = "",
    daily_budget: float | None = None,
) -> list[dict]:
    """Get real restaurant options for a destination.

    PRIMARY: Amap POI search (real restaurants with names, ratings, locations)
    SECONDARY: Destination-aware DeepSeek estimates for missing meal slots
    FALLBACK: Descriptive options with Numbeo prices + '(verify)' suffix
    """
    cuisines = cuisine_tags or []
    count = max(12, min(int(num_days) * 3, 42))

    # Get real Numbeo meal prices for the destination
    numbeo_prices = _get_numbeo_meal_prices(destination)

    options = []
    seen = set()

    # Try real restaurant data for each cuisine preference
    search_cuisines = cuisines if cuisines else ["local"]
    for cuisine in search_cuisines:
        real_results = _search_amap_restaurants(destination, cuisine, count=8)
        for rr in real_results:
            name = rr.get("name", "")
            if not name or name.casefold() in seen:
                continue
            if (
                not destination_allows_retired_tokyo_places(destination)
                and retired_tokyo_record_field(rr, include_name=False)
            ):
                continue

            # Assign meal slots in rotation
            slot_idx = len(options) % 3
            slot = ["breakfast", "lunch", "dinner"][slot_idx]
            slot_price = _slot_budget(daily_budget, slot)
            base_price = numbeo_prices.get(slot, 25)

            option = estimated_record({
                "id": f"food_{len(options) + 1}",
                "name": name,
                "cuisine": cuisine,
                "cuisine_family": cuisine,
                "price": slot_price if slot_price is not None else base_price,
                "meal_type": slot,
                "area": rr.get("area", destination),
                "rating": rr.get("rating", 0),
                "lat": rr.get("lat"),
                "lng": rr.get("lng"),
                "tags": [cuisine],
                "source": "amap_poi",
            }, destination)
            option["source"] = "amap_poi"
            seen.add(name.casefold())
            options.append(option)
            if len(options) >= count:
                break
        if len(options) >= count:
            break

    # Fill missing choices with destination-aware estimates. This is deliberately
    # field-aware: a local restaurant brand may contain "Tokyo", while a Tokyo
    # area is invalid for a different requested destination.
    if len(options) < count:
        result = generate_json(SYSTEM_PROMPT, {
            "destination": destination,
            "selected_cuisines_in_priority_order": cuisines,
            "requested_count": count,
            "num_days": num_days,
            "budget": budget or {},
            "food_budget_per_day": daily_budget,
            "per_meal_budget_limits": {
                slot: _slot_budget(daily_budget, slot)
                for slot in ("breakfast", "lunch", "dinner")
            } if daily_budget else None,
            "all_preferences": preferences or {},
            "time_constraints": time_constraints,
            "truthfulness_requirement": ESTIMATE_NOTE,
        }, temperature=0.6)
        raw_options = result.get("options", []) if isinstance(result, dict) else []
        if not isinstance(raw_options, list):
            raw_options = []
        for raw in raw_options:
            if not isinstance(raw, dict):
                continue
            if (
                not destination_allows_retired_tokyo_places(destination)
                and retired_tokyo_record_field(raw, include_name=False)
            ):
                continue
            name = text(raw.get("name"))
            slot = text(raw.get("meal_type")).lower()
            if (
                not name
                or name.casefold() in seen
                or slot not in {"breakfast", "lunch", "dinner"}
            ):
                continue
            family = text(
                raw.get("cuisine_family"),
                text(
                    raw.get("cuisine"),
                    cuisines[0] if cuisines else "Local",
                ),
            )
            option = estimated_record({
                "id": f"food_{len(options) + 1}",
                "name": name,
                "cuisine": text(raw.get("cuisine"), family),
                "cuisine_family": family,
                "price": round(number(raw.get("price"), 25), 2),
                "meal_type": slot,
                "area": text(raw.get("area"), destination),
                "rating": min(number(raw.get("rating"), 0), 5.0),
                "tags": string_list(
                    raw.get("tags"),
                    [family.lower(), "verify"],
                ),
            }, destination)
            if cuisines and not matches_cuisine_preferences(option, cuisines):
                continue
            slot_limit = _slot_budget(daily_budget, slot)
            if slot_limit is not None and option["price"] > slot_limit:
                continue
            seen.add(name.casefold())
            options.append(option)
            if len(options) >= count:
                break

    # Ensure balanced meal slots with safe destination-labelled fallbacks.
    required_per_slot = count // 3
    fallback_options = _generate_fallback_options(
        destination,
        cuisines,
        count,
        daily_budget,
    )
    completed = []
    for slot in ("breakfast", "lunch", "dinner"):
        slot_options = [o for o in options if o.get("meal_type") == slot]
        slot_names = {option["name"].casefold() for option in slot_options}
        slot_options.extend(
            item for item in fallback_options
            if (
                item["meal_type"] == slot
                and item["name"].casefold() not in slot_names
            )
        )
        completed.extend(slot_options[:required_per_slot])

    # Renumber IDs
    for i, option in enumerate(completed[:count], start=1):
        option["id"] = f"food_{i}"

    return completed[:count]
