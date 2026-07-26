"""Ctrip (携程) hotel detail scraper — extracts images, description, lat/lng,
room types, amenities, and cost breakdown from individual hotel pages.

Reuses the stealth browser setup from ``ctrip.py`` to avoid bot detection.
Each scrape opens the hotel detail URL, waits for the SPA to hydrate, and
parses the embedded ``__NEXT_DATA__`` blob (most reliable) before falling
back to DOM selectors.

Usage::

    from booking.ctrip_detail import scrape_hotel_detail
    detail = scrape_hotel_detail("https://hotels.ctrip.com/hotels/12345.html")
"""
from __future__ import annotations

import json
import re
import random as _rnd
from typing import Any

from security import validate_ctrip_hotel_url


def _stealth_browser_for_detail():
    """Create a Playwright stealth browser — identical to ctrip._stealth_browser().

    This is intentionally duplicated (not imported) so the detail scraper
    is a self-contained module that can be used independently.
    """
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()

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
            print(f"[ctrip_detail] browser launched via channel={strategy or 'default'}")
            break
        except Exception as e:
            print(f"[ctrip_detail] channel={strategy} failed: {e}, trying next...")

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
        geolocation={"latitude": 31.2304, "longitude": 121.4737},
    )

    page = context.new_page()

    # --- Cookie loading (same logic as ctrip.py) ---
    from .ctrip import _load_ctrip_cookie_string
    ctrip_cookie = _load_ctrip_cookie_string()

    if ctrip_cookie:
        cookies = []
        for pair in ctrip_cookie.split(";"):
            pair = pair.strip()
            if "=" not in pair:
                continue
            key, val = pair.split("=", 1)
            cookies.append({
                "name": key.strip(), "value": val.strip(),
                "domain": ".ctrip.com", "path": "/",
                "httpOnly": False, "secure": False, "sameSite": "Lax",
            })
        if cookies:
            page.context.add_cookies(cookies)

    # --- Stealth init script ---
    page.add_init_script("""
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const arr = [1,2,3,4,5];
            arr.item = i => arr[i];
            arr.namedItem = () => null;
            arr.refresh = () => {};
            return arr;
        }
    });
    window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
    const origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission, onchange: null }) :
        origQuery(parameters)
    );
    Object.defineProperty(navigator, 'languages', {
        get: () => ['zh-CN', 'zh', 'en-US', 'en']
    });
    Object.defineProperty(navigator, 'platform', {
        get: () => 'MacIntel'
    });
    const getParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(p) {
        if (p === 37445) return 'Intel Inc.';
        if (p === 37446) return 'Intel Iris OpenGL Engine';
        return getParam.call(this, p);
    };
    """)

    try:
        from playwright_stealth import Stealth
        Stealth().apply_stealth_sync(page)
    except Exception:
        pass

    return pw, browser, page


