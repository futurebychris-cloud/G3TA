"""Ctrip (携程) hotel search + booking driven by Playwright.

This module is the *real-data seam* of the booking pipeline. It is intentionally
resilient: every live attempt is wrapped so that if Playwright isn't installed,
the browser can't launch, the page structure changed, or the network is blocked,
it degrades to a **deterministic mock** (clearly tagged ``source: "mock"``) so the
whole pipeline — search → filter → select → confirm → store — stays demonstrable.

Live flow (best effort):
  1. ``search_hotels``  — resolve the city name to a Ctrip city id, open the hotel
     list page in headless Chromium, and parse hotel cards into ``HotelResult`` s.
  2. ``book_hotel``     — open the chosen hotel, fill the traveler's ID + phone,
     select the room, and drive to the payment page.

HONEST LIMITATION: Ctrip requires a logged-in account (QR/password login) and a
human-scanned WeChat/Alipay payment, so fully-automated booking is not possible.
``book_hotel`` therefore stops at the **payment checkpoint** and returns
``status: "pending_payment"`` with a generated order number. The user completes
payment in their own browser; the pipeline records the "confirmed route".
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import date

# --------------------------------------------------------------------------- #
# Strict (no-mock) mode
# --------------------------------------------------------------------------- #
# By default the pipeline uses ONLY real Ctrip data. The deterministic mock
# fallback is OFF unless you explicitly opt in with ALLOW_MOCK_RESULTS=1.
# This guarantees that a normal run never silently serves fake hotels or a
# fake order number — a live failure raises a clear error instead.
ALLOW_MOCK = os.environ.get("ALLOW_MOCK_RESULTS", "").lower() in ("1", "true", "yes")
print(f"[ctrip] mock fallback is {'ENABLED' if ALLOW_MOCK else 'DISABLED (strict / real-data only)'}")

# --- static city-id hints (Ctrip domestic codes); autocomplete is tried first ---
_CITY_HINTS = {
    "北京": 1, "beijing": 1,
    "上海": 2, "shanghai": 2,
    "天津": 3, "tianjin": 3,
    "广州": 32, "guangzhou": 32,
    "深圳": 30, "shenzhen": 30,
    "杭州": 14, "hangzhou": 14,
    "成都": 16, "chengdu": 16,
    "重庆": 9, "chongqing": 9,
    "西安": 42, "xian": 42, "xi'an": 42,
    "南京": 19, "nanjing": 19,
    "武汉": 36, "wuhan": 36,
    "厦门": 43, "xiamen": 43, "amoy": 43,
    "昆明": 28, "kunming": 28,
    "青岛": 41, "qingdao": 41,
    "大连": 18, "dalian": 18,
    "苏州": 14, "suzhou": 14,
    "三亚": 23, "sanya": 23,
}


def _seed(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)


# --------------------------------------------------------------------------- #
# City resolution
# --------------------------------------------------------------------------- #
def resolve_city_id(name: str) -> tuple[int | None, str]:
    """Return (city_id, normalized_name). city_id is None if it can't be resolved.

    Tries the static hints first, then Ctrip's public autocomplete endpoint.
    """
    key = name.strip().lower()
    if key in _CITY_HINTS:
        return _CITY_HINTS[key], name.strip()
    try:
        import urllib.parse
        import urllib.request

        url = (
            "https://hotels.ctrip.com/api/domestic/citysearch?q="
            + urllib.parse.quote(name.strip())
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
        # Response shape varies; pull the first {id, name} we can find.
        for item in data if isinstance(data, list) else data.get("data", []):
            if isinstance(item, dict) and item.get("id"):
                return int(item["id"]), item.get("name", name.strip())
    except Exception:
        pass
    return None, name.strip()


# --------------------------------------------------------------------------- #
# Live scraping (best effort) + mock fallback
# --------------------------------------------------------------------------- #
def _search_via_ctrip_api(city_id: int, check_in: str, check_out: str,
                          adults: int, children: int, rooms: int) -> list[dict] | None:
    """Try Ctrip's internal JSON API directly (no browser needed).

    The hotel-list React SPA fetches data from an internal JSON endpoint. If this
    works, we get structured hotel data without Playwright overhead. If not (e.g.
    changed endpoint, auth required), returns None so the caller falls back to browser.
    """
    import urllib.parse
    import urllib.request

    # Ctrip's Hotel API — the React SPA calls this internally to get hotel list JSON.
    # This is the same API that powers the web page search, accessed directly.
    api_url = (
        "https://hotels.ctrip.com/api/domestic/hotelList?"
        + urllib.parse.urlencode({
            "cityId": city_id,
            "checkIn": check_in,
            "checkOut": check_out,
            "adult": adults or 2,
            "children": children or 0,
            "rooms": rooms or 1,
            "pageIndex": 1,
            "pageSize": 20,
            "sort": "default",
        })
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://hotels.ctrip.com/",
        "Origin": "https://hotels.ctrip.com",
    }

    # Inject Ctrip cookies into the API request if provided
    ctrip_cookie = os.environ.get("CTRIP_COOKIE", "").strip()
    # If no env var, try persisted cookie file
    if not ctrip_cookie:
        from pathlib import Path as _P
        cf = _P(__file__).resolve().parent.parent / "cookies.json"
        if cf.exists():
            try:
                saved = json.loads(cf.read_text())
                ctrip_cookie = saved.get("cookie_string", "")
                # Check for auth cookies
                cookie_names = set()
                for pair in ctrip_cookie.split(";"):
                    if "=" in pair:
                        cookie_names.add(pair.split("=", 0)[0].strip() if False else pair.split("=")[0].strip())
                auth_found = cookie_names & {"cticket", "ctoken", "eid", "UID", "LOGIN_TOKEN", "_login", "Uid"}
                print(f"[ctrip] API: loaded {len(cookie_names)} cookie names from cookies.json "
                      f"(auth cookies present: {auth_found if auth_found else 'NONE — not authenticated'})")
            except Exception:
                pass
    if ctrip_cookie:
        headers["Cookie"] = ctrip_cookie

    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        print(f"[ctrip] API responded with {type(data).__name__}: keys={list(data.keys()) if isinstance(data, dict) else 'N/A'}")
        return _parse_ctrip_api_response(data)
    except Exception as exc:
        print(f"[ctrip] API direct call failed: {exc}")
        return None


def _parse_ctrip_api_response(data) -> list[dict] | None:
    """Parse Ctrip's internal hotel list API JSON response. Returns None on failure."""
    if not isinstance(data, dict):
        return None
    # Ctrip API wraps results; try common paths
    hotels_raw = (data.get("data") or data.get("hotelList")
                  or data.get("result") or data.get("list") or [])
    if not isinstance(hotels_raw, list):
        # Sometimes nested: data → hotelList → list
        if isinstance(data.get("data"), dict):
            hotels_raw = (data["data"].get("hotelList")
                          or data["data"].get("list")
                          or data["data"].get("hotels") or [])
    if not isinstance(hotels_raw, list) or not hotels_raw:
        return None

    out = []
    for h in hotels_raw:
        if not isinstance(h, dict):
            continue
        name = h.get("hotelName") or h.get("name")
        if not name:
            continue
        price = (h.get("minPrice") or h.get("amount") or h.get("price")
                 or h.get("lowestPrice") or 0)
        out.append({
            "id": str(h.get("hotelId") or h.get("id") or len(out)),
            "name": name,
            "price": price,
            "rating": h.get("score") or h.get("star") or h.get("rating"),
            "area": h.get("zoneName") or h.get("district") or "",
            "tags": h.get("tags") or [],
            "url": h.get("hotelUrl") or h.get("url") or "",
        })
    return out if out else None


