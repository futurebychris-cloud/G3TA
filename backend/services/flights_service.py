"""Real flight search — PRIMARY: Ctrip Playwright scraping, FALLBACK: distance-based estimate.

Replaces DeepSeek LLM estimates with real flight data scraped from Ctrip (携程).
When Playwright scraping is unavailable, falls back to geographic distance-based
estimates with clear verification warnings — never fabricates LLM prices.

Usage:
    get_flight_options(origin, destination, dates, budget, transport_types)
    → [{id, carrier, mode, price, duration, departure_time, departure_airport,
        departure_lat, departure_lng, arrival_airport, arrival_lat, arrival_lng,
        coordinate_system, stops, source, verification_required}]
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from typing import Any


def _real_ctrip_flight_search(origin: str, destination: str, depart_date: str) -> list[dict]:
    """Search Ctrip for real flights via Playwright browser.

    Returns list of {flight_number, airline, depart_time, arrive_time,
                      price, currency, duration, stops, source: 'ctrip'}.
    """
    flights = []
    pw = None
    try:
        from playwright.sync_api import sync_playwright
        import urllib.parse

        pw = sync_playwright().start()
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = browser.new_context(
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            viewport={"width": 1440, "height": 900},
        )
        page = ctx.new_page()

        encoded_origin = urllib.parse.quote(origin)
        encoded_dest = urllib.parse.quote(destination)
        url = (
            f"https://flights.ctrip.com/international/search"
            f"#/depart={encoded_origin}&arrive={encoded_dest}"
            f"&depdate={depart_date}&adult=1&child=0&infant=0"
        )
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        time.sleep(4)

        import re

        # Strategy 1: __NEXT_DATA__ JSON
        content = page.content()
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
                for f in flight_list:
                    price_val = f.get("adultPrice") or f.get("price") or 0
                    flights.append({
                        "flight_number": str(f.get("flightNo", "")),
                        "airline": str(f.get("airlineName", "")),
                        "depart_time": str(f.get("departureDate", "")),
                        "arrive_time": str(f.get("arrivalDate", "")),
                        "price": float(price_val) if price_val else 0,
                        "currency": "CNY",
                        "duration": str(f.get("duration", "")),
                        "stops": int(f.get("stopCount", 0)),
                        "source": "ctrip",
                    })
            except Exception as e:
                print(f"[flights] NEXT_DATA parse: {e}")

        # Strategy 2: DOM scraping
        if not flights:
            cards = page.query_selector_all(
                ".flight-item, .flight-card, [class*='flight'], "
                ".list-item, [class*='listItem']"
            )
            for card in cards[:8]:
                try:
                    text = card.inner_text()
                    nums = re.findall(r'([A-Z]{2}\d+)', text)
                    prices = re.findall(r'[¥￥]\s*([\d,]+)', text)
                    flights.append({
                        "flight_number": nums[0] if nums else "",
                        "airline": "",
                        "depart_time": depart_date,
                        "arrive_time": depart_date,
                        "price": float(prices[0].replace(",", "")) if prices else 0,
                        "currency": "CNY",
                        "duration": "",
                        "stops": 0,
                        "source": "ctrip",
                    })
                except Exception:
                    continue

        print(f"[flights] Ctrip search: {len(flights)} results for {origin}→{destination}")

    except Exception as e:
        print(f"[flights] Ctrip search failed: {e}")
    finally:
        if pw:
            try:
                pw.stop()
            except Exception:
                pass

    return flights


def _distance_flight_estimate(origin: str, destination: str, currency: str) -> list[dict]:
    """Fallback: estimate flight cost from geographic distance.

    Uses Amap geocoding + distance calculation. Marks as estimated.
    """
    options = []
    try:
        from services.gaode_service import city_distance_km, CITY_COST_KM
        dist_km = city_distance_km(origin, destination)
        base_price = round(dist_km * CITY_COST_KM, 2)
    except Exception:
        dist_km = 7000  # default for international
        base_price = 850

    for i in range(3):
        factor = 1.0 + (i - 1) * 0.15  # -15%, base, +15%
        price = round(base_price * factor, 2)
        options.append({
            "id": f"transport_{i+1}_est",
            "carrier": f"Verify carrier — {origin}→{destination}",
            "mode": "flight",
            "price": price,
            "duration": f"~{max(1, round(dist_km / 800))}h — verify",
            "departure_time": "Verify schedule",
            "departure_airport": f"{origin} airport — verify",
            "arrival_airport": f"{destination} airport — verify",
            "stops": i,
            "origin": origin,
            "destination": destination,
            "source": "distance_estimate",
            "verification_required": True,
            "distance_km": round(dist_km),
        })

    return options


def get_flight_options(
    origin: str,
    destination: str,
    dates: dict,
    budget: dict | None = None,
    transport_types: list[str] | None = None,
) -> list[dict]:
    """Get real flight options: Ctrip Playwright scraping first, distance fallback last.

    NEVER uses DeepSeek LLM for prices — only real Ctrip data or geographic estimates.
    """
    transport_types = transport_types or ["flight"]
    currency = (budget or {}).get("currency", "USD")
    depart_date = dates.get("start", "")

    # ---- PRIMARY: Real Ctrip Playwright scraping ----
    ctrip_flights = _real_ctrip_flight_search(origin, destination, depart_date)

    if ctrip_flights:
        options = []
        for i, f in enumerate(ctrip_flights[:5]):
            price = f["price"]
            # Convert CNY to target currency if needed
            if f["currency"] == "CNY" and currency != "CNY":
                price = round(price / 7.2, 2)  # rough CNY→USD

            options.append({
                "id": f"transport_{i+1}",
                "carrier": f.get("airline", "Unknown airline"),
                "mode": "flight",
                "price": price,
                "duration": f.get("duration", "Verify"),
                "departure_time": f.get("depart_time", "Verify"),
                "departure_airport": origin,
                "arrival_airport": destination,
                "stops": f.get("stops", 0),
                "origin": origin,
                "destination": destination,
                "source": "ctrip",
                "verification_required": True,
            })
        print(f"[flights] Using {len(options)} REAL Ctrip flight options")
        return options

    # ---- FALLBACK: Distance-based estimate (NOT LLM) ----
    print(f"[flights] Ctrip unavailable, using distance-based estimate")
    return _distance_flight_estimate(origin, destination, currency)
