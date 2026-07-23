"""Hotel amenities check service.

Scrapes Ctrip hotel detail pages to check for specific amenities:
- 牙刷 (toothbrush)
- 牙膏 (toothpaste)
- 乳液/润肤露 (lotion/body lotion)
- 拖鞋 (slippers)
- 吹风机 (hair dryer)
- 洗漱用品 (toiletries in general)

Helps the packing list agent know what's provided by the hotel vs what to bring.

Usage:
    from services.hotel_amenities_service import check_amenities
    result = check_amenities("Shanghai", "Jin Jiang Hotel")
    # Returns: {amenities: {toothbrush: true, toothpaste: true, ...}, source: "ctrip"}
"""
from __future__ import annotations

import json
import re
from typing import Any


# Known amenities to check for, with Chinese + English keywords
_AMENITY_KEYWORDS: dict[str, list[str]] = {
    "toothbrush": ["牙刷", "toothbrush", "牙具"],
    "toothpaste": ["牙膏", "toothpaste"],
    "lotion": ["润肤露", "身体乳", "乳液", "护肤", "body lotion", "lotion"],
    "slippers": ["拖鞋", "slippers"],
    "hair_dryer": ["吹风机", "hair dryer", "电吹风"],
    "shampoo": ["洗发水", "洗发露", "shampoo"],
    "shower_gel": ["沐浴露", "沐浴液", "shower gel", "body wash"],
    "toiletries": ["洗漱用品", "一次性洗漱", "toiletries", "amenities"],
    "razor": ["剃须刀", "razor"],
    "comb": ["梳子", "comb"],
    "sewing_kit": ["针线包", "sewing kit"],
    "bathrobe": ["浴袍", "bathrobe"],
}

# Supplementary: known hotel amenity patterns by market
# China hotels: most 3+ star provide toothbrush/toothpaste; Japan hotels: almost always provide everything
_MARKET_DEFAULTS: dict[str, dict[str, bool]] = {
    "china": {
        "toothbrush": True, "toothpaste": True, "slippers": True,
        "shampoo": True, "shower_gel": True, "hair_dryer": True,
        "lotion": False,  # lotion is hit-or-miss in Chinese hotels
    },
    "japan": {
        "toothbrush": True, "toothpaste": True, "lotion": True,
        "slippers": True, "shampoo": True, "shower_gel": True,
        "hair_dryer": True, "bathrobe": True,
    },
    "korea": {
        "toothbrush": True, "toothpaste": False,  # often not provided in Korea
        "lotion": True, "slippers": True, "shampoo": True,
        "shower_gel": True, "hair_dryer": True,
    },
    "thailand": {
        "toothbrush": True, "toothpaste": True, "lotion": True,
        "slippers": True, "shampoo": True, "shower_gel": True,
        "hair_dryer": True,
    },
    "europe": {
        "toothbrush": False, "toothpaste": False,  # rarely provided in Europe
        "lotion": False, "slippers": False,
        "shampoo": True, "shower_gel": True, "hair_dryer": True,
    },
    "usa": {
        "toothbrush": False, "toothpaste": False,
        "lotion": True, "slippers": False,
        "shampoo": True, "shower_gel": True, "hair_dryer": True,
    },
    "singapore": {
        "toothbrush": True, "toothpaste": True, "lotion": True,
        "slippers": True, "shampoo": True, "shower_gel": True,
        "hair_dryer": True,
    },
    "uae": {
        "toothbrush": True, "toothpaste": True, "lotion": True,
        "slippers": True, "shampoo": True, "shower_gel": True,
        "hair_dryer": True, "bathrobe": True,
    },
}


# Destination → market mapping
_DESTINATION_MARKET: dict[str, str] = {
    "shanghai": "china", "beijing": "china", "guangzhou": "china",
    "shenzhen": "china", "hangzhou": "china", "chengdu": "china",
    "chongqing": "china", "xian": "china", "nanjing": "china",
    "suzhou": "china", "xiamen": "china", "kunming": "china",
    "sanya": "china", "wuhan": "china", "qingdao": "china",
    "dalian": "china", "tianjin": "china", "changsha": "china",
    "tokyo": "japan", "osaka": "japan", "kyoto": "japan",
    "seoul": "korea", "busan": "korea", "jeju": "korea",
    "bangkok": "thailand", "chiang mai": "thailand", "phuket": "thailand",
    "singapore": "singapore",
    "paris": "europe", "london": "europe", "rome": "europe",
    "barcelona": "europe", "berlin": "europe", "milan": "europe",
    "amsterdam": "europe",
    "new york": "usa", "los angeles": "usa", "san francisco": "usa",
    "dubai": "uae", "abu dhabi": "uae",
    "mumbai": "india", "delhi": "india",
}