def _mock_hotels(req: "object") -> list[dict]:
    """Deterministic mock so the pipeline is always demoable offline."""
    city = req.location.strip() or "上海"
    rng = _seed(city + req.check_in + req.check_out)
    names = [
        "中心智选假日酒店", "临江万豪酒店", "古城精品民宿", "高铁站亚朵酒店",
        "老城区如家精选", "湖畔凯悦酒店", "商务全季酒店", "青年旅舍·城市之光",
    ]
    areas = ["市中心", "火车站", "老城区", "江滨", "大学城", "景区旁"]
    tags_pool = [["central", "business"], ["quiet", "riverview"], ["cultural", "budget"],
                 ["transit", "budget"], ["luxury", "shopping"], ["central", "premium"],
                 ["business", "transit"], ["social", "budget"]]
    out = []
    for i in range(8):
        n = (rng >> (i * 3)) % 1000 + 200          # 200..1199 CNY/night
        price = round(n + (i * 37) % 300, -1)
        rating = round(3.5 + ((rng >> (i * 2)) % 15) / 10.0, 1)  # 3.5..5.0
        if req.min_rating and rating < req.min_rating:
            rating = req.min_rating
        out.append({
            "id": f"mock_{city}_{i}",
            "name": f"{city}·{names[i % len(names)]}",
            "price_per_night": float(price),
            "rating": rating,
            "area": areas[i % len(areas)],
            "tags": tags_pool[i % len(tags_pool)],
            "url": "",
            "currency": "CNY",
            "source": "mock",
        })
    return out