def scrape_hotel_detail(
    hotel_url: str,
    check_in: str | None = None,
    check_out: str | None = None,
    nights: int = 1,
) -> dict[str, Any]:
    """Scrape detailed hotel info from a Ctrip hotel detail page.

    Args:
        hotel_url: Full Ctrip hotel detail URL (e.g. https://hotels.ctrip.com/hotels/12345.html)
        check_in: Check-in date YYYY-MM-DD (optional, for room price accuracy)
        check_out: Check-out date YYYY-MM-DD (optional)
        nights: Number of nights (default 1, for total cost calculation)

    Returns a dict with fields:
        images: list[str]        — image URLs for hotel gallery
        description: str         — brief hotel introduction
        star_rating: float|None  — star rating (e.g. 4.5)
        lat: float|None          — latitude
        lng: float|None          — longitude
        labels: list[str]        — amenity/label tags (bathtub, breakfast, wifi, ...)
        rooms: list[dict]        — [{name, price_per_night, bed_type, includes}]
        total_cost: float|None   — calculated: lowest room price * nights - discount
        discount: float|None     — discount amount if available

    If any field cannot be extracted, it is returned as None / empty list.
    """
    result: dict[str, Any] = {
        "images": [],
        "description": "",
        "star_rating": None,
        "lat": None,
        "lng": None,
        "labels": [],
        "rooms": [],
        "total_cost": None,
        "discount": None,
    }

    if not hotel_url:
        return result
    hotel_url = validate_ctrip_hotel_url(hotel_url)

    # If dates are provided, append them to the URL so the page loads with pricing
    url = hotel_url
    if check_in and check_out:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}checkin={check_in}&checkout={check_out}"

    pw, browser, page = _stealth_browser_for_detail()
    try:
        page.wait_for_timeout(_rnd.randint(800, 2200))
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)  # allow React SPA hydration

        # Simulate human scroll
        for _ in range(3):
            page.mouse.wheel(0, _rnd.randint(200, 600))
            page.wait_for_timeout(_rnd.randint(300, 900))

        current_url = page.url

        # --- Login redirect check ---
        if "passport" in current_url.lower() or "login" in current_url.lower():
            print(f"[ctrip_detail] login redirect detected for {hotel_url}")
            # Return whatever we can — likely empty
            return result

        # --- Primary: parse __NEXT_DATA__ ---
        next_data = _extract_next_data(page)
        if next_data:
            result = _merge_detail(result, _parse_detail_from_next_data(next_data))

        # --- Fallback: DOM scraping for missing fields ---
        if not result["images"]:
            result["images"] = _scrape_images_from_dom(page)
        if not result["description"]:
            result["description"] = _scrape_description_from_dom(page)
        if not result["labels"]:
            result["labels"] = _scrape_labels_from_dom(page)
        if not result["rooms"]:
            result["rooms"] = _scrape_rooms_from_dom(page)
        if result["lat"] is None or result["lng"] is None:
            lat_lng = _scrape_lat_lng_from_dom(page)
            if lat_lng:
                result["lat"], result["lng"] = lat_lng

        # --- Calculate total cost ---
        if result["rooms"] and nights > 0:
            cheapest = min(
                (r.get("price_per_night", 0) or 0 for r in result["rooms"]),
                default=0,
            )
            if cheapest > 0:
                result["total_cost"] = cheapest * nights - (result.get("discount") or 0)

    except Exception as exc:
        print(f"[ctrip_detail] scrape error for {hotel_url}: {exc}")
    finally:
        browser.close()
        pw.stop()

    return result


# --------------------------------------------------------------------------- #
# Extraction from __NEXT_DATA__
# --------------------------------------------------------------------------- #

