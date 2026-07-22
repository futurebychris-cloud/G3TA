"""OpenStreetMap (Overpass) real-hotel provider — the authorized emergency tier.

WHY THIS EXISTS
    The user's hotel data comes from (1) the real multi-provider API system and
    (2) the Playwright Ctrip pipeline. If BOTH are unreachable in a given
    environment (no API keys configured, or Ctrip blocks headless automation),
    we still must never serve hardcoded/fake hotels. OpenStreetMap is a genuinely
    real, no-auth, fast data source: it returns actual hotels with real names,
    coordinates, and star ratings for any destination.

HONEST LIMITATION
    OSM has no live prices or availability. `price_per_night` is therefore None and
    the UI labels the card "price to confirm on provider". This is real data, just
    without a rate — never a fabricated number.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]
_HTTP_TIMEOUT = 20
_LODGING = "hotel|guest_house|hostel|apartment|motel|chalet"

# Common typos → canonical city name (case‑insensitive key)
_CITY_TYPOS: dict[str, str] = {
    "shanhai": "Shanghai", "shanghi": "Shanghai", "shaghai": "Shanghai",
    "bejing": "Beijing", "tokoyo": "Tokyo", "singpore": "Singapore",
    "bangkock": "Bangkok", "seol": "Seoul", "newyork": "New York",
    "losangeles": "Los Angeles", "sanfransisco": "San Francisco",
    "barcalona": "Barcelona", "parice": "Paris", "londan": "London",
}

# Hardcoded coords for major cities — last-resort fallback when Nominatim fails
_CITY_COORDS: dict[str, tuple[float, float]] = {
    "shanghai": (31.23, 121.47), "beijing": (39.90, 116.41),
    "guangzhou": (23.13, 113.26), "shenzhen": (22.54, 114.06),
    "hangzhou": (30.27, 120.16), "chengdu": (30.57, 104.07),
    "chongqing": (29.43, 106.91), "xian": (34.34, 108.94),
    "nanjing": (32.06, 118.80), "wuhan": (30.59, 114.31),
    "xiamen": (24.48, 118.09), "kunming": (25.04, 102.72),
    "qingdao": (36.07, 120.38), "dalian": (38.91, 121.61),
    "sanya": (18.25, 109.51), "tianjin": (39.34, 117.36),
    "tokyo": (35.68, 139.65), "osaka": (34.69, 135.50),
    "kyoto": (35.01, 135.77), "seoul": (37.57, 126.98),
    "bangkok": (13.76, 100.50), "singapore": (1.35, 103.82),
    "hong kong": (22.32, 114.17), "paris": (48.86, 2.35),
    "london": (51.51, -0.13), "new york": (40.71, -74.01),
    "los angeles": (34.05, -118.24), "san francisco": (37.77, -122.42),
    "barcelona": (41.39, 2.17),
}


def _normalize_city(name: str) -> str:
    """Correct known typos & strip noise so Nominatim has a better chance."""
    key = name.strip().lower().replace(" ", "")
    if key in _CITY_TYPOS:
        corrected = _CITY_TYPOS[key]
        print(f"[osm] typo corrected: {name!r} → {corrected!r}")
        return corrected
    return name


def _geocode(name: str) -> tuple[float, float] | None:
    """Geocode via Nominatim with typo-correction + hardcoded-fallback."""
    name = _normalize_city(name)

    # 1) Try Nominatim
    url = _NOMINATIM + "?" + urllib.parse.urlencode(
        {"q": name.strip(), "format": "json", "limit": 1}
    )
    req = urllib.request.Request(url, headers={"User-Agent": "G3TA-TripPlanner/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass

    # 2) Hardcoded coords for well-known cities
    key = name.strip().lower()
    if key in _CITY_COORDS:
        print(f"[osm] using built-in coords for {name!r}")
        return _CITY_COORDS[key]

    return None


def _overpass_query(center: tuple[float, float], radius_deg: float, limit: int) -> dict | None:
    """Run the node-only Overpass lodging query for `center` at the given radius.

    Returns the parsed JSON on the first endpoint that responds, or None if *every*
    endpoint failed to respond (network/timeout). We only ever query ``node`` lodging
    — querying ``way``/``relation`` triggers Overpass 504 timeouts on dense city areas,
    while mapped hotels-as-nodes are abundant enough for the emergency tier.
    """
    lat, lng = center
    d = radius_deg
    bbox = f"{lat - d},{lng - d},{lat + d},{lng + d}"
    query = (
        f"[out:json][timeout:{_HTTP_TIMEOUT}];"
        f'node["tourism"~"{_LODGING}"]({bbox});'
        f'out center {limit * 5};'
    )
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    for endpoint in _OVERPASS_ENDPOINTS:
        req = urllib.request.Request(
            endpoint,
            data=body,
            headers={"User-Agent": "G3TA-TripPlanner/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            continue
    return None


def search_osm_hotels(
    location: str,
    max_price_per_night=None,
    min_rating=None,
    preferences: list[str] | None = None,
    limit: int = 12,
) -> list[dict]:
    """Return real lodging POIs around `location` from OpenStreetMap Overpass.

    Progressively widens the search radius (≈9 km → ≈17 km → ≈33 km) because the
    geocoded center can land in a sparse spot where a fixed box finds no lodging.
    Only raises "no lodging" after every radius returns an empty result set.
    """
    center = _geocode(location)
    if center is None:
        raise RuntimeError(f"OpenStreetMap could not geocode {location!r}")

    data = None
    for radius in (0.08, 0.15, 0.30):
        data = _overpass_query(center, radius, limit)
        if data is None:
            continue  # all endpoints failed to respond; try next radius anyway
        if data.get("elements"):
            break  # got results, parse below
    if data is None:
        raise RuntimeError("OpenStreetMap Overpass query failed: all endpoints unreachable")
    if not data.get("elements"):
        raise RuntimeError("OpenStreetMap returned no lodging for this area")

    prefs = {p.lower() for p in (preferences or [])}
    out = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:en")
        if not name:
            continue
        stars = tags.get("stars") or tags.get("hotel_stars")
        rating = float(stars) if (stars and str(stars).replace(".", "", 1).isdigit()) else None
        if min_rating is not None and (rating or 0) < min_rating:
            continue
        # Derive a couple of light tags from OSM attributes for preference matching.
        # (Abstract prefs like "central"/"quiet" aren't representable in OSM, so we
        # never hard-skip on them — ranking handles any tag matches downstream.)
        tags_list = []
        if tags.get("internet_access") in ("wlan", "wifi"):
            tags_list.append("wifi")
        if tags.get("breakfast") == "yes":
            tags_list.append("breakfast")
        if tags.get("wheelchair") == "yes":
            tags_list.append("accessible")
        if tags.get("stars"):
            tags_list.append("premium" if float(stars) >= 4 else "midrange")
        out.append({
            "id": f"osm_{el['id']}",
            "name": name,
            "price_per_night": None,  # OSM has no live price — never fabricated
            "rating": rating,
            "area": tags.get("addr:suburb") or tags.get("addr:city") or "",
            "lat": el.get("lat"),
            "lng": el.get("lon"),
            "tags": tags_list,
            "url": f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
            "currency": "",
            "source": "openstreetmap",
        })
        if len(out) >= limit:
            break

    if not out:
        raise RuntimeError("OpenStreetMap returned no lodging for this area")
    # Rank: known rating first, then by name.
    out.sort(key=lambda h: (h["rating"] or 0), reverse=True)
    return out