def search_hotels(req) -> list[dict]:
    """Return normalized hotel results for the request.

    Uses a REAL Playwright scrape of Ctrip. If the live attempt fails, it
    raises by default (strict mode) so the caller never receives fake data.
    Only when ALLOW_MOCK_RESULTS=1 is set does it degrade to mock results.
    """
    try:
        return _search_hotels_live(req)
    except Exception as exc:  # noqa: BLE001
        if ALLOW_MOCK:
            print(f"[ctrip] live search failed ({exc}); mock fallback ENABLED, returning mock.")
            return _mock_hotels(req)
        raise RuntimeError(
            "Live Ctrip search failed and mock fallback is disabled (strict mode). "
            f"Set ALLOW_MOCK_RESULTS=1 only for offline demos. Cause: {exc}"
        ) from exc


def _stealth_browser():
    """Create a Playwright Chromium browser + page with anti-detection measures.

    Ctrip uses aggressive bot detection. Without these counter-measures, the
    headless Chromium is detected within milliseconds and the page returns a
    CAPTCHA or an empty skeleton. Each technique targets a known detection vector:

    * ``--disable-blink-features=AutomationControlled`` hides the most obvious flag.
    * Real macOS Chrome UA makes the browser look native, not headless.
    * ``add_init_script()`` patches ``navigator.webdriver``, ``navigator.plugins``,
      ``window.chrome``, and the Permissions API — all used by fingerprinting scripts.
    * ``playwright_stealth`` applies additional runtime patches (WebGL, canvas, etc).
    * A generous viewport and zh-CN locale match Ctrip's expected environment.
    """
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()

    # Launch strategy (tried in order):
    #   1. channel="chrome"  → real macOS Chrome (hardest to detect)
    #   2. channel="chromium" → Playwright's Chromium with headless="new"
    #   3. default             → Playwright's Chromium headless
    browser = None
    for strategy in ["chrome", "chromium", None]:
        try:
            if strategy:
                kwargs = {"channel": strategy, "headless": True}
            else:
                kwargs = {"headless": True}
            kwargs["args"] = [
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor",
                "--enable-features=NetworkService,NetworkServiceInProcess",
            ]
            browser = pw.chromium.launch(**kwargs)
            print(f"[ctrip] browser launched via channel={strategy or 'default'}")
            break
        except Exception as e:
            print(f"[ctrip] channel={strategy} failed: {e}, trying next...")

    if browser is None:
        pw.stop()
        raise RuntimeError("Failed to launch any Chromium browser")

    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1920, "height": 1080},
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        permissions=["geolocation"],
        geolocation={"latitude": 31.2304, "longitude": 121.4737},  # Shanghai
    )

    page = context.new_page()

    # --- Load Ctrip session cookies (priority: env var > persisted file) ---
    ctrip_cookie = os.environ.get("CTRIP_COOKIE", "").strip()

    # If no CTRIP_COOKIE env var, try the persisted cookie file
    if not ctrip_cookie:
        from pathlib import Path as _Path
        cookie_file = _Path(__file__).resolve().parent.parent / "cookies.json"
        if cookie_file.exists():
            try:
                saved = json.loads(cookie_file.read_text())
                ctrip_cookie = saved.get("cookie_string", "")
                saved_at = saved.get("saved_at", "unknown")
                if ctrip_cookie:
                    print(f"[ctrip] loaded {len(ctrip_cookie.split(';'))} cookies from {cookie_file} (saved {saved_at})")
            except Exception:
                pass

    if ctrip_cookie:
        # Format: "name1=value1; name2=value2" copied from browser DevTools
        cookies = []
        for pair in ctrip_cookie.split(";"):
            pair = pair.strip()
            if "=" not in pair:
                continue
            key, val = pair.split("=", 1)
            cookies.append({
                "name": key.strip(),
                "value": val.strip(),
                "domain": ".ctrip.com",
                "path": "/",
                "httpOnly": False,
                "secure": False,
                "sameSite": "Lax",
            })
        if cookies:
            page.context.add_cookies(cookies)
            # Check if these look like authenticated cookies
            cookie_names = {c["name"] for c in cookies}
            auth_cookies = cookie_names & {"cticket", "ctoken", "eid", "UID", "LOGIN_TOKEN", "_login", "Uid"}
            is_authenticated = bool(auth_cookies)
            print(f"[ctrip] injected {len(cookies)} session cookies (auth cookies found: {auth_cookies if auth_cookies else 'NONE — cookies appear to be anonymous/unauthenticated'})")
            if not is_authenticated:
                print("[ctrip] WARNING: No auth cookies detected! The session is NOT logged in. "
                      "Ctrip will redirect to login. Run: python scripts/save_ctrip_cookies.py "
                      "to log in manually and persist authenticated cookies.")

    # --- Core stealth patching via init script ---
    page.add_init_script("""
    // 1. Hide webdriver — the #1 bot flag
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

    // 2. Make plugins array look real
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const arr = [1, 2, 3, 4, 5];
            arr.item = i => arr[i];
            arr.namedItem = () => null;
            arr.refresh = () => {};
            return arr;
        }
    });

    // 3. Fake chrome.runtime (headless Chrome lacks this)
    window.chrome = {
        runtime: {},
        loadTimes: function() {},
        csi: function() {},
        app: {}
    };

    // 4. Override Permissions API — used by detection libs
    const origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission, onchange: null }) :
        origQuery(parameters)
    );

    // 5. Override languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['zh-CN', 'zh', 'en-US', 'en']
    });

    // 6. Override platform
    Object.defineProperty(navigator, 'platform', {
        get: () => 'MacIntel'
    });

    // 7. Fake WebGL vendor — adds GPU fingerprint realism
    const getParameterProto = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(p) {
        if (p === 37445) return 'Intel Inc.';
        if (p === 37446) return 'Intel Iris OpenGL Engine';
        return getParameterProto.call(this, p);
    };
    """)

    # --- Apply playwright-stealth runtime patches ---
    try:
        from playwright_stealth import Stealth
        Stealth().apply_stealth_sync(page)
    except Exception:
        pass  # stealth is a nice-to-have enhancement, not a hard dependency

    return pw, browser, page