def _extract_next_data(page) -> dict | None:
    raw = page.evaluate("""() => {
        const el = document.getElementById('__NEXT_DATA__');
        return el ? el.textContent : null;
    }""")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _parse_detail_from_next_data(data: dict) -> dict[str, Any]:
    """Extract hotel detail fields from Ctrip's __NEXT_DATA__ JSON."""
    result: dict[str, Any] = {}

    props = data.get("props", {}).get("pageProps", {}) or data.get("props", {})

    def deep_get(obj, *keys):
        """Recursively search for keys in a nested dict/list."""
        if isinstance(obj, dict):
            for k in keys:
                if k in obj:
                    return obj[k]
            for v in obj.values():
                res = deep_get(v, *keys)
                if res is not None:
                    return res
        elif isinstance(obj, list):
            for item in obj:
                res = deep_get(item, *keys)
                if res is not None:
                    return res
        return None

    # --- Hotel Info ---
    hotel_info = deep_get(props, "hotelInfo", "hotelDetail", "hotel_info", "hotel") or {}
    if isinstance(hotel_info, list) and hotel_info:
        hotel_info = hotel_info[0]

    # Star rating
    star = None
    star_val = (
        hotel_info.get("starRating") or hotel_info.get("star")
        or hotel_info.get("hotelStar") or hotel_info.get("starLevel")
        or deep_get(props, "starRating", "hotelStar", "star")
    )
    if star_val is not None:
        try:
            star = float(star_val)
        except (ValueError, TypeError):
            pass
    if star:
        result["star_rating"] = star

    # Description
    desc = (
        hotel_info.get("description") or hotel_info.get("intro")
        or hotel_info.get("introduction") or hotel_info.get("summary")
        or deep_get(props, "description", "introduction", "intro")
    )
    if desc and isinstance(desc, str):
        result["description"] = desc.strip()

    # --- Coordinates ---
    lat = (
        hotel_info.get("latitude") or hotel_info.get("lat")
        or deep_get(props, "latitude", "lat", "mapInfo")
    )
    lng = (
        hotel_info.get("longitude") or hotel_info.get("lng") or hotel_info.get("lon")
        or deep_get(props, "longitude", "lng", "lon", "mapInfo")
    )
    # Check if mapInfo is a dict with lat/lng
    if not lat:
        map_info = deep_get(props, "mapInfo")
        if isinstance(map_info, dict):
            lat = map_info.get("latitude") or map_info.get("lat")
            lng = lng or map_info.get("longitude") or map_info.get("lng") or map_info.get("lon")
    try:
        if lat is not None and lng is not None:
            result["lat"] = float(lat)
            result["lng"] = float(lng)
    except (ValueError, TypeError):
        pass

    # --- Images ---
    images = []
    img_list = (
        hotel_info.get("images") or hotel_info.get("photos")
        or hotel_info.get("imageList") or hotel_info.get("picList")
        or deep_get(props, "images", "photos", "imageList", "picList")
    )
    if img_list:
        if isinstance(img_list, list):
            for img in img_list:
                url = _extract_image_url(img)
                if url:
                    images.append(url)
        elif isinstance(img_list, str):
            images.append(img_list)
    result["images"] = images

    # --- Labels / Amenities ---
    labels = []
    facilities = (
        hotel_info.get("facilities") or hotel_info.get("facilityList")
        or hotel_info.get("amenities") or hotel_info.get("serviceTags")
        or deep_get(props, "facilities", "facilityList", "amenities")
    )
    if facilities:
        if isinstance(facilities, list):
            for f in facilities:
                label = _extract_label(f)
                if label:
                    labels.append(label)
        elif isinstance(facilities, str):
            labels.append(facilities)
    # Also check tags
    tags = (
        hotel_info.get("tags") or hotel_info.get("hotelTags")
        or deep_get(props, "tags", "hotelTags")
    )
    if isinstance(tags, list):
        for t in tags:
            if isinstance(t, str):
                labels.append(t)
            elif isinstance(t, dict):
                label = t.get("name") or t.get("tagName") or t.get("label")
                if label:
                    labels.append(str(label))
    result["labels"] = list(dict.fromkeys(labels))  # dedupe

    # --- Rooms ---
    rooms = []
    room_list = (
        hotel_info.get("rooms") or hotel_info.get("roomList")
        or hotel_info.get("roomTypeList") or deep_get(props, "rooms", "roomList", "roomTypeList")
    )
    if isinstance(room_list, list):
        for r in room_list:
            if not isinstance(r, dict):
                continue
            room_entry = {
                "name": (r.get("roomName") or r.get("name") or r.get("roomTypeName") or ""),
                "price_per_night": _parse_price(r),
                "bed_type": (r.get("bedType") or r.get("bed") or ""),
                "includes": (r.get("includes") or r.get("breakfast") or ""),
                "cancellation": (r.get("cancelPolicy") or r.get("cancelRule") or ""),
            }
            if room_entry["name"]:
                rooms.append(room_entry)
    result["rooms"] = rooms

    # --- Discount ---
    discount_val = (
        hotel_info.get("discount") or hotel_info.get("coupon")
        or deep_get(props, "discount", "coupon", "promotionPrice")
    )
    try:
        if discount_val is not None:
            result["discount"] = float(discount_val)
    except (ValueError, TypeError):
        pass

    return result


def _extract_image_url(img) -> str | None:
    """Extract a full image URL from various Ctrip image data formats."""
    if isinstance(img, str):
        if img.startswith("http"):
            return img
        if img.startswith("//"):
            return f"https:{img}"
        return f"https://{img}" if img else None
    if isinstance(img, dict):
        url = img.get("url") or img.get("src") or img.get("imageUrl") or img.get("big")
        if url:
            return _extract_image_url(url)
    return None


