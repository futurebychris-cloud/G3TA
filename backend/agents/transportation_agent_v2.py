"""Transportation Agent v2 (Route Scout) — multi-source transport comparison.

Data sources (tried in priority order):
  1. 12306.cn public endpoint → current Chinese train records when available
  2. Ctrip public flight/train pages through Playwright
  3. Configured flight providers
  4. Gaode Maps / OSRM → local distance and cost estimates

If providers fail, clearly labeled estimates may keep the plan usable. Every
option carries source metadata and requires verification before purchase.

Output: {"options": [...], "recommended": {...}, "cost": number,
         "local_transport_cost": number, "scrape_status": "ok"|"partial"|"failed",
         "errors": [...]}
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
import urllib.parse

from services.flights_service import get_flight_options
from services.runtime_cache import cached_call

from .base import llm_reason, report_progress, trip_days

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

CHINA_CITIES = {
    "北京", "上海", "广州", "深圳", "杭州", "成都", "重庆", "西安", "南京", "武汉",
    "厦门", "昆明", "青岛", "大连", "苏州", "三亚", "天津", "长沙",
    "beijing", "shanghai", "guangzhou", "shenzhen", "hangzhou",
    "chengdu", "chongqing", "xian", "nanjing", "wuhan", "xiamen",
}

TRANSPORT_PROMPT = (
    "You are the Transportation Agent (Route Scout). From the given transport "
    "options, pick the best one "
    "balancing price, duration, and user preferences. "
    "Prefer live provider records; clearly labeled estimates are a fallback only. "
    "Return ONLY a JSON object with keys: recommended_id and reasoning."
)


def _route_point(option: dict, prefix: str, label: str, role: str) -> dict | None:
    """Build a map-safe route point only from explicitly AMap-compatible coordinates."""
    lat = option.get(f"{prefix}_lat")
    lng = option.get(f"{prefix}_lng")
    coordinate_system = str(option.get("coordinate_system") or "").casefold()
    coordinate_system = coordinate_system.replace("_", "-").replace(" ", "")
    if (
        coordinate_system not in {"gcj-02", "gcj02", "amap", "amap-compatible"}
        or isinstance(lat, bool)
        or isinstance(lng, bool)
        or not isinstance(lat, (int, float))
        or not isinstance(lng, (int, float))
        or not math.isfinite(lat)
        or not math.isfinite(lng)
        or not -90 <= lat <= 90
        or not -180 <= lng <= 180
    ):
        return None
    return {
        "label": label,
        "type": "transport",
        "role": role,
        "lat": lat,
        "lng": lng,
        "coordinate_system": "GCJ-02",
    }


def _route_metadata(origin: str, destination: str, recommended: dict) -> tuple[list[dict], dict]:
    departure = recommended.get("departure_airport") or recommended.get("from") or origin
    arrival = recommended.get("arrival_airport") or recommended.get("to") or destination
    points = [
        _route_point(recommended, "departure", departure, "departure"),
        _route_point(recommended, "arrival", arrival, "arrival"),
    ]
    return [point for point in points if point], {
        "mode": recommended.get("mode") or recommended.get("type") or "flight",
        "origin": origin,
        "destination": destination,
        "departure_airport": departure,
        "arrival_airport": arrival,
        "carrier": recommended.get("carrier"),
        "departure_time": recommended.get("departure_time"),
        "duration": recommended.get("duration"),
        "stops": recommended.get("stops", 0),
    }


# --------------------------------------------------------------------------- #
# Shared stealth browser (reuses ctrip.py's anti-detection setup)
# --------------------------------------------------------------------------- #

def _stealth_browser():
    """Get a stealth Playwright browser. Tries ctrip.py's full anti-detection
    setup first; falls back to a minimal browser if ctrip is not importable."""
    try:
        from booking.ctrip import _stealth_browser as ctrip_browser
        return ctrip_browser()
    except Exception:
        pass
    # Minimal fallback
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True, args=[
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox", "--disable-gpu",
    ])
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/131.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
        locale="zh-CN",
    )
    page = ctx.new_page()
    page.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
    )
    return pw, browser, page


# --------------------------------------------------------------------------- #
# Scope detection
# --------------------------------------------------------------------------- #

def _detect_scope(origin: str, destination: str) -> str:
    o = origin.lower().strip()
    d = destination.lower().strip()
    if any(c in o for c in CHINA_CITIES) and any(c in d for c in CHINA_CITIES):
        return "national"
    return "international"


# --------------------------------------------------------------------------- #
# Airport IATA code mapping for international routes
# --------------------------------------------------------------------------- #

AIRPORT_CODES = {
    "new york": "nyc", "shanghai": "sha", "beijing": "bjs", "tokyo": "tyo",
    "london": "lon", "paris": "par", "los angeles": "lax", "chicago": "chi",
    "san francisco": "sfo", "seattle": "sea", "boston": "bos", "miami": "mia",
    "toronto": "yto", "vancouver": "yvr", "sydney": "syd", "melbourne": "mel",
    "singapore": "sin", "bangkok": "bkk", "seoul": "sel", "hong kong": "hkg",
    "taipei": "tpe", "kuala lumpur": "kul", "dubai": "dxb", "frankfurt": "fra",
    "munich": "muc", "rome": "rom", "milan": "mil", "madrid": "mad",
    "barcelona": "bcn", "amsterdam": "ams", "moscow": "mow", "istanbul": "ist",
    "guangzhou": "can", "shenzhen": "szx", "chengdu": "ctu", "hangzhou": "hgh",
    "xian": "sia", "nanjing": "nkg", "wuhan": "wuh", "xiamen": "xmn",
    "kunming": "kmg", "qingdao": "tao", "dalian": "dlc", "suzhou": "szv",
    "sanya": "syx", "changsha": "csx", "tianjin": "tsn", "chongqing": "ckg",
}


def _resolve_airport_code(city: str) -> str:
    """Resolve a city name to an IATA code. Falls back to lowercase city name."""
    key = city.lower().strip()
    return AIRPORT_CODES.get(key, key.replace(" ", "-"))


# --------------------------------------------------------------------------- #
# Ctrip Flight Scraping — REAL prices from __NEXT_DATA__
# --------------------------------------------------------------------------- #

def _scrape_ctrip_flights(origin: str, destination: str, date_str: str) -> tuple[list[dict], str | None]:
    """Scrape real-time flight prices from Ctrip flights page.

    Uses Playwright to load the Ctrip domestic/international flights search
    page, then extracts structured flight data from the __NEXT_DATA__ JSON
    (Next.js SSR payload). Falls back to DOM scraping of rendered cards.

    Returns: (flights_list, error_string_or_None)
    """
    flights = []
    pw = None
    error = None

    try:
        pw, browser, page = _stealth_browser()

        scope = _detect_scope(origin, destination)
        enc_origin = urllib.parse.quote(origin)
        enc_dest = urllib.parse.quote(destination)

        if scope == "national":
            # Ctrip domestic flights search URL
            url = (
                f"https://flights.ctrip.com/international/search/domestic?"
                f"dcity={enc_origin}&acity={enc_dest}&ddate={date_str}"
            )
        else:
            # Ctrip international flights: use IATA airport codes
            origin_code = _resolve_airport_code(origin)
            dest_code = _resolve_airport_code(destination)
            url = (
                f"https://flights.ctrip.com/international/search/oneway-"
                f"{origin_code}-{dest_code}?"
                f"depdate={date_str}&cabin=y_s&adult=1&child=0&infant=0"
            )

        print(f"[transport] navigating to Ctrip flights ({scope}): {origin}→{destination} {date_str}")
        print(f"[transport] URL: {url}")
        navigation_response = page.goto(
            url, timeout=30000, wait_until="domcontentloaded"
        )
        time.sleep(5)  # let JS render flight list

        # Log what URL we actually landed on (Ctrip may redirect)
        actual_url = page.url
        if actual_url != url:
            print(f"[transport] redirected to: {actual_url[:120]}")
        else:
            print(f"[transport] page loaded at: {actual_url[:120]}")

        # --- Strategy 1: __NEXT_DATA__ JSON (most reliable) ---
        content = page.content()
        response_status = (
            navigation_response.status if navigation_response is not None else None
        )
        if response_status == 432 or "whaleguard block" in content.lower():
            error = (
                "Ctrip flight request was blocked by WhaleGuard"
                + (f" (HTTP {response_status})" if response_status else "")
                + ". Use a valid logged-in Ctrip browser session and retry; "
                "the scraper does not bypass verification challenges."
            )
            return flights, error
        m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', content)
        if m:
            try:
                data = json.loads(m.group(1))
                flight_list = (
                    data.get("props", {})
                    .get("initialState", {})
                    .get("flight", {})
                    .get("list", [])
                )
                if not flight_list:
                    # Try alternate path: initialState.flights.flightList
                    flight_list = (
                        data.get("props", {})
                        .get("initialState", {})
                        .get("flights", {})
                        .get("flightList", [])
                    )

                for i, f in enumerate(flight_list):
                    if not isinstance(f, dict):
                        continue
                    flight_no = (
                        f.get("flightNo") or f.get("flightNumber")
                        or f.get("flight_number", "")
                    )
                    airline = f.get("airlineName") or f.get("airline", "")
                    price_raw = (
                        f.get("adultPrice") or f.get("price")
                        or f.get("lowestPrice", 0)
                    )
                    price = float(price_raw) if price_raw else 0
                    depart = f.get("departureDate") or f.get("depTime", "")
                    arrive = f.get("arrivalDate") or f.get("arrTime", "")

                    if price > 0:
                        flights.append({
                            "id": f"ctrip_f{i}",
                            "carrier": airline or "Unknown",
                            "flight_number": str(flight_no),
                            "departure_time": str(depart),
                            "arrival_time": str(arrive),
                            "price": round(price),
                            "currency": "CNY",
                            "stops": f.get("stopCount", 0) if isinstance(f.get("stopCount"), int) else 0,
                            "from": origin,
                            "to": destination,
                            "type": "flight",
                            "source": "ctrip_live",
                        })
                if flights:
                    print(f"[transport] Ctrip flights __NEXT_DATA__: {len(flights)} results")
            except Exception as e:
                print(f"[transport] __NEXT_DATA__ parse failed: {e}")

        # --- Strategy 2: DOM scraping (fallback if __NEXT_DATA__ fails) ---
        if not flights:
            cards = page.query_selector_all(
                ".flight-item, .flight-card, [class*='flight-list'] > div, "
                "[class*='FlightItem'], li[class*='flight']"
            )
            for i, card in enumerate(cards[:15]):
                try:
                    text = card.inner_text()
                    # Extract flight number pattern like MU5101, CA1234
                    fn_matches = re.findall(r'([A-Z]{2}\d{3,4})', text)
                    flight_no = fn_matches[0] if fn_matches else ""

                    # Extract price: ¥1,234 or CNY 1,234
                    price_matches = re.findall(r'[¥￥]\s*([\d,]+)', text)
                    if not price_matches:
                        price_matches = re.findall(r'CNY\s*([\d,]+)', text, re.IGNORECASE)
                    price = float(price_matches[0].replace(",", "")) if price_matches else 0

                    # Extract times
                    times = re.findall(r'(\d{2}:\d{2})', text)
                    depart = times[0] if times else ""
                    arrive = times[-1] if len(times) > 1 else ""

                    if price > 0:
                        flights.append({
                            "id": f"ctrip_dom_{i}",
                            "carrier": "",
                            "flight_number": flight_no,
                            "departure_time": depart,
                            "arrival_time": arrive,
                            "price": round(price),
                            "currency": "CNY",
                            "stops": 0,
                            "from": origin,
                            "to": destination,
                            "type": "flight",
                            "source": "ctrip_live",
                        })
                except Exception:
                    continue

            if flights:
                print(f"[transport] Ctrip flights DOM: {len(flights)} results")

        if not flights:
            error = (
                f"Ctrip flights page loaded but no flights extracted for "
                f"{origin}→{destination} on {date_str}. The page may require "
                f"login or the DOM structure has changed."
            )

    except Exception as e:
        error = f"Flight scraping failed: {e}"
        print(f"[transport] {error}")
    finally:
        if pw:
            try:
                pw.stop()
            except Exception:
                pass

    return flights, error


# --------------------------------------------------------------------------- #
# Ctrip Train Scraping — REAL prices from Ctrip trains page
# --------------------------------------------------------------------------- #

def _scrape_ctrip_trains(origin: str, destination: str, date_str: str) -> tuple[list[dict], str | None]:
    """Scrape real-time train prices from Ctrip's train booking page.

    Ctrip resells 12306 tickets and shows real prices in the search results.
    This is easier to scrape than 12306 directly (no CAPTCHA gate).

    Returns: (trains_list, error_string_or_None)
    """
    trains = []
    pw = None
    error = None

    try:
        pw, browser, page = _stealth_browser()

        # Ctrip train search URL
        enc_origin = urllib.parse.quote(origin)
        enc_dest = urllib.parse.quote(destination)
        url = (
            f"https://trains.ctrip.com/trainbooking/search?"
            f"from={enc_origin}&to={enc_dest}&date={date_str}"
        )
        print(f"[transport] navigating to Ctrip trains: {origin}→{destination} {date_str}")
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        time.sleep(5)  # let JS render train list

        content = page.content()

        # --- Strategy 1: __NEXT_DATA__ or __INITIAL_STATE__ ---
        for pattern in [
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
        ]:
            m = re.search(pattern, content, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
                    # Try multiple possible paths into the train list
                    train_list = None
                    for path in [
                        ["props", "initialState", "train", "list"],
                        ["props", "initialState", "trains", "trainList"],
                        ["props", "pageProps", "trainList"],
                        ["trainList"],
                    ]:
                        d = data
                        for key in path:
                            d = d.get(key, {}) if isinstance(d, dict) else {}
                        if isinstance(d, list) and d:
                            train_list = d
                            break

                    if train_list:
                        for i, t in enumerate(train_list):
                            if not isinstance(t, dict):
                                continue
                            price = (
                                t.get("price") or t.get("secondClassPrice")
                                or t.get("priceSecond") or 0
                            )
                            if float(price) > 0:
                                trains.append({
                                    "id": f"ctrip_tr_{i}",
                                    "type": "train",
                                    "train_number": str(t.get("trainNo") or t.get("trainNumber") or ""),
                                    "carrier": "中国铁路",
                                    "from": origin,
                                    "to": destination,
                                    "departure_time": str(t.get("departTime") or t.get("depTime") or ""),
                                    "arrival_time": str(t.get("arriveTime") or t.get("arrTime") or ""),
                                    "duration": str(t.get("duration") or t.get("runTime") or ""),
                                    "price": round(float(price)),
                                    "currency": "CNY",
                                    "stops": 0,
                                    "source": "ctrip_live_train",
                                })
                    if trains:
                        break
                except Exception as e:
                    print(f"[transport] train JSON parse failed ({pattern[:30]}): {e}")

        # --- Strategy 2: DOM scraping ---
        if not trains:
            rows = page.query_selector_all(
                "tr[id^='ticket_'], .train-item, .train-card, "
                "[class*='train-list'] > div, [class*='TrainItem'], "
                "li[class*='train']"
            )
            for i, row in enumerate(rows[:20]):
                try:
                    text = row.inner_text()
                    # Train number: G102, D310, K180 etc
                    tn = re.findall(r'([GDCKZT]\d{2,5})', text)
                    train_no = tn[0] if tn else ""

                    # Price
                    prices = re.findall(r'[¥￥]\s*([\d,]+)', text)
                    price = float(prices[0].replace(",", "")) if prices else 0

                    # Times
                    times = re.findall(r'(\d{2}:\d{2})', text)
                    depart = times[0] if times else ""
                    arrive = times[-1] if len(times) > 1 else ""

                    if price > 0:
                        trains.append({
                            "id": f"ctrip_tr_dom_{i}",
                            "type": "train",
                            "train_number": train_no,
                            "carrier": "中国铁路",
                            "from": origin,
                            "to": destination,
                            "departure_time": depart,
                            "arrival_time": arrive,
                            "duration": "",
                            "price": round(price),
                            "currency": "CNY",
                            "stops": 0,
                            "source": "ctrip_live_train",
                        })
                except Exception:
                    continue

            if trains:
                print(f"[transport] Ctrip trains DOM: {len(trains)} results")

        if not trains:
            error = (
                f"Ctrip trains page loaded but no trains extracted for "
                f"{origin}→{destination} on {date_str}. The page may need "
                f"login or the route is not served by Ctrip trains."
            )

    except Exception as e:
        error = f"Train scraping failed: {e}"
        print(f"[transport] {error}")
    finally:
        if pw:
            try:
                pw.stop()
            except Exception:
                pass

    return trains, error


# --------------------------------------------------------------------------- #
# Local transport (not bookable — fixed daily estimates are the industry norm)
# --------------------------------------------------------------------------- #

def _local_transport_options(city: str) -> list[dict]:
    """Local transport modes + estimated daily costs for a Chinese city."""
    return [
        {"mode": "subway", "estimated_cost_per_day": 15, "currency": "CNY",
         "notes": "Metro system coverage"},
        {"mode": "taxi/ride-hail", "estimated_cost_per_day": 80, "currency": "CNY",
         "notes": "Didi/taxi for 3-4 rides"},
        {"mode": "bus", "estimated_cost_per_day": 6, "currency": "CNY",
         "notes": "Public bus"},
        {"mode": "bike/scooter", "estimated_cost_per_day": 10, "currency": "CNY",
         "notes": "Shared bikes"},
        {"mode": "walk", "estimated_cost_per_day": 0, "currency": "CNY",
         "notes": "Walkable areas"},
    ]


# --------------------------------------------------------------------------- #
# Main agent
# --------------------------------------------------------------------------- #

def run(trip_input: dict) -> dict:
    """Run the transport agent using provider records plus labeled fallbacks.

    Returns:
        {
            options: [...], recommended: {...}, cost: number,
            local_transport_cost: number, scope: str, reasoning: str,
            destination: str, scrape_status: "ok"|"partial"|"failed",
            errors: [str], verification_required: True, trip_id: str
        }
    """
    origin = trip_input.get("origin", "北京")
    destination = trip_input["location"]
    dates = trip_input["dates"]
    trip_id = trip_input.get("trip_id", hashlib.sha256(
        f"{origin}{destination}{dates['start']}".encode()).hexdigest()[:12])
    preferences = trip_input.get("preferences", {})
    transport_types = preferences.get("transportation_type", []) if isinstance(preferences, dict) else []
    requested_modes = [
        str(mode).strip().lower()
        for mode in transport_types
        if str(mode).strip()
    ] or ["flight"]
    wants_flight = any(mode in {"flight", "plane", "air"} for mode in requested_modes)
    wants_train = any(mode in {"train", "rail"} for mode in requested_modes)
    wants_car = any(mode in {"car", "drive", "driving"} for mode in requested_modes)

    scope = _detect_scope(origin, destination)
    errors: list[str] = []
    all_options: list[dict] = []
    days = trip_days(trip_input)

    # ---- Phase 1: Honor the requested intercity modes --------------------
    if wants_car:
        report_progress(trip_input, "正在通过高德计算城际驾车路线")
        try:
            from services.gaode_service import get_intercity_driving
            road = cached_call(
                "transport-intercity-driving",
                (origin, destination),
                lambda: get_intercity_driving(origin, destination),
                ttl_seconds=1800,
            )
            if road:
                duration_min = int(float(road.get("duration_min", 0) or 0))
                hours, minutes = divmod(duration_min, 60)
                duration = (
                    f"{hours}h {minutes}m" if hours
                    else f"{minutes}m"
                )
                car_option = {
                    "id": "amap-driving-route",
                    "type": "car",
                    "mode": "car",
                    "carrier": "AMap driving route",
                    "from": origin,
                    "to": destination,
                    "departure_time": "Flexible",
                    "arrival_time": "Route-dependent",
                    "duration": duration,
                    "distance_km": road.get("distance_km"),
                    "price": road.get("estimated_cost_cny", 0),
                    "currency": "CNY",
                    "stops": 0,
                    "source": f"{road.get('source', 'road')}_route_cost_estimate",
                    "price_basis": road.get("cost_basis"),
                }
                if road.get("coordinate_system") == "GCJ-02":
                    car_option.update({
                        "coordinate_system": "GCJ-02",
                        "departure_lat": road["origin_lat"],
                        "departure_lng": road["origin_lng"],
                        "arrival_lat": road["destination_lat"],
                        "arrival_lng": road["destination_lng"],
                    })
                all_options.append(car_option)
        except Exception as exc:
            errors.append(f"Driving route unavailable: {exc}")

    if wants_flight:
        report_progress(trip_input, "正在查询航班与实时票价")
        flights, flight_err = cached_call(
            "transport-flights",
            (origin, destination, dates["start"]),
            lambda: _scrape_ctrip_flights(origin, destination, dates["start"]),
            ttl_seconds=900,
            persist=True,
            source="ctrip_playwright_flights",
        )
        if flight_err:
            print(f"[transport] FLIGHT ERROR: {flight_err}")
            errors.append(flight_err)
        if flights:
            print(f"[transport] got {len(flights)} flights, prices: {[f['price'] for f in flights[:3]]}...")
            all_options.extend(flights)

    # ---- Phase 2: 12306 trains (preferred for domestic China) ----
    if wants_train and scope == "national":
        report_progress(trip_input, "正在查询 12306 列车班次")
        try:
            from services.train12306_service import search_trains as search_12306
            trains_12306 = cached_call(
                "transport-12306",
                (origin, destination, dates["start"]),
                lambda: search_12306(origin, destination, dates["start"]),
                ttl_seconds=300,
            )
            if trains_12306:
                real_price_count = sum(1 for t in trains_12306 if "real_price" in t.get("source", ""))
                for t in trains_12306:
                    source_label = t.get("source", "12306_live")
                    all_options.append({
                        "id": f"12306_{t['train_no']}",
                        "type": "train",
                        "train_number": t["train_no"],
                        "carrier": "中国铁路",
                        "from": origin,
                        "to": destination,
                        "departure_time": t["departure_time"],
                        "arrival_time": t["arrival_time"],
                        "duration": t["duration"],
                        "price": round(t["price_second"]),
                        "price_first": round(t["price_first"]),
                        "price_business": round(t["price_business"]),
                        "seats_second": t["seats_second"],
                        "currency": "CNY",
                        "stops": 0,
                        "source": source_label,
                    })
                print(f"[transport] 12306: {len(trains_12306)} trains "
                      f"({real_price_count} with real prices, "
                      f"{len(trains_12306) - real_price_count} estimated)")
        except Exception as e:
            print(f"[transport] 12306 failed: {e}")

    # ---- Phase 3: Ctrip trains (fallback if 12306 returned nothing) ----
    if (
        wants_train
        and scope == "national"
        and not any(
            str(option.get("source", "")).startswith("12306_live")
            for option in all_options
        )
    ):
        report_progress(trip_input, "12306 无可用结果，正在查询备用列车来源")
        trains, train_err = cached_call(
            "transport-ctrip-trains",
            (origin, destination, dates["start"]),
            lambda: _scrape_ctrip_trains(origin, destination, dates["start"]),
            ttl_seconds=900,
            persist=True,
            source="ctrip_playwright_trains",
        )
        if train_err:
            print(f"[transport] TRAIN ERROR: {train_err}")
            errors.append(train_err)
        if trains:
            print(f"[transport] got {len(trains)} trains, prices: {[t['price'] for t in trains[:3]]}...")
            all_options.extend(trains)

    # ---- Phase 4: Clearly labeled estimate fallback ----
    # Live providers are preferred. If they are unavailable, retain the old safe
    # destination-aware estimate path instead of crashing the entire itinerary.
    if not all_options:
        report_progress(trip_input, "实时来源不可用，正在生成明确标注的估算方案")
        try:
            estimated = get_flight_options(
                origin,
                destination,
                dates,
                trip_input.get("budget", {}),
                transport_types,
                use_ai=False,
            )
            if estimated:
                all_options.extend(estimated)
                errors.append("Live transport providers were unavailable; showing labeled estimates.")
        except Exception as exc:
            errors.append(f"Estimated transport fallback failed: {exc}")

    # ---- Determine source status ----
    if not all_options:
        scrape_status = "failed"
        return {
            "options": [],
            "recommended": {},
            "cost": 0,
            "local_transport_cost": 0,
            "local_transport_options": [],
            "scope": scope,
            "reasoning": "",
            "destination": destination,
            "scrape_status": "failed",
            "errors": errors,
            "verification_required": True,
            "route_points": [],
            "route_summary": {
                "mode": requested_modes[0],
                "origin": origin,
                "destination": destination,
            },
            "coverage": {
                "requested_modes": requested_modes,
                "available_modes": [],
                "note": "No live transportation option was available for the requested route.",
            },
            "error_message": (
                f"Could not find any real transport options for "
                f"{origin} → {destination} on {dates['start']}. "
                f"Errors: {'; '.join(errors)}"
            ),
            "trip_id": trip_id,
        }
    elif all(
        not str(option.get("source", "")).startswith("12306_live")
        and "ctrip" not in str(option.get("source", ""))
        for option in all_options
    ):
        scrape_status = "estimated"
    elif errors:
        scrape_status = "partial"
    else:
        scrape_status = "ok"

    # ---- Phase 5: LLM selects best option ----
    report_progress(trip_input, "正在比较价格、时长和换乘次数")
    result = None
    if len(all_options) > 1:
        try:
            result = llm_reason(TRANSPORT_PROMPT, {
                "origin": origin, "destination": destination, "dates": dates,
                "total_budget": trip_input.get("budget", {}), "preferences": preferences,
                "category_budget_caps": trip_input.get("_budget_caps", {}),
                "transport_types": transport_types, "options": all_options, "scope": scope,
            })
        except Exception as e:
            print(f"[transport] LLM selection failed ({e}), using cheapest option")

    recommended = None
    selection_reasoning = None
    if result and result.get("recommended_id"):
        recommended = next(
            (o for o in all_options if o["id"] == result["recommended_id"]), None
        )
        if recommended is not None:
            selection_reasoning = result.get("reasoning")
    if recommended is None:
        # Preserve the stable behavior: prefer a non-stop option, then price.
        priced = [o for o in all_options if o.get("price", 0) > 0]
        nonstop = [o for o in priced if o.get("stops", 0) == 0]
        pool = nonstop or priced or all_options
        recommended = min(pool, key=lambda o: o.get("price", float("inf")))
        selection_reasoning = (
            "Only available option matched the selected transport mode."
            if len(all_options) == 1
            else "Cheapest suitable option selected (LLM reasoning unavailable)."
        )

    cost = recommended.get("price", 0)

    # ---- Phase 6: Local transport (Gaode/OSRM real routing) ----
    report_progress(trip_input, "正在估算目的地市内交通")
    try:
        from services.gaode_service import get_local_transport as gaode_transport
        local_info = cached_call(
            "transport-local",
            (destination, len(days)),
            lambda: gaode_transport(destination, num_days=len(days)),
            ttl_seconds=1800,
        )
        local = [
            {"mode": m["mode"], "estimated_cost_per_day": m["cost_per_day"],
             "currency": m["currency"], "notes": m["notes"]}
            for m in local_info["modes"]
        ]
        local_total = round(local_info["total_cost_cny"], 2)
        print(f"[transport] local transport ({local_info.get('city_tier', '?')}): "
              f"¥{local_total}/trip via {'Gaode/OSRM' if local_info.get('has_real_routing') else 'tier estimate'}")
    except Exception as e:
        print(f"[transport] Gaode/OSRM failed ({e}), using fallback estimates")
        local = _local_transport_options(destination)
        local_est = sum(l["estimated_cost_per_day"] * 0.3 for l in local)
        local_total = round(local_est * len(days), 2)

    # Planning is read-only. A route recommendation must never trigger a provider
    # browser or create an order without a separate, authenticated user action.
    ttype = recommended.get("type") or recommended.get("mode") or "flight"
    booking_result = {
        "status": "comparison_only",
        "message": (
            "G3TA compared this option but did not place an order. "
            "Verify the current fare and complete purchase with the provider."
        ),
    }

    # ---- Phase 7: Store to database ----
    bref = None
    bstat = "pending"
    try:
        from booking.shared_db import save_transport
        save_transport(
            trip_id=trip_id,
            transport_type=ttype,
            scope=scope,
            from_location=origin,
            to_location=destination,
            departure_time=f"{dates['start']} {recommended.get('departure_time', '08:00')}",
            arrival_time=f"{dates['start']} {recommended.get('arrival_time', '10:00')}",
            carrier=recommended.get("carrier", ""), flight_number=recommended.get("flight_number", ""),
            train_number=recommended.get("train_number", ""), price=cost,
            currency=recommended.get("currency", "CNY"), booking_status=bstat, booking_ref=bref or "")
    except Exception as e:
        print(f"[transport] DB save failed: {e}")

    route_option = {
        **recommended,
        "mode": recommended.get("mode") or recommended.get("type") or "flight",
    }
    route_points, route_summary = _route_metadata(origin, destination, route_option)
    available_modes = list(dict.fromkeys(
        str(option.get("mode") or option.get("type") or "flight").strip().lower()
        for option in all_options
        if str(option.get("mode") or option.get("type") or "flight").strip()
    ))
    unsupported = [mode for mode in requested_modes if mode not in available_modes]

    return {
        "options": all_options,
        "recommended": recommended,
        "cost": cost,
        "local_transport_cost": local_total,
        "local_transport_options": local,
        "scope": scope,
        "reasoning": selection_reasoning,
        "destination": destination,
        "scrape_status": scrape_status,
        "errors": errors,
        "booking_result": booking_result,
        "verification_required": True,
        "route_points": route_points,
        "route_summary": route_summary,
        "coverage": {
            "requested_modes": requested_modes,
            "available_modes": available_modes,
            "note": (
                f"No option is currently available for: {', '.join(unsupported)}. Verify with a live provider."
                if unsupported else None
            ),
        },
        "trip_id": trip_id,
    }