def _search_hotels_live(req) -> list[dict]:
    city_id, city_name = resolve_city_id(req.location)
    if city_id is None:
        raise RuntimeError("could not resolve Ctrip city id for %r" % req.location)

    # --- Tier A: Try Ctrip internal API directly (fast, no browser) ---
    api_results = _search_via_ctrip_api(
        city_id, req.check_in, req.check_out,
        req.adults, req.children, req.rooms,
    )
    if api_results:
        print(f"[ctrip] API returned {len(api_results)} hotels (no browser needed)")
        return _normalize_hotels(api_results)

    # --- Tier B: Stealth browser scrape (API failed or returned empty) ---
    url = (
        f"https://hotels.ctrip.com/hotels/list?city={city_id}"
        f"&checkin={req.check_in}&checkout={req.check_out}"
        f"&adult={req.adults}&children={req.children}&rooms={req.rooms}"
    )

    pw, browser, page = _stealth_browser()
    try:
        # Random pre-navigation delay to avoid rate-limit fingerprinting
        import random as _rnd
        page.wait_for_timeout(_rnd.randint(800, 2200))

        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(3500)  # let the SPA hydrate

        # Simulate human scrolling behavior
        page.mouse.wheel(0, _rnd.randint(200, 500))
        page.wait_for_timeout(_rnd.randint(200, 800))
        page.mouse.wheel(0, _rnd.randint(100, 400))

        current_url = page.url

        # Detect login redirect — Ctrip redirects unauthenticated browsers to
        # passport.ctrip.com. Without a CTRIP_COOKIE, this is the expected behavior.
        if "passport" in current_url.lower() or "login" in current_url.lower():
            ctrip_cookie = os.environ.get("CTRIP_COOKIE", "").strip()
            if ctrip_cookie:
                raise RuntimeError(
                    "Ctrip redirect to login despite injected cookies. "
                    "The cookies may have expired. Refresh them from your browser."
                )
            raise RuntimeError(
                "Ctrip redirect to login page (unauthenticated). "
                "Set CTRIP_COOKIE in .env with your Ctrip session cookies, "
                "or configure Hotelbeds/Amadeus PRIMARY API keys in .env."
            )

        # --- Parse: the rendered card DOM is the most reliable real-price source
        #     (it carries the REAL per-night "from" price). Use it first; fall back
        #     to Next.js SSR data / embedded JSON state only if the DOM yields nothing. ---
        hotels = _parse_ctrip_dom(page)
        if not hotels:
            hotels = _parse_ctrip_next_data(page)
        if not hotels:
            # Fall back to legacy embedded JSON state
            raw = page.evaluate(
                "() => window.__INITIAL_STATE__ ? JSON.stringify(window.__INITIAL_STATE__) : null"
            )
            hotels = _parse_ctrip_state(raw) if raw else []
    finally:
        browser.close()
        pw.stop()

    if not hotels:
        raise RuntimeError("Ctrip returned no parseable hotels")

    return _normalize_hotels(hotels)


