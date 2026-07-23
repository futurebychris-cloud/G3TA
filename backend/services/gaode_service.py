"""Gaode Maps (高德地图) Local Transport Service.

Supports:
  1. Gaode Web API (with API key in GAODE_KEY env var):
     - Geocoding: city name → lat/lng
     - Route planning: driving/walking/transit between two points
  2. Free fallback (no key needed):
     - OpenStreetMap Nominatim for geocoding
     - OSRM for driving/walking routes
     - Fixed transit estimates for metro/bus

Usage:
    from services.gaode_service import get_local_transport, geocode_city
    coords = geocode_city("上海")
    routes = get_local_transport("杭州", "上海", num_days=5)
"""
from __future__ import annotations

import json
import math
import os
import re
import threading
import time
import urllib.parse
import urllib.request

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GAODE_KEY = os.environ.get("GAODE_KEY", os.environ.get("AMAP_KEY", "")).strip()
GAODE_BASE = "https://restapi.amap.com/v3"
_GAODE_REQUEST_LOCK = threading.Lock()
_GAODE_LAST_REQUEST_AT = 0.0
_GAODE_MIN_INTERVAL_SECONDS = 0.4
_GAODE_CITY_FILTERS: dict[str, str] = {}

# ---------------------------------------------------------------------------
# City coordinate cache (known Chinese cities)
# ---------------------------------------------------------------------------
_CITY_COORDS: dict[str, tuple[float, float]] = {
    "北京": (39.9042, 116.4074), "上海": (31.2304, 121.4737),
    "广州": (23.1291, 113.2644), "深圳": (22.5431, 114.0579),
    "杭州": (30.2741, 120.1551), "成都": (30.5728, 104.0668),
    "重庆": (29.4316, 106.9123), "西安": (34.3416, 108.9398),
    "南京": (32.0603, 118.7969), "武汉": (30.5928, 114.3055),
    "厦门": (24.4798, 118.0894), "昆明": (25.0389, 102.7183),
    "青岛": (36.0671, 120.3826), "大连": (38.9140, 121.6147),
    "苏州": (31.2990, 120.5853), "三亚": (18.2528, 109.5120),
    "天津": (39.3434, 117.3616), "长沙": (28.2282, 112.9388),
    "宁波": (29.8683, 121.5440), "郑州": (34.7466, 113.6253),
    "济南": (36.6512, 116.9972), "福州": (26.0745, 119.2965),
    "合肥": (31.8206, 117.2272), "南昌": (28.6820, 115.8582),
    "南宁": (22.8170, 108.3665), "贵阳": (26.6477, 106.6302),
    "兰州": (36.0611, 103.8343), "西宁": (36.6171, 101.7785),
    "银川": (38.4872, 106.2309), "呼和浩特": (40.8424, 111.7498),
    "乌鲁木齐": (43.8256, 87.6168), "拉萨": (29.6500, 91.1000),
    "哈尔滨": (45.8038, 126.5350), "长春": (43.8171, 125.3235),
    "沈阳": (41.8057, 123.4315), "石家庄": (38.0428, 114.5149),
    "太原": (37.8706, 112.5489), "桂林": (25.2742, 110.2896),
    "海口": (20.0174, 110.3492), "无锡": (31.4912, 120.3119),
    "温州": (28.0015, 120.6988), "珠海": (22.2707, 113.5767),
    "佛山": (23.0215, 113.1219),
}


def _gaode_json(path: str, params: dict, timeout: int = 8) -> dict:
    """Call a Gaode Web Service endpoint while respecting its per-key QPS limit."""
    global _GAODE_LAST_REQUEST_AT

    last_response = {}
    for attempt in range(3):
        with _GAODE_REQUEST_LOCK:
            delay = _GAODE_MIN_INTERVAL_SECONDS - (time.monotonic() - _GAODE_LAST_REQUEST_AT)
            if delay > 0:
                time.sleep(delay)
            url = f"{GAODE_BASE}{path}?" + urllib.parse.urlencode({
                "key": GAODE_KEY,
                "output": "JSON",
                **params,
            })
            req = urllib.request.Request(url, headers={"User-Agent": "G3TA/1.0"})
            _GAODE_LAST_REQUEST_AT = time.monotonic()
            with urllib.request.urlopen(req, timeout=timeout) as response:
                last_response = json.loads(response.read())

        if last_response.get("status") == "1":
            return last_response
        if last_response.get("info") != "CUQPS_HAS_EXCEEDED_THE_LIMIT":
            return last_response
        time.sleep(0.5 * (attempt + 1))
    return last_response