def _get_market_defaults(location: str) -> dict[str, bool]:
    """Get market-default amenity expectations for a location."""
    key = location.lower().strip().split(",")[0].strip()
    market = _DESTINATION_MARKET.get(key, "china")
    return _MARKET_DEFAULTS.get(market, _MARKET_DEFAULTS["china"])


def _scrape_ctrip_hotel_amenities(hotel_name: str, city: str) -> dict | None:
    """Try to get real hotel amenities from Ctrip detail page."""
    try:
        from playwright.sync_api import sync_playwright

        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True, args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox", "--disable-gpu",
        ])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        page = context.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

        # Search Ctrip hotels
        search_url = f"https://hotels.ctrip.com/hotel/{city}?q={hotel_name}"
        page.goto(search_url, timeout=25000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        amenities_found = {}

        # Check __NEXT_DATA__ for facility data
        raw = page.evaluate(
            "() => { const el = document.getElementById('__NEXT_DATA__'); "
            "return el ? el.textContent : null; }"
        )
        if raw:
            try:
                data = json.loads(raw)
                page_text = json.dumps(data, ensure_ascii=False).lower()
                for amenity, keywords in _AMENITY_KEYWORDS.items():
                    amenities_found[amenity] = any(
                        kw.lower() in page_text for kw in keywords
                    )
            except Exception:
                pass

        # DOM fallback: look for facility/amenity sections
        if not amenities_found:
            facility_sections = page.query_selector_all(
                "[class*='facility'], [class*='amenity'], [class*='service_'], "
                "[class*='serviceItem'], [class*='hotel_facility']"
            )
            page_text = " ".join(
                el.inner_text() for el in facility_sections[:10]
            ).lower()

            for amenity, keywords in _AMENITY_KEYWORDS.items():
                amenities_found[amenity] = any(
                    kw.lower() in page_text for kw in keywords
                )

        browser.close()
        pw.stop()

        if amenities_found:
            return amenities_found
    except Exception as e:
        print(f"[hotel_amenities] Ctrip scrape failed: {e}")

    return None


def check_amenities(location: str, hotel_name: str = "") -> dict[str, Any]:
    """Check what amenities are likely provided by hotels in the destination.

    Tries Ctrip scraping first (with hotel name), falls back to market defaults.

    Returns: {
        amenities: {toothbrush: bool, toothpaste: bool, lotion: bool, ...},
        source: "ctrip_scraped" | "market_defaults",
        packing_note: str,
        market: str,
    }
    """
    market_defaults = _get_market_defaults(location)

    # Try Ctrip if hotel name provided
    scraped = None
    if hotel_name:
        scraped = _scrape_ctrip_hotel_amenities(hotel_name, location)

    if scraped:
        # Merge with market defaults for missing fields
        amenities = {**market_defaults, **scraped}
        source = "ctrip_scraped"
    else:
        amenities = dict(market_defaults)
        source = "market_defaults"

    # Generate packing note
    missing = [k for k, v in amenities.items() if not v]
    provided = [k for k, v in amenities.items() if v]

    if missing:
        missing_names = {
            "toothbrush": "牙刷/Toothbrush",
            "toothpaste": "牙膏/Toothpaste",
            "lotion": "润肤露/Lotion",
            "slippers": "拖鞋/Slippers",
            "hair_dryer": "吹风机/Hair dryer",
            "shampoo": "洗发水/Shampoo",
            "shower_gel": "沐浴露/Shower gel",
            "toiletries": "洗漱用品/Toiletries",
            "razor": "剃须刀/Razor",
            "comb": "梳子/Comb",
            "sewing_kit": "针线包/Sewing kit",
            "bathrobe": "浴袍/Bathrobe",
        }
        missing_readable = [missing_names.get(k, k) for k in missing if k in missing_names]
        packing_note = (
            f"Pack these items (not provided by hotel): {', '.join(missing_readable)}. "
            if missing_readable
            else "Check with hotel for specific amenity availability."
        )
    else:
        packing_note = "Hotel provides all standard toiletries — no need to pack extras."

    note_suffix = ""
    if source == "market_defaults":
        note_suffix = (
            f" ({'Chinese' if 'china' in str(_get_market_defaults(location)) else 'Local'} "
            f"market defaults — verify with your specific hotel)"
        )
        packing_note += note_suffix

    return {
        "amenities": amenities,
        "source": source,
        "packing_note": packing_note,
        "missing_items": missing,
        "provided_items": provided,
        "market": _DESTINATION_MARKET.get(
            location.lower().strip().split(",")[0].strip(), "unknown"
        ),
    }