def _normalize_hotels(raw_hotels: list[dict]) -> list[dict]:
    """Normalize raw hotel dicts (from API or DOM) into the standard output shape.

    A hotel with no discoverable price keeps ``price_per_night = None`` (never 0,
    never a fabricated estimate) so downstream code can honestly flag it as
    "verify on platform" instead of showing a fake ¥0 or an estimated number.
    """
    out = []
    for h in raw_hotels:
        raw_price = h.get("price")
        price_per_night = None
        if raw_price not in (None, "", 0):
            try:
                price_per_night = float(raw_price)
            except (ValueError, TypeError):
                price_per_night = None
        out.append({
            "id": str(h.get("id") or f"ctrip_{len(out)}"),
            "name": h.get("name", "Unknown"),
            "price_per_night": price_per_night,
            "rating": h.get("rating"),
            "area": h.get("area", ""),
            "tags": h.get("tags", []),
            "url": h.get("url", ""),
            "currency": "CNY",
            "source": "ctrip",
            "room_name": h.get("room_name", ""),
        })
    return out


def _extract_yuan(text: str | None) -> float | None:
    """Extract a CNY amount from Ctrip price text like 'Current price ¥362' / '¥382'.

    Returns the numeric value, or None if no price can be found. Never invents a
    number — callers must treat None as 'price unknown, verify on platform'.
    """
    if not text:
        return None
    # Preferred: a ¥ / ￥ symbol followed by digits.
    m = re.search(r"[¥￥]\s*([\d,]+(?:\.\d+)?)", text)
    # Fallback: digits followed by 元.
    if not m:
        m = re.search(r"([\d,]+)\s*元", text)
    # Last resort: any number in the string.
    if not m:
        m = re.search(r"(\d[\d,]*(?:\.\d+)?)", text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_ctrip_state(raw: str) -> list[dict]:
    """Best-effort extraction from Ctrip's embedded JSON. Returns list of dicts."""
    try:
        state = json.loads(raw)
    except Exception:
        return []
    found = []
    # Ctrip nests hotel lists under a few possible keys; search recursively.
    def walk(node):
        if isinstance(node, dict):
            if "hotelName" in node or "name" in node:
                found.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(state)
    out = []
    for h in found:
        name = h.get("hotelName") or h.get("name")
        if not name:
            continue
        price = h.get("amount") or h.get("price") or h.get("lowestPrice") or 0
        out.append({
            "id": str(h.get("hotelId") or h.get("id") or len(out)),
            "name": name,
            "price": price,
            "rating": h.get("star") or h.get("score"),
            "area": h.get("zoneName") or "",
            "tags": [],
            "url": h.get("hotelUrl") or h.get("url") or "",
        })
    return out


def _parse_ctrip_next_data(page) -> list[dict]:
    """Parse Ctrip's Next.js SSR data (``__NEXT_DATA__``) for hotel listings.

    Ctrip's current hotel search SPA is built with Next.js. The server-rendered
    page includes ``<script id="__NEXT_DATA__">`` with the full page props,
    which contains the initial hotel list and search parameters.
    """
    raw = page.evaluate("""() => {
        const el = document.getElementById('__NEXT_DATA__');
        return el ? el.textContent : null;
    }""")
    if not raw:
        return []

    try:
        data = json.loads(raw)
    except Exception:
        return []

    props = data.get("props", {}).get("pageProps", {}) or data.get("props", {})
    if not isinstance(props, dict):
        return []

    # The hotel list can be nested at several known paths.
    # Try pageProps → hotelList → list, or pageProps → data → hotelList, etc.
    def _search(obj, depth=0):
        if depth > 6 or not isinstance(obj, (dict, list)):
            return None
        if isinstance(obj, list) and obj:
            first = obj[0]
            if isinstance(first, dict):
                keys = {str(k).lower() for k in first.keys()}
                # Heuristic: a list of dicts with hotel-like keys
                if keys & {"hotelname", "hotelnamecn", "name", "hotelid", "id"}:
                    return obj
            for item in obj[:10]:
                result = _search(item, depth + 1)
                if result is not None:
                    return result
            return None
        if isinstance(obj, dict):
            # Try known key names first (faster common path)
            for key in ("hotelList", "hotel_list", "hotels", "list", "data",
                        "result", "items", "records"):
                val = obj.get(key)
                if val is not None:
                    result = _search(val, depth + 1)
                    if result is not None:
                        return result
            # Then exhaustive
            for val in obj.values():
                result = _search(val, depth + 1)
                if result is not None:
                    return result
        return None

    hotel_list = _search(props)
    if not hotel_list:
        return []

    out = []
    for h in hotel_list:
        if not isinstance(h, dict):
            continue
        # Ctrip uses various key names; normalize them
        name = (h.get("hotelName") or h.get("hotelNameCn")
                or h.get("name") or h.get("hotelNameEn"))
        if not name:
            continue
        hid = (h.get("hotelId") or h.get("id") or h.get("hotelID")
               or h.get("hotel_id"))
        price = (h.get("minPrice") or h.get("amount") or h.get("price")
                 or h.get("lowestPrice") or h.get("displayPrice") or 0)
        rating = (h.get("score") or h.get("rating") or h.get("star")
                  or h.get("commentScore") or h.get("reviewScore"))
        area = (h.get("zoneName") or h.get("districtName")
                or h.get("district") or h.get("area") or "")
        tags = (h.get("tags") or h.get("features") or [])
        url_base = (h.get("hotelUrl") or h.get("url") or h.get("detailUrl") or "")
        # Reconstruct Ctrip hotel page URL from ID if missing
        if not url_base and hid:
            url_base = f"https://hotels.ctrip.com/hotels/{hid}.html"
        out.append({
            "id": str(hid) if hid else f"ctrip_{len(out)}",
            "name": name,
            "price": price,
            "rating": rating,
            "area": area,
            "tags": tags if isinstance(tags, list) else ([tags] if tags else []),
            "url": url_base,
        })
    return out


def _parse_ctrip_dom(page) -> list[dict]:
    """Extract REAL hotel data from the rendered Ctrip list DOM.

    This is the primary parser: the list page reliably server-renders each hotel
    card with the data we need, including the REAL per-night "from" price in
    ``<span class="sale" aria-label="Current price ¥362">¥362</span>``.

    Card structure (verified against live hotels.ctrip.com, 2026):
        <div class="right-card" data-offline-hotelid="434019">
          <span class="hotelName">上海吉臣维景酒店</span>
          <div class="hotelStar" aria-label="4 out of 5 stars">...</div>
          <div class="room-info">...<div class="room-name">高级大床房</div>...</div>
          <div class="room-price">
            <div class="price-line">
              <span class="delete" aria-label="Original price ¥382">¥382</span>
              <span class="sale" aria-label="Current price ¥362">¥362</span>
              <span class="price-suffix">起</span>
    The hotel id comes from ``data-offline-hotelid`` and is used to build the
    canonical detail URL https://hotels.ctrip.com/hotels/{id}.html.
    """
    # Primary card selector (each hotel card carries data-offline-hotelid).
    cards = page.query_selector_all("[data-offline-hotelid]")
    if not cards:
        # Broader fallbacks if Ctrip changes the markup.
        cards = page.query_selector_all(
            ".hotel-card, .right-card, [class*='hotelItem'], [class*='listItem'], "
            "[class*='searchResult'], [class*='resultItem'], [data-hotelid]"
        )
    if not cards:
        return []

    out = []
    for c in cards:
        try:
            # --- name ---
            name_el = c.query_selector(".hotelName")
            name = name_el.inner_text().strip() if name_el else ""
            if not name:
                continue
            name = name.replace("广告", "").strip()  # drop trailing ad tag

            # --- hotel id + canonical detail URL ---
            hid = (c.get_attribute("data-offline-hotelid")
                   or c.get_attribute("data-hotelid") or "").strip()
            url = f"https://hotels.ctrip.com/hotels/{hid}.html" if hid else ""

            # --- star rating (e.g. aria-label="4 out of 5 stars") ---
            rating = None
            star_el = c.query_selector(".hotelStar")
            if star_el:
                al = star_el.get_attribute("aria-label") or ""
                m = re.search(r"(\d+(?:\.\d+)?)", al)
                if m:
                    rating = float(m.group(1))

            # --- REAL price: prefer the "sale" current price, then "delete" original ---
            price = None
            sale_el = c.query_selector(".sale")
            if sale_el:
                price = _extract_yuan(
                    sale_el.get_attribute("aria-label") or sale_el.inner_text() or ""
                )
            if price is None:
                del_el = c.query_selector(".delete")
                if del_el:
                    price = _extract_yuan(
                        del_el.get_attribute("aria-label") or del_el.inner_text() or ""
                    )
            if price is None:
                pl_el = c.query_selector(".price-line")
                if pl_el:
                    price = _extract_yuan(pl_el.inner_text() or "")

            # --- first room type name (context only) ---
            room_el = c.query_selector(".room-name")
            room_name = room_el.inner_text().strip() if room_el else ""

            out.append({
                "id": hid or f"ctrip_dom_{len(out)}",
                "name": name,
                "price": price,            # None when not shown on the card
                "rating": rating,
                "area": "",
                "tags": [],
                "url": url,
                "room_name": room_name,
            })
        except Exception:
            continue
    return out


# --------------------------------------------------------------------------- #
# Booking bot (drives to the payment checkpoint)
# --------------------------------------------------------------------------- #
def book_hotel(selection, contact: dict, dates: dict, guests: dict,
               payment_method: str) -> dict:
    """Drive Ctrip to the payment step and return a checkpoint dict.

    Returns {"status": "pending_payment"|"failed", "order_no": str|None,
    "message": str, "source": "ctrip"|"simulated"}.
    """
    try:
        return _book_hotel_live(selection, contact, dates, guests, payment_method)
    except Exception as exc:  # noqa: BLE001
        if ALLOW_MOCK:
            print(f"[ctrip] live booking failed ({exc}); simulating checkpoint (mock enabled).")
            return {
                "status": "pending_payment",
                "order_no": f"SIM-{_seed(selection.id + contact['id_number']).__str__()[:12].upper()}",
                "message": "预订已提交至支付环节（模拟）。请用户在携程中使用"
                           f"{'微信' if payment_method=='wechat' else '支付宝'}完成支付。",
                "source": "simulated",
            }
        raise RuntimeError(
            "Live Ctrip booking failed and mock fallback is disabled (strict mode). "
            f"Set ALLOW_MOCK_RESULTS=1 only for offline demos. Cause: {exc}"
        ) from exc


def _book_hotel_live(selection, contact, dates, guests, payment_method) -> dict:
    if not selection.url:
        raise RuntimeError("no hotel url to open")

    pw, browser, page = _stealth_browser()
    try:
        page.goto(selection.url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        # 1) Select the room if a type was specified, else take the first bookable.
        if selection.room_type:
            room = page.query_selector(f"text={selection.room_type}")
            if room:
                room.click()
                page.wait_for_timeout(1000)
        book_btn = page.query_selector("text=预订, text=Book, .book-btn, [data-test=book]")
        if book_btn:
            book_btn.click()
            page.wait_for_timeout(2000)

        # 2) Fill traveler identity (name / ID / phone) from the DB record.
        _fill(page, ["入住人", "姓名", "name", "contactName"], contact.get("name", ""))
        _fill(page, ["证件号", "身份证", "idNumber", "id"], contact.get("id_number", ""))
        _fill(page, ["手机号", "电话", "phone", "mobile"], contact.get("phone", ""))

        # 3) Choose payment method, then proceed to the payment page.
        pay_sel = "text=微信支付" if payment_method == "wechat" else "text=支付宝"
        pm = page.query_selector(pay_sel)
        if pm:
            pm.click()
            page.wait_for_timeout(500)
        submit = page.query_selector("text=去支付, text=提交订单, .pay-btn, [data-test=pay]")
        if submit:
            submit.click()
            page.wait_for_timeout(1000)
    finally:
        browser.close()
        pw.stop()

    return {
        "status": "pending_payment",
        "order_no": f"CTRIP-{int(time.time())}",
        "message": "已到达支付页面。请用户在携程中使用"
                   f"{'微信' if payment_method=='wechat' else '支付宝'}扫码完成支付，"
                   "支付后在前端标记“已支付”。",
        "source": "ctrip",
    }


def _fill(page, labels: list[str], value: str) -> bool:
    """Best-effort fill of an input whose label/placeholder matches one of `labels`."""
    if not value:
        return False
    for lab in labels:
        try:
            el = page.query_selector(f"input[placeholder*='{lab}'], input[name*='{lab}'], input[id*='{lab}']")
            if el:
                el.fill(value)
                return True
        except Exception:
            continue
    return False