def _extract_label(facility) -> str | None:
    """Extract a human-readable label from a facility dict or string."""
    if isinstance(facility, str):
        return facility
    if isinstance(facility, dict):
        return (facility.get("name") or facility.get("facilityName")
                or facility.get("label") or facility.get("title")
                or str(facility.get("id", "")))
    return None


def _parse_price(room: dict) -> float | None:
    """Parse price from a room dict, handling various Ctrip key names."""
    price = (room.get("price") or room.get("amount") or room.get("salePrice")
             or room.get("lowestPrice") or room.get("displayPrice")
             or room.get("roomPrice") or room.get("avgPrice"))
    if price is not None:
        try:
            return round(float(price))
        except (ValueError, TypeError):
            pass
    return None


# --------------------------------------------------------------------------- #
# DOM fallback scrapers
# --------------------------------------------------------------------------- #

def _scrape_images_from_dom(page) -> list[str]:
    """Scrape hotel images from the DOM when __NEXT_DATA__ is unavailable."""
    images = []
    try:
        # Ctrip detail pages often use a carousel/slider with img tags
        selectors = [
            ".hotel-detail-img img", "[class*='banner'] img",
            "[class*='gallery'] img", "[class*='carousel'] img",
            "[class*='hero'] img", ".pic-wrap img",
            "img[src*='dimg']", "img[src*='hotelpic']",
        ]
        for sel in selectors:
            imgs = page.query_selector_all(sel)
            for img in imgs:
                src = img.get_attribute("src") or img.get_attribute("data-src") or ""
                if src and src.startswith("http") and "ctrip" not in src.lower().split("logo"):
                    images.append(src)
            if images:
                break
    except Exception:
        pass
    return list(dict.fromkeys(images))  # dedupe, keep order


def _scrape_description_from_dom(page) -> str:
    """Scrape hotel description/intro from DOM."""
    selectors = [
        "[class*='hotelIntro']", "[class*='hotel-intro']",
        "[class*='description']", "[class*='summary']",
        ".hotel-desc", ".intro-text", "[data-test='hotel-desc']",
    ]
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if len(text) > 20:
                    return text
        except Exception:
            continue
    return ""


def _scrape_labels_from_dom(page) -> list[str]:
    """Scrape amenity/service labels from DOM."""
    labels = []
    selectors = [
        "[class*='facility'] span", "[class*='amenity'] span",
        "[class*='serviceTag']", "[class*='tagList'] span",
        ".hotel-tags .tag",
    ]
    for sel in selectors:
        try:
            els = page.query_selector_all(sel)
            for el in els:
                text = el.inner_text().strip()
                if text and len(text) < 30:
                    labels.append(text)
        except Exception:
            continue
    return list(dict.fromkeys(labels))


def _scrape_rooms_from_dom(page) -> list[dict]:
    """Scrape room types and prices from DOM."""
    rooms = []
    # Look for room list containers
    room_sels = [
        "[class*='roomItem']", "[class*='room-item']",
        "[class*='roomCard']", "tr[class*='room']",
        "[data-test='room-item']", "li[class*='room']",
    ]
    cards = []
    for sel in room_sels:
        cards = page.query_selector_all(sel)
        if cards:
            break

    for card in cards:
        try:
            name = ""
            for ns in (".room-name", "[class*='roomName']", "h4", "h5", "strong"):
                nel = card.query_selector(ns)
                if nel:
                    name = nel.inner_text().strip()
                    break

            price = None
            for ps in (".price", "[class*='price']", "[class*='Price']"):
                pel = card.query_selector(ps)
                if pel:
                    price_text = pel.inner_text()
                    digits = "".join(filter(lambda c: c.isdigit() or c == ".", price_text))
                    if digits:
                        try:
                            price = round(float(digits))
                        except ValueError:
                            pass
                    break

            if name:
                rooms.append({
                    "name": name,
                    "price_per_night": price,
                    "bed_type": "",
                    "includes": "",
                    "cancellation": "",
                })
        except Exception:
            continue
    return rooms