def _geocode_single(address: str, city: str = "") -> tuple[float, float] | None:
    """Geocode a single address/POI name via Gaode API. Returns (lat, lng) or None."""
    if not GAODE_KEY:
        return None
    try:
        full_address = f"{city} {address}" if city else address
        data = _gaode_json("/geocode/geo", {"address": full_address})
        if data.get("status") == "1" and data.get("geocodes"):
            loc = data["geocodes"][0]["location"].split(",")
            return (float(loc[1]), float(loc[0]))
    except Exception as e:
        print(f"[gaode] geocode '{address}' failed: {e}")
    return None


def geocode_city(city: str) -> tuple[float, float] | None:
    """Get lat/lng for a city name.

    Priority: built-in cache → Gaode API → OpenStreetMap Nominatim.
    """
    key = city.strip()
    if key in _CITY_COORDS:
        return _CITY_COORDS[key]
    lk = key.lower()
    for k, v in _CITY_COORDS.items():
        if k.lower() == lk:
            return v

    # Try Gaode geocoding API
    if GAODE_KEY:
        try:
            data = _gaode_json("/geocode/geo", {"address": city})
            if data.get("status") == "1" and data.get("geocodes"):
                geocode = data["geocodes"][0]
                loc = geocode["location"].split(",")
                coords = (float(loc[1]), float(loc[0]))
                _CITY_COORDS[key] = coords
                city_filter = geocode.get("adcode") or geocode.get("city") or geocode.get("province")
                if city_filter:
                    _GAODE_CITY_FILTERS[lk] = str(city_filter)
                return coords
        except Exception as e:
            print(f"[gaode] geocoding failed: {e}")

    # Fallback: OpenStreetMap Nominatim (free, no key)
    try:
        url = (
            "https://nominatim.openstreetmap.org/search?"
            + urllib.parse.urlencode({"q": city, "format": "json", "limit": 1})
        )
        req = urllib.request.Request(url, headers={
            "User-Agent": "G3TA/1.0 (trip planner)",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=8) as r:
            results = json.loads(r.read())
        if results:
            coords = (float(results[0]["lat"]), float(results[0]["lon"]))
            _CITY_COORDS[key] = coords
            return coords
    except Exception as e:
        print(f"[gaode] OSM geocoding failed: {e}")

    return None


def _gaode_city_filter(city: str) -> str:
    """Resolve Chinese or English city input to an AMap adcode for city-limited POI search."""
    key = city.strip().casefold()
    if not key or not GAODE_KEY:
        return city
    if key in _GAODE_CITY_FILTERS:
        return _GAODE_CITY_FILTERS[key]
    try:
        data = _gaode_json("/geocode/geo", {"address": city})
        if data.get("status") == "1" and data.get("geocodes"):
            geocode = data["geocodes"][0]
            city_filter = geocode.get("adcode") or geocode.get("city") or geocode.get("province")
            if city_filter:
                _GAODE_CITY_FILTERS[key] = str(city_filter)
                return str(city_filter)
    except Exception as e:
        print(f"[gaode] could not resolve city filter '{city}': {e}")
    return city


def _poi_keywords(name: str) -> str:
    """Prefer the Chinese part of a bilingual POI name because AMap ranks it more precisely."""
    chinese = "".join(re.findall(r"[\u3400-\u9fff]+", name))
    return chinese or name.strip()


def _geocode_poi_text(name: str, city: str = "", venue: str = "") -> tuple[float, float] | None:
    """Resolve a named POI with AMap Place Text Search rather than address geocoding."""
    if not GAODE_KEY or not name.strip():
        return None
    try:
        keywords = _poi_keywords(name)
        if venue:
            keywords = f"{keywords} {venue}".strip()
        params = {
            "keywords": keywords,
            "offset": 10,
            "page": 1,
            "extensions": "base",
        }
        if city:
            params.update({"city": _gaode_city_filter(city), "citylimit": "true"})
        data = _gaode_json("/place/text", params)
        for poi in data.get("pois") or []:
            location = str(poi.get("location") or "")
            if "," not in location:
                continue
            lng, lat = location.split(",", 1)
            return (float(lat), float(lng))
    except Exception as e:
        print(f"[gaode] POI search '{name}' failed: {e}")
    return None


def geocode_poi(name: str, city: str = "", venue: str = "") -> tuple[float, float] | None:
    """Geocode a point-of-interest (attraction, hotel, landmark) to coordinates.

    Tries multiple search strategies in order:
    1. City-limited AMap Place Text Search
    2. Full address: city + venue + name
    3. City + name
    4. Name only

    Returns (lat, lng) or None.
    """
    result = _geocode_poi_text(name, city, venue)
    if result:
        return result

    # Address fallback for hotels and POIs that are not present in Place Text Search.
    if venue and city:
        result = _geocode_single(f"{venue} {name}", city)
        if result:
            return result

    # Strategy 2: city + name
    if city:
        result = _geocode_single(name, city)
        if result:
            return result

    # Strategy 3: name only
    result = _geocode_single(name)
    if result:
        return result

    return None


def geocode_activities(activities: list[dict], city: str) -> list[dict]:
    """Add lat/lng to each activity dict by geocoding its name+location.

    Modifies activities in place and also returns them.
    Activities that already have lat/lng are skipped.
    """
    for act in activities:
        if "lat" in act and act["lat"] and "lng" in act and act["lng"]:
            continue
        name = act.get("name", "")
        act_city = act.get("location", "") or city
        venue = act.get("venue", act.get("address", ""))
        coords = geocode_poi(name, act_city, venue)
        if coords:
            act["lat"] = coords[0]
            act["lng"] = coords[1]
            print(f"[gaode] geocoded '{name}' → ({coords[0]:.4f}, {coords[1]:.4f})")
        else:
            print(f"[gaode] could not geocode '{name}'")
    return activities


# ---------------------------------------------------------------------------
# Haversine distance
# ---------------------------------------------------------------------------
def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in km between two lat/lng points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# Cost per km for transport fallback estimation (CNY/km)
# China HSR: ~0.5 CNY/km, flights: ~1.0 CNY/km
CITY_COST_KM = 0.75  # blended estimate


def city_distance_km(city_a: str, city_b: str) -> float:
    """Estimate distance in km between two city names.

    Uses cached coordinates + Haversine. Falls back to 800km default
    for unknown cities (reasonable for most China domestic routes).
    """
    coords_a = geocode_city(city_a)
    coords_b = geocode_city(city_b)
    if coords_a and coords_b:
        return _haversine(coords_a[0], coords_a[1], coords_b[0], coords_b[1])
    return 800.0  # default for unknown cities


# ---------------------------------------------------------------------------
# Route Planning
# ---------------------------------------------------------------------------
def _gaode_driving(origin_coords: tuple[float, float],
                   dest_coords: tuple[float, float]) -> dict | None:
    """Gaode driving route between two coordinates."""
    if not GAODE_KEY:
        return None
    try:
        url = (
            f"{GAODE_BASE}/direction/driving?"
            + urllib.parse.urlencode({
                "key": GAODE_KEY,
                "origin": f"{origin_coords[1]},{origin_coords[0]}",
                "destination": f"{dest_coords[1]},{dest_coords[0]}",
                "strategy": "0",
                "output": "JSON",
            })
        )
        req = urllib.request.Request(url, headers={"User-Agent": "G3TA/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        if data.get("status") == "1" and data.get("route", {}).get("paths"):
            path = data["route"]["paths"][0]
            return {
                "distance_km": round(float(path["distance"]) / 1000, 1),
                "duration_min": round(float(path["duration"]) / 60, 0),
                "toll": float(path.get("tolls", 0)),
                "source": "gaode",
            }
    except Exception as e:
        print(f"[gaode] driving route failed: {e}")
    return None


def _osrm_route(origin_coords: tuple[float, float],
                dest_coords: tuple[float, float],
                profile: str = "driving") -> dict | None:
    """Free OSRM routing (OpenStreetMap-based, no API key)."""
    try:
        url = (
            f"https://router.project-osrm.org/route/v1/{profile}/"
            f"{origin_coords[1]},{origin_coords[0]};"
            f"{dest_coords[1]},{dest_coords[0]}?"
            f"overview=false&alternatives=false&steps=false"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "G3TA/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        if data.get("code") == "Ok" and data.get("routes"):
            route = data["routes"][0]
            return {
                "distance_km": round(route["distance"] / 1000, 1),
                "duration_min": round(route["duration"] / 60, 0),
                "source": "osrm",
            }
    except Exception as e:
        print(f"[gaode] OSRM route failed: {e}")
    return None


# ---------------------------------------------------------------------------
# Local Transport Estimation
# ---------------------------------------------------------------------------
# Daily cost estimates by city tier (CNY/day), used as fallback
_CITY_TIER_COSTS: dict[str, dict[str, float]] = {
    # Tier 1: subway + taxi/bus estimates
    "tier1": {"metro": 12, "bus": 4, "taxi": 60, "bike": 5, "walk": 0},
    "tier2": {"metro": 8,  "bus": 3, "taxi": 40, "bike": 3, "walk": 0},
    "tier3": {"metro": 5,  "bus": 2, "taxi": 25, "bike": 2, "walk": 0},
}

_TIER_MAP: dict[str, str] = {
    "北京": "tier1", "上海": "tier1", "广州": "tier1", "深圳": "tier1",
    "杭州": "tier1", "成都": "tier1", "重庆": "tier1", "武汉": "tier1",
    "南京": "tier1", "天津": "tier1", "苏州": "tier1", "西安": "tier1",
    "长沙": "tier1", "厦门": "tier1", "青岛": "tier1", "大连": "tier1",
    "郑州": "tier1", "济南": "tier1", "合肥": "tier1", "福州": "tier1",
    "宁波": "tier2", "无锡": "tier2", "昆明": "tier2", "南宁": "tier2",
    "贵阳": "tier2", "南昌": "tier2", "沈阳": "tier2", "长春": "tier2",
    "哈尔滨": "tier2", "石家庄": "tier2", "太原": "tier2", "温州": "tier2",
    "珠海": "tier2", "佛山": "tier2", "海口": "tier2", "桂林": "tier2",
}


def get_local_transport(city: str, num_days: int = 1,
                        num_attractions: int = 3) -> dict:
    """Estimate local transport costs for a trip.

    Uses Gaode/OSRM for inter-attraction distances when coordinates are available.

    Returns:
        {modes: [...], total_cost_cny: float, daily_breakdown: {...},
         currency: "CNY", has_real_routing: bool}
    """
    coords = geocode_city(city)
    city_tier = _TIER_MAP.get(city, "tier2")
    costs = _CITY_TIER_COSTS.get(city_tier, _CITY_TIER_COSTS["tier2"])

    # Try Gaode route between city center and a typical attraction area
    has_real_routing = False
    route_info = None

    if coords:
        # Simulate a typical daily trip: hotel → attraction1 → attraction2 → hotel
        # Use a nearby point (~5km offset) to simulate attraction location
        offset_lat = 0.03  # ~3km
        offset_lng = 0.04  # ~3km
        attraction_coords = (coords[0] + offset_lat, coords[1] + offset_lng)

        if GAODE_KEY:
            route_info = _gaode_driving(coords, attraction_coords)
            if route_info:
                has_real_routing = True
                print(f"[gaode] real route: {route_info['distance_km']}km, "
                      f"{route_info['duration_min']}min by car")

        if not route_info:
            route_info = _osrm_route(coords, attraction_coords, "driving")
            if route_info:
                has_real_routing = True
                print(f"[gaode] OSRM route: {route_info['distance_km']}km, "
                      f"{route_info['duration_min']}min by car")

    # Build per-day estimates
    if route_info:
        # Use real distances to adjust taxi estimates
        daily_distance_km = route_info["distance_km"] * 3  # 3 trips/day
        taxi_cost_per_day = round(daily_distance_km * 2.5, 1)  # ~2.5 CNY/km
        metro_cost_per_day = (
            3 if daily_distance_km < 10 else
            5 if daily_distance_km < 30 else 8
        )
    else:
        taxi_cost_per_day = costs["taxi"]
        metro_cost_per_day = costs["metro"]

    modes = [
        {"mode": "metro/subway", "cost_per_day": metro_cost_per_day,
         "currency": "CNY", "notes": f"{city}地铁"},
        {"mode": "bus", "cost_per_day": costs["bus"],
         "currency": "CNY", "notes": "公共汽车"},
        {"mode": "taxi/ride-hail", "cost_per_day": taxi_cost_per_day,
         "currency": "CNY", "notes": "滴滴/出租车"},
        {"mode": "bike/scooter", "cost_per_day": costs["bike"],
         "currency": "CNY", "notes": "共享单车/电动车"},
        {"mode": "walk", "cost_per_day": 0,
         "currency": "CNY", "notes": "步行可达区域"},
    ]

    daily_total = sum(m["cost_per_day"] for m in modes)
    total = round(daily_total * num_days, 1)

    return {
        "modes": modes,
        "total_cost_cny": total,
        "daily_total_cny": daily_total,
        "daily_breakdown": {m["mode"]: m["cost_per_day"] for m in modes},
        "city": city,
        "city_tier": city_tier,
        "coords": coords,
        "num_days": num_days,
        "route_sample": route_info,
        "currency": "CNY",
        "has_real_routing": has_real_routing,
    }


# ---------------------------------------------------------------------------
# Gaode POI Search — Real restaurant & attraction data
# ---------------------------------------------------------------------------

def search_restaurants(
    city: str,
    keywords: str = "",
    cuisine: str = "",
    max_results: int = 15,
) -> list[dict]:
    """Search restaurants via Gaode POI API with real ratings and price data.

    Uses Gaode's POI (Point of Interest) search API:
        GET https://restapi.amap.com/v3/place/text?keywords=...&types=餐饮&city=...

    Returns list of restaurant dicts with real data:
        {name, address, rating, price_level, cuisine_type, lat, lng, source}
    """
    if not GAODE_KEY:
        return _fallback_restaurant_search(city, keywords, cuisine, max_results)

    try:
        search_keywords = keywords or cuisine or f"{city} 美食"
        types_code = "050000|060000"  # 餐饮 + 购物(含美食广场)

        url = (
            f"{GAODE_BASE}/place/text?"
            + urllib.parse.urlencode({
                "key": GAODE_KEY,
                "keywords": search_keywords,
                "types": types_code,
                "city": city,
                "citylimit": "true",
                "offset": min(max_results, 25),
                "page": 1,
                "extensions": "all",
                "output": "JSON",
            })
        )
        req = urllib.request.Request(url, headers={"User-Agent": "G3TA/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())

        if data.get("status") != "1":
            print(f"[gaode] POI search failed: {data.get('info', 'unknown')}")
            return _fallback_restaurant_search(city, keywords, cuisine, max_results)

        pois = data.get("pois", [])
        if not pois:
            return _fallback_restaurant_search(city, keywords, cuisine, max_results)

        restaurants = []
        for poi in pois:
            name = poi.get("name", "")
            if not name:
                continue

            # Gaode POI fields
            address = poi.get("address", "")
            rating_str = poi.get("biz_ext", {}).get("rating", "0")
            cost_str = poi.get("biz_ext", {}).get("cost", "0")
            typecode = poi.get("typecode", "")

            # Parse rating
            try:
                rating = float(rating_str)
            except (ValueError, TypeError):
                rating = 0

            # Parse average cost per person
            try:
                avg_cost = float(cost_str) if cost_str else 0
            except (ValueError, TypeError):
                avg_cost = 0

            # Determine cuisine type from POI type code
            cuisine_type = _classify_cuisine_from_typecode(typecode, cuisine)

            # Parse location
            location = poi.get("location", "")
            lat, lng = 0.0, 0.0
            if location and "," in location:
                parts = location.split(",")
                try:
                    lng = float(parts[0])
                    lat = float(parts[1])
                except (ValueError, IndexError):
                    pass

            # Parse deep-info (photos, business hours, phone)
            deep_info = poi.get("deep_info", {}) or {}
            photos = []
            for photo_item in deep_info.get("photos", [])[:3]:
                if isinstance(photo_item, dict) and photo_item.get("url"):
                    photos.append(photo_item["url"])

            restaurants.append({
                "name": name,
                "address": address,
                "cuisine_type": cuisine_type,
                "rating": round(rating, 1),
                "avg_cost": round(avg_cost, 0),
                "price_level": _cost_to_price_level(avg_cost),
                "lat": lat,
                "lng": lng,
                "photos": photos,
                "source": "gaode_poi",
                "city": city,
            })

        # Sort by rating descending
        restaurants.sort(key=lambda r: r["rating"], reverse=True)
        restaurants = restaurants[:max_results]

        print(f"[gaode] POI search: {len(restaurants)} restaurants in {city} "
              f"(avg rating: {sum(r['rating'] for r in restaurants)/max(len(restaurants),1):.1f})")
        return restaurants

    except Exception as e:
        print(f"[gaode] POI restaurant search failed: {e}")
        return _fallback_restaurant_search(city, keywords, cuisine, max_results)


def _cost_to_price_level(avg_cost: float) -> int:
    """Convert average cost per person to price level (1-4)."""
    if avg_cost <= 0:
        return 2
    if avg_cost < 50:
        return 1
    if avg_cost < 120:
        return 2
    if avg_cost < 250:
        return 3
    return 4


def _classify_cuisine_from_typecode(typecode: str, default_cuisine: str) -> str:
    """Classify cuisine type from Gaode POI type code."""
    code = typecode.lower() if typecode else ""
    cuisine_map = {
        "050100": "中餐厅", "050101": "中餐厅", "050102": "中餐厅",
        "050200": "外国餐厅", "050201": "西餐", "050202": "日韩料理",
        "050300": "小吃快餐", "050400": "咖啡厅", "050500": "茶艺馆",
        "050600": "冷饮店", "050700": "糕饼店", "050800": "甜品店",
        "060100": "火锅", "060200": "烧烤", "060300": "自助餐",
        "060400": "海鲜", "060500": "私房菜",
    }
    for key, val in cuisine_map.items():
        if code.startswith(key):
            return val
    # Fall back to extracting keywords
    code_lower = code.lower()
    for kw, label in [
        ("hotpot", "火锅"), ("bbq", "烧烤"), ("western", "西餐"),
        ("japanese", "日料"), ("korean", "韩餐"), ("seafood", "海鲜"),
        ("cafe", "咖啡"), ("buffet", "自助"), ("noodle", "面食"),
        ("sushi", "日料"), ("pizza", "西餐"),
    ]:
        if kw in code_lower:
            return label
    return default_cuisine or "中餐厅"


def _fallback_restaurant_search(
    city: str, keywords: str = "", cuisine: str = "", max_results: int = 10
) -> list[dict]:
    """Fallback restaurant search using OSM Nominatim when Gaode key is unavailable."""
    restaurants = []
    try:
        query = f"restaurant {cuisine or keywords or ''} {city}"
        url = (
            "https://nominatim.openstreetmap.org/search?"
            + urllib.parse.urlencode({
                "q": query.strip(),
                "format": "json",
                "limit": max_results,
                "addressdetails": 1,
                "namedetails": 1,
            })
        )
        req = urllib.request.Request(url, headers={
            "User-Agent": "G3TA/1.0 (trip planner)",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=10) as r:
            results = json.loads(r.read())

        for item in results:
            name = (item.get("namedetails", {}) or {}).get("name") or item.get("display_name", "").split(",")[0]
            lat = float(item.get("lat", 0))
            lon = float(item.get("lon", 0))
            if name and lat and lon:
                restaurants.append({
                    "name": name.strip(),
                    "address": item.get("display_name", ""),
                    "cuisine_type": cuisine or "Local",
                    "rating": 0,
                    "avg_cost": 0,
                    "price_level": 2,
                    "lat": lat,
                    "lng": lon,
                    "photos": [],
                    "source": "osm_fallback",
                    "city": city,
                })
    except Exception as e:
        print(f"[gaode] OSM fallback search failed: {e}")

    return restaurants


def search_attraction_pois(
    city: str,
    keywords: str = "",
    max_results: int = 10,
) -> list[dict]:
    """Search attractions/tourist sites via Gaode POI API.

    Returns list with: {name, address, rating, ticket_price, lat, lng, source}
    """
    if not GAODE_KEY:
        return []

    try:
        search_keywords = keywords or f"{city} 景点"
        url = (
            f"{GAODE_BASE}/place/text?"
            + urllib.parse.urlencode({
                "key": GAODE_KEY,
                "keywords": search_keywords,
                "types": "110000|120000|140000|170000",  # 风景名胜|公园|纪念馆|旅游景点
                "city": city,
                "citylimit": "true",
                "offset": min(max_results, 25),
                "page": 1,
                "extensions": "all",
                "output": "JSON",
            })
        )
        req = urllib.request.Request(url, headers={"User-Agent": "G3TA/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())

        if data.get("status") != "1":
            return []

        pois = data.get("pois", [])
        attractions = []
        for poi in pois:
            name = poi.get("name", "")
            if not name:
                continue

            rating_str = poi.get("biz_ext", {}).get("rating", "0")
            try:
                rating = float(rating_str)
            except (ValueError, TypeError):
                rating = 0

            # Try to get ticket price from deep_info or biz_ext
            ticket_price = 0
            biz_ext = poi.get("biz_ext", {}) or {}
            deep_info = poi.get("deep_info", {}) or {}

            # Check for ticket price in various fields
            for price_field in ["ticket_price", "cost", "price", "admission"]:
                val = biz_ext.get(price_field, "") or deep_info.get(price_field, "")
                if val:
                    try:
                        ticket_price = float(str(val).replace("¥", "").replace(",", ""))
                        break
                    except (ValueError, TypeError):
                        pass

            location = poi.get("location", "")
            lat, lng = 0.0, 0.0
            if location and "," in location:
                parts = location.split(",")
                try:
                    lng = float(parts[0])
                    lat = float(parts[1])
                except (ValueError, IndexError):
                    pass

            attractions.append({
                "name": name,
                "address": poi.get("address", ""),
                "rating": round(rating, 1),
                "ticket_price": round(ticket_price, 0),
                "lat": lat,
                "lng": lng,
                "source": "gaode_poi",
                "city": city,
                "place_id": poi.get("id", ""),
            })

        attractions.sort(key=lambda a: a["rating"], reverse=True)
        return attractions[:max_results]

    except Exception as e:
        print(f"[gaode] POI attraction search failed: {e}")
        return []


def get_route_path(
    origin_lat: float, origin_lng: float,
    dest_lat: float, dest_lng: float,
    mode: str = "driving",
) -> list[tuple[float, float]] | None:
    """Get the actual route polyline path between two points via Gaode API.

    Used for rendering real road routes on the frontend map (not straight lines).

    Args:
        origin_lat/lng: Starting point
        dest_lat/lng: Destination
        mode: "driving", "walking", "transit"

    Returns:
        List of (lat, lng) coordinate pairs tracing the route path, or None on failure.
    """
    if not GAODE_KEY:
        return None

    try:
        direction_type = mode if mode in ("driving", "walking", "transit") else "driving"
        url = (
            f"{GAODE_BASE}/direction/{direction_type}?"
            + urllib.parse.urlencode({
                "key": GAODE_KEY,
                "origin": f"{origin_lng},{origin_lat}",
                "destination": f"{dest_lng},{dest_lat}",
                "strategy": "0",
                "output": "JSON",
            })
        )
        req = urllib.request.Request(url, headers={"User-Agent": "G3TA/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())

        if data.get("status") != "1":
            print(f"[gaode] routing failed: {data.get('info', 'unknown')}")
            return None

        route = data.get("route", {})
        paths = route.get("paths", [])
        if not paths:
            return None

        # Get the polyline from the first path
        steps = paths[0].get("steps", [])
        if not steps:
            return None

        # Gaode returns encoded polylines per step — decode them
        all_points: list[tuple[float, float]] = []
        for step in steps:
            polyline = step.get("polyline", "")
            if polyline:
                points = _decode_gaode_polyline(polyline, origin_lat, origin_lng, dest_lat, dest_lng)
                all_points.extend(points)

        if all_points:
            print(f"[gaode] route path: {len(all_points)} points, "
                  f"{paths[0].get('distance', '?')}m, {paths[0].get('duration', '?')}s")
            return all_points

        return None

    except Exception as e:
        print(f"[gaode] route path query failed: {e}")
        return None


def _decode_gaode_polyline(
    polyline: str,
    o_lat: float, o_lng: float,
    d_lat: float, d_lng: float,
) -> list[tuple[float, float]]:
    """Decode a Gaode-encoded polyline string into lat/lng pairs.

    Gaode uses a variation of Google's polyline encoding with slight differences.
    This decoder tries multiple strategies.
    """
    if not polyline:
        return []

    points = []
    i = 0
    current_lat = 0
    current_lng = 0

    try:
        # Try standard Google-style polyline decoding
        # Gaode format uses semicolon-separated "lng,lat" pairs
        if ";" in polyline:
            for pair in polyline.split(";"):
                parts = pair.strip().split(",")
                if len(parts) >= 2:
                    try:
                        lng = float(parts[0])
                        lat = float(parts[1])
                        points.append((lat, lng))
                    except ValueError:
                        continue
                elif len(parts) == 1 and parts[0].strip():
                    # Single coordinate pair
                    try:
                        parts2 = parts[0].split()
                        if len(parts2) >= 2:
                            lng = float(parts2[0])
                            lat = float(parts2[1])
                            points.append((lat, lng))
                    except ValueError:
                        continue
        else:
            # Try Google polyline algorithm (Gaode uses same encoding)
            while i < len(polyline):
                # Decode latitude
                shift = 0
                result = 0
                while i < len(polyline):
                    byte = ord(polyline[i]) - 63
                    i += 1
                    result |= (byte & 0x1F) << shift
                    shift += 5
                    if not (byte & 0x20):
                        break
                if result & 1:
                    current_lat += ~(result >> 1)
                else:
                    current_lat += (result >> 1)

                # Decode longitude
                shift = 0
                result = 0
                while i < len(polyline):
                    byte = ord(polyline[i]) - 63
                    i += 1
                    result |= (byte & 0x1F) << shift
                    shift += 5
                    if not (byte & 0x20):
                        break
                if result & 1:
                    current_lng += ~(result >> 1)
                else:
                    current_lng += (result >> 1)

                points.append((current_lat / 1e5, current_lng / 1e5))

            if points:
                return points

    except Exception:
        pass

    # If all decoding failed, return start and end points
    return [(o_lat, o_lng), (d_lat, d_lng)]


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    for city in ["上海", "杭州", "北京"]:
        transport = get_local_transport(city, num_days=5)
        print(f"\n{city} ({transport['city_tier']}): "
              f"¥{transport['total_cost_cny']}/5 days")
        for m in transport["modes"]:
            print(f"  {m['mode']}: ¥{m['cost_per_day']}/day")
