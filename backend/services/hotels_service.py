"""Lodging data source — PRIMARY real-API layer.

This is the "API system" for hotel information. It is a pluggable set of real
hotel APIs selected by the credentials you configure (no single one is required):

    hotelbeds  HBX Group (ex-Amadeus-style) free self-service Evaluation Key
               (HOTELS_HOTELBEDS_KEY / _SECRET, optional _DEST_CODE)
    amadeus    Amadeus Enterprise Hotel Search  (HOTELS_AMADEUS_KEY / _SECRET)
    rapidapi   a RapidAPI hotel-search provider (HOTELS_RAPIDAPI_KEY + _HOST)
    tongcheng  同程旅仓 hotel list  (HOTELS_TONGCHENG_ACCOUNT)
    elong      艺龙开放平台          (HOTELS_ELONG_KEY)  — partner account required

CRITICAL — no hardcoded fallback:
    If no provider is configured, or every configured provider fails / returns no
    data, this module RAISES (it never serves a fake hotel list). The caller
    (services/hotels_provider.py) then falls back to the Playwright Ctrip pipeline,
    and finally to OpenStreetMap. This guarantees the planner only ever shows real
    data — never fabricated/hardcoded hotels.

All providers return the SAME normalized shape so no agent code has to change:
    [{"id", "name", "price_per_night", "rating", "area", "lat", "lng", "tags"}]
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

from ._geography import destination_allows_retired_tokyo_places, retired_tokyo_record_field

_PROVIDERS = ("hotelbeds", "amadeus", "rapidapi", "tongcheng", "elong")
_HTTP_TIMEOUT = 15


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def get_hotel_options(
    destination: str,
    dates: dict,
    max_price_per_night: float | None = None,
    budget: dict | None = None,
    preferences: dict | None = None,
) -> list[dict]:
    """Return real hotel options from the first configured provider that succeeds.

    Raises RuntimeError if no provider is configured or all configured providers
    fail — the caller should then fall back to the Playwright Ctrip pipeline.
    """
    for name in _PROVIDERS:
        try:
            fn = _DISPATCH[name]
            out = fn(destination, dates, max_price_per_night)
            if out:
                if not destination_allows_retired_tokyo_places(destination):
                    out = [
                        option for option in out
                        if isinstance(option, dict) and not retired_tokyo_record_field(option)
                    ]
                if out:
                    return out
        except Exception as exc:  # a missing key or a network error is not fatal here
            print(f"[hotels] provider '{name}' unavailable ({exc}); trying next.")
    raise RuntimeError(
        "No hotel API provider returned data (no HOTELS_* keys configured, or all "
        "calls failed). Caller should fall back to the Playwright Ctrip pipeline."
    )


_DISPATCH = {
    "hotelbeds": _hotelbeds if False else None,  # placeholder, wired below
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _nights(dates: dict) -> int:
    d0 = date.fromisoformat(dates["start"])
    d1 = date.fromisoformat(dates["end"])
    if d1 < d0:
        d0, d1 = d1, d0
    return max((d1 - d0).days, 1)


def _http_json(url: str, headers: dict | None = None, data: dict | bytes | None = None, method: str = "GET"):
    req = urllib.request.Request(url, headers=headers or {}, method=method)
    if data is not None:
        if isinstance(data, (bytes, bytearray)):
            req.data = bytes(data)
        else:
            req.data = json.dumps(data).encode("utf-8")
            req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


# --------------------------------------------------------------------------- #
# Amadeus (Enterprise Hotel Search)
# --------------------------------------------------------------------------- #
def _amadeus(destination, dates, max_price_per_night):
    key = os.getenv("HOTELS_AMADEUS_KEY")
    secret = os.getenv("HOTELS_AMADEUS_SECRET")
    if not (key and secret):
        raise RuntimeError("HOTELS_AMADEUS_KEY / HOTELS_AMADEUS_SECRET not set")

    token = _http_json(
        "https://api.amadeus.com/v1/security/oauth2/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=urllib.parse.urlencode(
            {"grant_type": "client_credentials", "client_id": key, "client_secret": secret}
        ).encode("utf-8"),
        method="POST",
    )["access_token"]

    city = destination.split(",")[0].strip()
    params = {
        "cityCode": city[:3].upper(),
        "checkInDate": dates["start"],
        "checkOutDate": dates["end"],
        "adults": 1,
        "radius": 20,
        "radiusUnit": "KM",
    }
    if max_price_per_night is not None:
        params["priceRange"] = f"1-{int(max_price_per_night)}"
    url = "https://api.amadeus.com/v3/shopping/hotel-offers?" + urllib.parse.urlencode(params)
    resp = _http_json(url, headers={"Authorization": f"Bearer {token}"})

    nights = _nights(dates)
    out = []
    for entry in resp.get("data", []):
        hotel = entry.get("hotel", {})
        offer = (entry.get("offers") or [{}])[0]
        price_total = float((offer.get("price") or {}).get("total", 0) or 0)
        out.append({
            "id": hotel.get("hotelId", f"ama_{len(out)}"),
            "name": hotel.get("name", "Unknown"),
            "price_per_night": round(price_total / nights, 2) if nights and price_total else (price_total or 0),
            "rating": float(hotel.get("rating") or 0) or None,
            "area": (hotel.get("address") or {}).get("cityName", city),
            "lat": float(hotel.get("latitude", 0) or 0),
            "lng": float(hotel.get("longitude", 0) or 0),
            "tags": [],
        })
    if not out:
        raise RuntimeError("Amadeus returned no offers for this destination")
    return out


# --------------------------------------------------------------------------- #
# Hotelbeds / HBX Group API Suite — self-service free Evaluation Key
# --------------------------------------------------------------------------- #

# City → (lat, lng) mapping for geolocation search (test API dest codes unreliable)
_HB_CITY_COORDS: dict[str, tuple[float, float]] = {
    "shanghai": (31.23, 121.47), "beijing": (39.90, 116.41),
    "guangzhou": (23.13, 113.26), "shenzhen": (22.54, 114.06),
    "hangzhou": (30.27, 120.16), "chengdu": (30.57, 104.07),
    "chongqing": (29.43, 106.91), "xian": (34.34, 108.94),
    "nanjing": (32.06, 118.80), "wuhan": (30.59, 114.31),
    "xiamen": (24.48, 118.09), "kunming": (25.04, 102.72),
    "qingdao": (36.07, 120.38), "dalian": (38.91, 121.61),
    "suzhou": (31.30, 120.59), "sanya": (18.25, 109.51),
    "tianjin": (39.34, 117.36), "changsha": (28.23, 112.94),
    "ningbo": (29.87, 121.54), "guiyang": (26.65, 106.63),
    "harbin": (45.80, 126.53), "shenyang": (41.80, 123.43),
    "zhengzhou": (34.75, 113.63), "jinan": (36.67, 116.98),
    "hefei": (31.82, 117.23), "fuzhou": (26.07, 119.30),
    "nanchang": (28.68, 115.86), "taiyuan": (37.87, 112.55),
    "lhasa": (29.65, 91.10), "urumqi": (43.83, 87.62),
    "tokyo": (35.68, 139.76), "osaka": (34.69, 135.50),
    "seoul": (37.57, 126.98), "bangkok": (13.75, 100.50),
    "singapore": (1.35, 103.82), "hongkong": (22.32, 114.17),
    "hong kong": (22.32, 114.17),
    "北京": (39.90, 116.41), "上海": (31.23, 121.47),
    "广州": (23.13, 113.26), "深圳": (22.54, 114.06),
    "杭州": (30.27, 120.16), "成都": (30.57, 104.07),
    "重庆": (29.43, 106.91), "西安": (34.34, 108.94),
    "南京": (32.06, 118.80), "武汉": (30.59, 114.31),
    "厦门": (24.48, 118.09), "昆明": (25.04, 102.72),
    "青岛": (36.07, 120.38), "大连": (38.91, 121.61),
    "苏州": (31.30, 120.59), "三亚": (18.25, 109.51),
    "天津": (39.34, 117.36), "长沙": (28.23, 112.94),
    "宁波": (29.87, 121.54), "贵阳": (26.65, 106.63),
    "哈尔滨": (45.80, 126.53), "沈阳": (41.80, 123.43),
    "郑州": (34.75, 113.63), "济南": (36.67, 116.98),
    "合肥": (31.82, 117.23), "福州": (26.07, 119.30),
    "南昌": (28.68, 115.86), "太原": (37.87, 112.55),
    "拉萨": (29.65, 91.10), "乌鲁木齐": (43.83, 87.62),
}


def _geocode_hotelbeds(city: str) -> tuple[float, float]:
    """Resolve city name to lat/lng for Hotelbeds geolocation search."""
    key = city.lower().strip().split(",")[0].strip()
    if key in _HB_CITY_COORDS:
        return _HB_CITY_COORDS[key]
    # Try Open-Meteo geocoding as fallback
    try:
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city)}&count=1&language=en"
        req = urllib.request.Request(url, headers={"User-Agent": "G3TA/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        if data.get("results"):
            r = data["results"][0]
            return r["latitude"], r["longitude"]
    except Exception as exc:
        raise RuntimeError(f"Could not geocode Hotelbeds destination '{city}'.") from exc
    raise RuntimeError(f"Could not geocode Hotelbeds destination '{city}'.")


def _hotelbeds(destination, dates, max_price_per_night):
    key = os.getenv("HOTELS_HOTELBEDS_KEY")
    secret = os.getenv("HOTELS_HOTELBEDS_SECRET")
    if not (key and secret):
        raise RuntimeError("HOTELS_HOTELBEDS_KEY / HOTELS_HOTELBEDS_SECRET not set")

    city = destination.split(",")[0].strip()
    lat, lng = _geocode_hotelbeds(city)

    ts = int(time.time())
    sig = hashlib.sha256(f"{key}{secret}{ts}".encode("utf-8")).hexdigest()
    headers = {
        "Api-key": key,
        "X-Signature": sig,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    base = os.getenv("HOTELS_HOTELBEDS_BASE", "https://api.test.hotelbeds.com")

    body: dict = {
        "stay": {"checkIn": dates["start"], "checkOut": dates["end"]},
        "occupancies": [{"rooms": 1, "adults": 1, "children": 0}],
        "geolocation": {"latitude": lat, "longitude": lng, "radius": 20, "unit": "km"},
    }
    if max_price_per_night:
        body["filter"] = {"maxRate": int(max_price_per_night)}

    url = f"{base}/hotel-api/1.0/hotels"
    print(f"[hotelbeds] request: dest={destination}, city={city}, lat={lat}, lng={lng}")
    print(f"[hotelbeds] key={key[:8]}..., ts={ts}, sig={sig[:16]}...")
    print(f"[hotelbeds] body={json.dumps(body)}")

    try:
        resp = _http_json(url, headers=headers, data=body, method="POST")
        print(f"[hotelbeds] success: got response keys={list(resp.keys()) if isinstance(resp, dict) else 'N/A'}")
    except Exception as exc:
        # Try to get the response body for better error diagnostics
        try:
            req = urllib.request.Request(url, headers=headers, method="POST")
            req.data = json.dumps(body).encode("utf-8")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as r:
                pass  # shouldn't reach here if exc was raised
        except urllib.error.HTTPError as http_err:
            err_body = http_err.read().decode("utf-8", errors="replace")
            print(f"[hotelbeds] HTTP {http_err.code} response body: {err_body[:500]}")
        except Exception:
            pass
        raise exc

    nights = _nights(dates)
    wrapper = resp.get("hotels") or {}
    hotels = wrapper.get("hotels") if isinstance(wrapper, dict) else wrapper
    if not isinstance(hotels, list):
        hotels = []

    def _net(h):
        for room in h.get("rooms") or []:
            for rate in room.get("rates") or []:
                net = rate.get("net")
                if net:
                    return float(net)
        return 0.0

    out = []
    for h in hotels:
        total = _net(h)
        if not total:
            continue
        cat = h.get("categoryCode") or ""
        rating = float(cat[0]) if cat[:1].isdigit() else None
        out.append({
            "id": str(h.get("code") or f"hb_{len(out)}"),
            "name": h.get("name", "Unknown"),
            "price_per_night": round(total / nights, 2) if nights else total,
            "rating": rating,
            "area": h.get("zoneName") or h.get("destinationName") or city,
            "lat": float(h.get("latitude") or 0),
            "lng": float(h.get("longitude") or 0),
            "tags": [],
        })
    if not out:
        raise RuntimeError("Hotelbeds returned no hotels (check DEST_CODE + key activation)")
    return out


# --------------------------------------------------------------------------- #
# RapidAPI (self-serve hotel-search aggregator)
# --------------------------------------------------------------------------- #
def _rapidapi(destination, dates, max_price_per_night):
    key = os.getenv("HOTELS_RAPIDAPI_KEY")
    host = os.getenv("HOTELS_RAPIDAPI_HOST")
    if not (key and host):
        raise RuntimeError("HOTELS_RAPIDAPI_KEY / HOTELS_RAPIDAPI_HOST not set")

    params = {
        "destination": destination,
        "checkin": dates["start"],
        "checkout": dates["end"],
        "adults1": "1",
        "pageNumber": "1",
    }
    if max_price_per_night is not None:
        params["priceMax"] = str(int(max_price_per_night))
    url = f"https://{host}/hotels/search?" + urllib.parse.urlencode(params)
    resp = _http_json(url, headers={"X-RapidAPI-Key": key, "X-RapidAPI-Host": host})

    rows = resp.get("data") or resp.get("results") or []
    out = []
    for i, h in enumerate(rows):
        prop = h.get("property") or h
        price = h.get("price") or {}
        price_val = float(price.get("totalPrice") or price.get("lead") or price.get("integer") or 0)
        out.append({
            "id": str(prop.get("id") or h.get("id") or f"rap_{i}"),
            "name": prop.get("name") or h.get("name") or "Unknown",
            "price_per_night": price_val,
            "rating": float(prop.get("rating") or h.get("rating") or 0) or None,
            "area": prop.get("address") or h.get("neighborhood") or "",
            "lat": float(prop.get("latitude") or h.get("latitude") or 0),
            "lng": float(prop.get("longitude") or h.get("longitude") or 0),
            "tags": [],
        })
    if not out:
        raise RuntimeError("RapidAPI provider returned no hotels")
    return out


# --------------------------------------------------------------------------- #
# 同程旅仓 (Tongcheng Lvcang) — partner account required
# --------------------------------------------------------------------------- #
def _tongcheng(destination, dates, max_price_per_night):
    account = os.getenv("HOTELS_TONGCHENG_ACCOUNT")
    if not account:
        raise RuntimeError("HOTELS_TONGCHENG_ACCOUNT (x-lvcang-api-account) not set")

    url = os.getenv("HOTELS_TONGCHENG_URL", "https://open.lvcang.cn/hotel/list")
    body = {
        "cityName": destination.split(",")[0].strip(),
        "checkIn": dates["start"],
        "checkOut": dates["end"],
        "pageIndex": 1,
        "pageSize": 20,
    }
    if max_price_per_night is not None:
        body["maxPrice"] = int(max_price_per_night)
    resp = _http_json(url, headers={"x-lvcang-api-account": account}, data=body, method="POST")

    rows = (resp.get("data") or {}).get("hotelList") or resp.get("hotels") or []
    out = []
    for i, h in enumerate(rows):
        out.append({
            "id": str(h.get("hotelId") or f"tc_{i}"),
            "name": h.get("hotelName") or "Unknown",
            "price_per_night": float(h.get("lowRate") or 0),
            "rating": float(h.get("starRate") or h.get("category") or 0) or None,
            "area": h.get("businessZoneName") or h.get("districtName") or "",
            "lat": float(h.get("latitude") or 0),
            "lng": float(h.get("longitude") or 0),
            "tags": [],
        })
    if not out:
        raise RuntimeError("同程旅仓 returned no hotels (verify account + endpoint)")
    return out


# --------------------------------------------------------------------------- #
# 艺龙开放平台 (eLong) — partner account required
# --------------------------------------------------------------------------- #
def _elong(destination, dates, max_price_per_night):
    raise RuntimeError(
        "艺龙 (eLong) requires an approved partner account + endpoint. "
        "Set HOTELS_ELONG_* and implement the call here, or use 'tongcheng' / 'amadeus'."
    )


_DISPATCH = {
    "hotelbeds": _hotelbeds,
    "amadeus": _amadeus,
    "rapidapi": _rapidapi,
    "tongcheng": _tongcheng,
    "elong": _elong,
}