def _scrape_lat_lng_from_dom(page) -> tuple[float, float] | None:
    """Scrape lat/lng from the page DOM (e.g. data attributes, map pins)."""
    try:
        # Check for data attributes on map containers
        lat = page.evaluate("""() => {
            const el = document.querySelector('[data-lat], [data-latitude], [lat]');
            if (el) return el.getAttribute('data-lat') || el.getAttribute('data-latitude') || el.getAttribute('lat');
            return null;
        }""")
        lng = page.evaluate("""() => {
            const el = document.querySelector('[data-lng], [data-lon], [data-longitude], [lng], [lon]');
            if (el) return el.getAttribute('data-lng') || el.getAttribute('data-lon') || el.getAttribute('data-longitude') || el.getAttribute('lng') || el.getAttribute('lon');
            return null;
        }""")
        if lat and lng:
            return float(lat), float(lng)
    except Exception:
        pass

    # Check for coordinates embedded in the page HTML
    try:
        html = page.content()
        # Pattern: "lat":31.123,"lng":121.456 or similar
        coord_patterns = [
            r'"latitude"\s*:\s*([0-9]+\.[0-9]+).*?"longitude"\s*:\s*([0-9]+\.[0-9]+)',
            r'"lat"\s*:\s*([0-9]+\.[0-9]+).*?"lng"\s*:\s*([0-9]+\.[0-9]+)',
            r'"lat"\s*:\s*([0-9]+\.[0-9]+).*?"lon"\s*:\s*([0-9]+\.[0-9]+)',
        ]
        for pattern in coord_patterns:
            m = re.search(pattern, html, re.DOTALL)
            if m:
                return float(m.group(1)), float(m.group(2))
    except Exception:
        pass

    return None


# --------------------------------------------------------------------------- #
# Merge helper
# --------------------------------------------------------------------------- #

def _merge_detail(base: dict, overlay: dict) -> dict:
    """Merge overlay into base, keeping existing base values if overlay is empty/None."""
    for key, val in overlay.items():
        if key == "images":
            if val:
                base["images"] = val
        elif key == "labels":
            if val:
                base["labels"] = list(dict.fromkeys(base.get("labels", []) + val))
        elif key == "rooms":
            if val:
                base["rooms"] = val
        elif val is not None and val != "" and val != []:
            base[key] = val
    return base


# --------------------------------------------------------------------------- #
# Batch enrichment helper
# --------------------------------------------------------------------------- #

def enrich_hotels_batch(
    hotels: list[dict],
    check_in: str | None = None,
    check_out: str | None = None,
    nights: int = 1,
    max_enrich: int = 5,
) -> list[dict]:
    """Enrich a list of hotel dicts with detail data from Ctrip.

    Only enriches hotels with a valid Ctrip URL. Limited to ``max_enrich``
    hotels to keep the operation fast. Hotels without a URL or from OSM/API
    sources are returned unchanged.

    Args:
        hotels: list of hotel dicts (must have "url" field)
        check_in: check-in date for price calculation
        check_out: check-out date for price calculation
        nights: number of nights
        max_enrich: max number of hotels to enrich (default 5)
    """
    enriched_count = 0
    for hotel in hotels:
        if enriched_count >= max_enrich:
            break
        url = hotel.get("url", "")
        if not url or "ctrip.com" not in url:
            continue

        print(f"[ctrip_detail] enriching hotel: {hotel.get('name', 'unknown')} from {url}")
        try:
            detail = scrape_hotel_detail(url, check_in, check_out, nights)
            # Merge detail fields into the hotel dict
            for field in ("images", "description", "labels", "rooms", "total_cost",
                          "discount", "star_rating", "lat", "lng"):
                val = detail.get(field)
                if val is not None and val != "" and val != []:
                    hotel[field] = val
            enriched_count += 1
        except Exception as exc:
            print(f"[ctrip_detail] enrichment failed for {url}: {exc}")
            continue

    return hotels
