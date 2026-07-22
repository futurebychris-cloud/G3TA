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
import urllib.parse
import urllib.request

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GAODE_KEY = os.environ.get("GAODE_KEY", "").strip()
GAODE_BASE = "https://restapi.amap.com/v3"

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


def _geocode_single(address: str, city: str = "") -> tuple[float, float] | None:
    """Geocode a single address/POI name via Gaode API. Returns (lat, lng) or None."""
    if not GAODE_KEY:
        return None
    try:
        full_address = f"{city} {address}" if city else address
        url = (
            f"{GAODE_BASE}/geocode/geo?"
            + urllib.parse.urlencode({
                "key": GAODE_KEY, "address": full_address, "output": "JSON",
            })
        )
        req = urllib.request.Request(url, headers={"User-Agent": "G3TA/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
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
            url = (
                f"{GAODE_BASE}/geocode/geo?"
                + urllib.parse.urlencode({
                    "key": GAODE_KEY, "address": city, "output": "JSON",
                })
            )
            req = urllib.request.Request(url, headers={"User-Agent": "G3TA/1.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            if data.get("status") == "1" and data.get("geocodes"):
                loc = data["geocodes"][0]["location"].split(",")
                coords = (float(loc[1]), float(loc[0]))
                _CITY_COORDS[key] = coords
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


def geocode_poi(name: str, city: str = "", venue: str = "") -> tuple[float, float] | None:
    """Geocode a point-of-interest (attraction, hotel, landmark) to coordinates.

    Tries multiple search strategies in order:
    1. Full address: city + venue + name
    2. City + name
    3. Name only
    4. City center fallback

    Returns (lat, lng) or None.
    """
    # Strategy 1: most specific
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

    # Strategy 4: city center
    return geocode_city(city)


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
        return _haversine(coords_a[1], coords_a[0], coords_b[1], coords_b[0])
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
# Test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    for city in ["上海", "杭州", "北京"]:
        transport = get_local_transport(city, num_days=5)
        print(f"\n{city} ({transport['city_tier']}): "
              f"¥{transport['total_cost_cny']}/5 days")
        for m in transport["modes"]:
            print(f"  {m['mode']}: ¥{m['cost_per_day']}/day")
