"""Legacy provider-browser experiments plus read-only search helpers.

The public application uses only the read-only flight/train search functions.
Every function that can submit traveler data or navigate toward an order is
disabled unless ``BOOKING_AUTOMATION_ENABLED=1``. HTTP access is additionally
protected by the server-side booking token in :mod:`security`.

These experiments stop at a provider payment or confirmation checkpoint; they
do not prove that a purchase or reservation exists.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime
from typing import Any


def _require_booking_automation() -> None:
    if os.getenv("BOOKING_AUTOMATION_ENABLED", "").strip().casefold() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise RuntimeError(
            "Booking automation is disabled. Search and compare options, then "
            "complete the purchase with the provider."
        )


# --------------------------------------------------------------------------- #
# Credential store (shared DB + cookies file)
# --------------------------------------------------------------------------- #

def get_stored_credentials(
    provider: str = "ctrip",
    user_id: int | None = None,
) -> dict | None:
    """Look up credentials for one explicitly selected traveler.

    Returns {name, id_number, phone, cookies_file} or None if no user exists.
    Falling back to the first database row would mix identities in a multi-user
    deployment, so an explicit ``user_id`` is required.
    """
    if user_id is None:
        return None
    try:
        from booking import db
        u = db.get_user_by_id(user_id)
        if u:
            cookies_file = os.path.join(
                os.path.dirname(__file__), f"cookies_{provider}.json"
            )
            return {
                "id": u.get("id"),
                "name": u.get("name", ""),
                "id_number": u.get("id_number", ""),
                "phone": u.get("phone", ""),
                "cookies_file": cookies_file,
            }
    except Exception as e:
        print(f"[auto_book] credential lookup failed: {e}")
    return None


def store_credentials(name: str, id_number: str, phone: str) -> int:
    """Deprecated: G3TA no longer persists traveler identity fields."""
    raise RuntimeError(
        "Persistent traveler credential storage is disabled. "
        "Use one-time details only in an authenticated provider request."
    )


# --------------------------------------------------------------------------- #
# Hotel auto-booking (wraps existing Ctrip pipeline)
# --------------------------------------------------------------------------- #

def auto_book_hotel(
    hotel_id: str,
    hotel_name: str,
    hotel_url: str = "",
    check_in: str = "",
    check_out: str = "",
    rooms: int = 1,
    adults: int = 1,
    children: int = 0,
    room_type: str | None = None,
    price_total: float | None = None,
    currency: str = "CNY",
    payment_method: str = "wechat",
    user_id: int | None = None,
) -> dict:
    """Auto-book a hotel via Ctrip Playwright pipeline.

    Steps:
      1. Look up user credentials from DB
      2. Call ctrip.book_hotel() with found credentials + hotel selection
      3. Store the confirmed route in DB
      4. Return order details (user pays in their own WeChat/Alipay)
    """
    _require_booking_automation()
    creds = get_stored_credentials("ctrip", user_id)
    contact = {"name": "", "id_number": "", "phone": ""}
    if creds:
        contact = {
            "name": creds["name"],
            "id_number": creds["id_number"],
            "phone": creds["phone"],
        }

    from booking.schemas import HotelSelection
    selection = HotelSelection(
        id=hotel_id,
        name=hotel_name,
        url=hotel_url,
        room_type=room_type,
        price_total=price_total,
        currency=currency,
    )

    try:
        from booking import ctrip, db as booking_db

        booking = ctrip.book_hotel(
            selection=selection,
            contact=contact,
            dates={"check_in": check_in, "check_out": check_out},
            guests={"rooms": rooms, "adults": adults, "children": children},
            payment_method=payment_method,
        )

        order_no = booking.get("order_no")
        status = booking.get("status", "pending_payment")

        if status in ("pending_payment", "confirmed") and order_no:
            booking_db.save_route(
                user_id=creds.get("id") if creds else None,
                hotel_name=hotel_name,
                hotel_id=hotel_id,
                hotel_url=hotel_url,
                check_in=check_in,
                check_out=check_out,
                rooms=rooms,
                adults=adults,
                children=children,
                room_type=room_type,
                price_total=price_total,
                currency=currency,
                payment_method=payment_method,
                status=status,
                order_no=order_no,
                raw=str({
                    "status": status,
                    "order_no": order_no,
                    "provider": "ctrip",
                }),
            )

        return {
            "status": status,
            "order_no": order_no,
            "message": booking.get(
                "message",
                "Hotel booking reached a provider checkpoint; verify the order with Ctrip.",
            ),
            "provider": "ctrip",
            "type": "hotel",
        }

    except Exception as e:
        print(f"[auto_book] hotel booking failed: {e}")
        return {
            "status": "failed",
            "order_no": None,
            "message": f"Hotel auto-booking failed: {e}",
            "provider": "ctrip",
            "type": "hotel",
        }


# --------------------------------------------------------------------------- #
# Flight auto-booking (Ctrip flights)
# --------------------------------------------------------------------------- #

def _stealth_browser():
    """Create Playwright stealth browser (shared with ctrip.py utils)."""
    try:
        from booking.ctrip import _stealth_browser as ctrip_browser
        return ctrip_browser()
    except Exception:
        pass
    # Minimal fallback
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        viewport={"width": 1440, "height": 900},
    )
    return pw, browser, ctx.new_page()


def _search_ctrip_flights(
    origin: str,
    destination: str,
    depart_date: str,
    return_date: str = "",
    adults: int = 1,
) -> list[dict]:
    """Search Ctrip flights via Playwright.

    Returns list of {flight_number, airline, depart_time, arrive_time,
                      price, currency, duration, stops}.
    """
    flights = []
    pw = None
    try:
        pw, browser, page = _stealth_browser()

        # Build Ctrip flight search URL
        from urllib.parse import quote
        base = "https://flights.ctrip.com/international/search"
        params = (
            f"#/depart={quote(origin)}&arrive={quote(destination)}"
            f"&depdate={depart_date}"
        )
        if return_date:
            params += f"&retdate={return_date}"
        params += f"&adult={adults}&child=0&infant=0"

        url = base + params
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        time.sleep(3)

        # Try to extract flight data from __NEXT_DATA__ or page
        content = page.content()
        import re
        m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', content)
        if m:
            data = json.loads(m.group(1))
            flight_list = (
                data.get("props", {})
                .get("initialState", {})
                .get("flight", {})
                .get("list", [])
            )
            for f in flight_list:
                flights.append({
                    "flight_number": f.get("flightNo", ""),
                    "airline": f.get("airlineName", ""),
                    "depart_time": f.get("departureDate", ""),
                    "arrive_time": f.get("arrivalDate", ""),
                    "price": f.get("adultPrice", 0),
                    "currency": "CNY",
                    "duration": f.get("duration", ""),
                    "stops": f.get("stopCount", 0),
                })

        # Fallback: scrape from rendered cards
        if not flights:
            cards = page.query_selector_all(".flight-item, .flight-card, [class*='flight']")
            for card in cards:
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
                    })
                except Exception:
                    continue

    except Exception as e:
        print(f"[auto_book] flight search failed: {e}")
    finally:
        if pw:
            try:
                pw.stop()
            except Exception:
                pass

    return flights


def auto_book_flight(
    origin: str,
    destination: str,
    depart_date: str,
    return_date: str = "",
    adults: int = 1,
    preferred_flight: str = "",
    max_price: float | None = None,
    payment_method: str = "wechat",
    user_id: int | None = None,
) -> dict:
    """Return a reviewed Ctrip flight choice without submitting an order."""
    _require_booking_automation()

    # Search flights
    flights = _search_ctrip_flights(origin, destination, depart_date, return_date, adults)

    if not flights:
        return {
            "status": "failed",
            "order_no": None,
            "message": f"No flights found for {origin} → {destination} on {depart_date}.",
            "provider": "ctrip",
            "type": "flight",
        }

    # Filter by budget
    if max_price:
        flights = [f for f in flights if f["price"] <= max_price]

    if not flights:
        return {
            "status": "failed",
            "order_no": None,
            "message": f"No flights within budget ({max_price} CNY) found.",
            "provider": "ctrip",
            "type": "flight",
        }

    # Select best flight (cheapest or preferred)
    if preferred_flight:
        selected = next(
            (f for f in flights if preferred_flight.upper() in f["flight_number"].upper()),
            flights[0],
        )
    else:
        selected = min(flights, key=lambda f: f["price"])

    import urllib.parse

    provider_url = (
        "https://flights.ctrip.com/international/search?"
        + urllib.parse.urlencode({
            "origin": origin,
            "destination": destination,
            "depart_date": depart_date,
        })
    )
    return {
        "status": "manual_required",
        "order_no": None,
        "message": (
            f"Flight {selected['flight_number']} ({origin}→{destination}) "
            f"was selected at {selected['price']} CNY. Recheck the current fare "
            "and complete purchase with Ctrip; G3TA did not submit an order."
        ),
        "provider": "ctrip",
        "provider_url": provider_url,
        "type": "flight",
        "details": selected,
    }


# --------------------------------------------------------------------------- #
# Train auto-booking (Ctrip trains — real prices, easier than 12306)
# --------------------------------------------------------------------------- #

def _search_12306_trains(
    origin_station: str,
    dest_station: str,
    depart_date: str,
) -> list[dict]:
    """Search trains via Ctrip's train booking page (NOT 12306 directly).

    Ctrip resells 12306 tickets with real-time prices shown in the search
    results. The page is easier to scrape than 12306 (no CAPTCHA gate on
    the search page), and prices are displayed directly.

    Returns list of {train_number, type, depart_time, arrive_time,
                      duration, price_second_class, price_first_class}.
    """
    import urllib.parse
    trains = []
    pw = None
    try:
        pw, browser, page = _stealth_browser()

        enc_origin = urllib.parse.quote(origin_station)
        enc_dest = urllib.parse.quote(dest_station)
        url = (
            f"https://trains.ctrip.com/trainbooking/search?"
            f"from={enc_origin}&to={enc_dest}&date={depart_date}"
        )
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        time.sleep(5)

        content = page.content()

        # --- Strategy 1: JSON state extraction ---
        for pattern in [
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
        ]:
            m = re.search(pattern, content, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
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
                        for t in train_list:
                            if not isinstance(t, dict):
                                continue
                            train_no = str(t.get("trainNo") or t.get("trainNumber") or "")
                            price_2nd = t.get("price") or t.get("secondClassPrice") or t.get("priceSecond") or 0
                            price_1st = t.get("firstClassPrice") or t.get("priceFirst") or 0
                            price_2nd = float(price_2nd) if price_2nd else 0
                            price_1st = float(price_1st) if price_1st else 0

                            trains.append({
                                "train_number": train_no,
                                "type": "HSR" if train_no.startswith("G") else
                                       "HSR" if train_no.startswith("D") else "Normal",
                                "depart_time": str(t.get("departTime") or t.get("depTime") or ""),
                                "arrive_time": str(t.get("arriveTime") or t.get("arrTime") or ""),
                                "duration": str(t.get("duration") or t.get("runTime") or ""),
                                "price_second_class": round(price_2nd),
                                "price_first_class": round(price_1st),
                            })
                    if trains:
                        break
                except Exception as e:
                    print(f"[auto_book] train JSON parse: {e}")

        # --- Strategy 2: DOM scraping ---
        if not trains:
            rows = page.query_selector_all(
                "tr[id^='ticket_'], .train-item, .train-card, "
                "[class*='train-list'] > div, [class*='TrainItem']"
            )
            for row in rows[:20]:
                try:
                    text = row.inner_text()
                    tn = re.findall(r'([GDCKZT]\d{2,5})', text)
                    train_no = tn[0] if tn else ""

                    prices = re.findall(r'[¥￥]\s*([\d,]+)', text)
                    price_2nd = float(prices[0].replace(",", "")) if prices else 0
                    price_1st = float(prices[1].replace(",", "")) if len(prices) > 1 else 0

                    times = re.findall(r'(\d{2}:\d{2})', text)
                    depart = times[0] if times else ""
                    arrive = times[-1] if len(times) > 1 else ""

                    if train_no:
                        trains.append({
                            "train_number": train_no,
                            "type": "HSR" if train_no.startswith(("G", "D")) else "Normal",
                            "depart_time": depart,
                            "arrive_time": arrive,
                            "duration": "",
                            "price_second_class": round(price_2nd),
                            "price_first_class": round(price_1st),
                        })
                except Exception:
                    continue

        print(f"[auto_book] Ctrip trains: {len(trains)} results with real prices")

    except Exception as e:
        print(f"[auto_book] Ctrip trains search failed: {e}")
    finally:
        if pw:
            try:
                pw.stop()
            except Exception:
                pass

    return trains


def auto_book_train(
    origin_station: str,
    dest_station: str,
    depart_date: str,
    preferred_train: str = "",
    seat_class: str = "second",
    adults: int = 1,
    user_id: int | None = None,
) -> dict:
    """Auto-book a train ticket via 12306.

    Note: 12306 has strong anti-bot protections (CAPTCHA, login verification).
    This function searches available trains and prepares booking data. Actual
    booking may require manual account login + CAPTCHA solving. After successful
    booking drive to payment, the order is recorded in shared_transport.
    """
    _require_booking_automation()
    creds = get_stored_credentials("12306", user_id)
    trip_id = hashlib.sha256(
        f"{origin_station}{dest_station}{depart_date}".encode()
    ).hexdigest()[:12]

    trains = _search_12306_trains(origin_station, dest_station, depart_date)

    if not trains:
        return {
            "status": "failed",
            "order_no": None,
            "message": (
                f"No trains found for {origin_station} → {dest_station} "
                f"on {depart_date}. 12306 may require manual login — try the app."
            ),
            "provider": "12306",
            "type": "train",
        }

    # Select the best train
    if preferred_train:
        selected = next(
            (t for t in trains if preferred_train.upper() in t["train_number"].upper()),
            trains[0],
        )
    else:
        # Prefer high-speed rail (G trains)
        hsr = [t for t in trains if t.get("type") == "HSR"]
        selected = hsr[0] if hsr else trains[0]

    price = (
        selected.get("price_first_class", 0)
        if seat_class == "first"
        else selected.get("price_second_class", 0)
    )

    try:
        from booking.shared_db import save_transport
        save_transport(
            trip_id=trip_id,
            transport_type="train",
            scope="national",
            from_location=origin_station,
            to_location=dest_station,
            departure_time=f"{depart_date} {selected.get('depart_time', '')}",
            arrival_time=f"{depart_date} {selected.get('arrive_time', '')}",
            train_number=selected.get("train_number", ""),
            price=price,
            currency="CNY",
            booking_status="pending",
            booking_ref="",
        )
    except Exception as e:
        print(f"[auto_book] DB save failed: {e}")

    return {
        "status": "manual_required",
        "order_no": None,
        "message": (
            f"Train {selected['train_number']} ({origin_station}→{dest_station}) "
            "was selected. Complete identity verification and purchase in the 12306 app; "
            "this selection is not a confirmed ticket."
        ),
        "provider": "12306",
        "type": "train",
        "details": selected,
    }


# --------------------------------------------------------------------------- #
# Restaurant auto-booking (美团 / Google Maps reservation)
# --------------------------------------------------------------------------- #

def auto_book_restaurant(
    restaurant_name: str,
    date: str,
    time_slot: str = "19:00",
    party_size: int = 2,
    phone: str = "",
    user_id: int | None = None,
) -> dict:
    """Book a restaurant reservation.

    Strategy:
      - China: Attempts 美团 (Meituan) or 大众点评 (Dianping) via Playwright
      - International: Opens Google Maps reservation link
      - Fallback: Returns the provider URL + phone for manual booking

    The function searches for the restaurant, navigates to the booking page,
    fills party size + date + time, and stops at the confirmation step.
    """
    _require_booking_automation()
    creds = (
        get_stored_credentials("meituan", user_id)
        or get_stored_credentials("ctrip", user_id)
    )
    trip_id = hashlib.sha256(
        f"{restaurant_name}{date}{time_slot}".encode()
    ).hexdigest()[:12]

    if not phone and creds:
        phone = creds.get("phone", "")

    pw = None
    try:
        pw, browser, page = _stealth_browser()

        # Try 美团 (domestic China restaurants)
        search_url = (
            f"https://www.meituan.com/s/{restaurant_name}/"
        )
        page.goto(search_url, timeout=15000, wait_until="domcontentloaded")
        time.sleep(2)

        # Try to find the restaurant and navigate to booking
        try:
            first_result = page.query_selector(".poi-item, .search-result-item, [class*='poi']")
            if first_result:
                first_result.click(timeout=3000)
                time.sleep(2)

                # Fill booking form
                try:
                    page.fill('input[name="date"]', date, timeout=2000)
                except Exception:
                    pass
                try:
                    page.fill('input[name="people"]', str(party_size), timeout=2000)
                except Exception:
                    pass
                try:
                    page.fill('input[name="time"]', time_slot, timeout=2000)
                except Exception:
                    pass
        except Exception:
            pass

        return {
            "status": "manual_required",
            "order_no": None,
            "message": (
                f"Restaurant '{restaurant_name}' was prepared for {date} at {time_slot} "
                f"({party_size} guests). Confirm it in the 美团/大众点评 app; "
                "no reservation has been recorded as ordered."
            ),
            "provider": "meituan",
            "type": "restaurant",
        }

    except Exception as e:
        print(f"[auto_book] restaurant booking failed: {e}")
        # Fallback: return manual booking info
        return {
            "status": "manual_required",
            "order_no": None,
            "message": (
                f"Auto-booking unavailable for '{restaurant_name}'. "
                f"Please book via Meituan/Dianping app or call the restaurant."
            ),
            "provider": "manual",
            "type": "restaurant",
            "phone": phone,
        }
    finally:
        if pw:
            try:
                pw.stop()
            except Exception:
                pass


# --------------------------------------------------------------------------- #
# Unified booking entry point — used by the FastAPI layer
# --------------------------------------------------------------------------- #

def book_item(
    item_type: str,
    **kwargs,
) -> dict:
    """Unified booking for any trip component.

    Args:
        item_type: "hotel" | "flight" | "train" | "restaurant"
        **kwargs: Type-specific parameters (see individual functions)

    Returns:
        {status, order_no, message, provider, type, details?}
    """
    _require_booking_automation()
    handlers = {
        "hotel": lambda: auto_book_hotel(
            hotel_id=kwargs.get("id", ""),
            hotel_name=kwargs.get("name", ""),
            hotel_url=kwargs.get("url", ""),
            check_in=kwargs.get("check_in", ""),
            check_out=kwargs.get("check_out", ""),
            rooms=kwargs.get("rooms", 1),
            adults=kwargs.get("adults", 1),
            price_total=kwargs.get("price"),
            payment_method=kwargs.get("payment", "wechat"),
            user_id=kwargs.get("user_id"),
        ),
        "flight": lambda: auto_book_flight(
            origin=kwargs.get("origin", ""),
            destination=kwargs.get("destination", ""),
            depart_date=kwargs.get("date", ""),
            adults=kwargs.get("adults", 1),
            max_price=kwargs.get("max_price"),
            payment_method=kwargs.get("payment", "wechat"),
            user_id=kwargs.get("user_id"),
        ),
        "train": lambda: auto_book_train(
            origin_station=kwargs.get("origin", ""),
            dest_station=kwargs.get("destination", ""),
            depart_date=kwargs.get("date", ""),
            preferred_train=kwargs.get("train", ""),
            adults=kwargs.get("adults", 1),
            user_id=kwargs.get("user_id"),
        ),
        "restaurant": lambda: auto_book_restaurant(
            restaurant_name=kwargs.get("name", ""),
            date=kwargs.get("date", ""),
            time_slot=kwargs.get("time", "19:00"),
            party_size=kwargs.get("party_size", 2),
            user_id=kwargs.get("user_id"),
        ),
    }
    handler = handlers.get(item_type)
    if not handler:
        return {
            "status": "failed",
            "order_no": None,
            "message": f"Unknown booking type: {item_type}",
            "provider": "unknown",
            "type": item_type,
        }
    return handler()


# --------------------------------------------------------------------------- #
# Search-first flow — return top results for customer to pick before booking
# --------------------------------------------------------------------------- #

TOP_N = 5  # number of top results to return


def search_flights(
    origin: str,
    destination: str,
    depart_date: str,
    return_date: str = "",
    adults: int = 1,
    max_price: float | None = None,
) -> dict:
    """Search flights and return top results for customer review.

    This is a non-booking search — the customer sees the top options first,
    then picks one to proceed with auto_book_flight().

    Returns: {status, results: [{...flight details...}], provider, type}
    """
    flights = _search_ctrip_flights(origin, destination, depart_date, return_date, adults)

    if not flights:
        return {
            "status": "no_results",
            "results": [],
            "message": (
                f"No flights found for {origin} → {destination} on {depart_date}. "
                f"Try different dates or check Ctrip directly."
            ),
            "provider": "ctrip",
            "type": "flight",
        }

    # Filter by max_price if specified
    if max_price:
        flights = [f for f in flights if f["price"] <= max_price]

    if not flights:
        return {
            "status": "over_budget",
            "results": [],
            "message": f"All {len(flights)} flights exceed the {max_price} CNY budget.",
            "provider": "ctrip",
            "type": "flight",
        }

    # Sort by price ascending, return top N
    flights.sort(key=lambda f: f.get("price", float("inf")))
    top = flights[:TOP_N]

    return {
        "status": "ok",
        "results": top,
        "total_found": len(flights),
        "message": f"Found {len(flights)} flights, showing top {len(top)} by price.",
        "provider": "ctrip",
        "type": "flight",
    }


def search_trains(
    origin_station: str,
    dest_station: str,
    depart_date: str,
) -> dict:
    """Search 12306 trains and return top results for customer review.

    Returns: {status, results: [{...train details...}], provider, type}
    """
    trains = _search_12306_trains(origin_station, dest_station, depart_date)

    if not trains:
        return {
            "status": "no_results",
            "results": [],
            "message": (
                f"No trains found for {origin_station} → {dest_station} on {depart_date}. "
                f"12306 may require manual login — try the 12306 App directly."
            ),
            "provider": "12306",
            "type": "train",
        }

    # Prioritize HSR (G-trains) first, then by departure time
    hsr = [t for t in trains if t.get("type") == "HSR"]
    normal = [t for t in trains if t.get("type") != "HSR"]
    top = (hsr + normal)[:TOP_N]

    return {
        "status": "ok",
        "results": top,
        "total_found": len(trains),
        "message": f"Found {len(trains)} trains ({len(hsr)} HSR), showing top {len(top)}.",
        "provider": "12306",
        "type": "train",
    }


def book_flight_by_index(
    origin: str,
    destination: str,
    depart_date: str,
    result_index: int = 0,
    adults: int = 1,
    payment_method: str = "wechat",
    user_id: int | None = None,
) -> dict:
    """Search flights, then book the Nth result (0-indexed) from the top results.

    Convenience function that combines search_flights() + auto_book_flight()
    into a single call for the frontend.

    Args:
        result_index: 0-based index into the top search results (0 = cheapest)
    """
    _require_booking_automation()
    search_result = search_flights(origin, destination, depart_date, adults=adults)
    results = search_result.get("results", [])

    if not results:
        return {
            "status": "failed",
            "order_no": None,
            "message": search_result.get("message", "No flights available."),
            "provider": "ctrip",
            "type": "flight",
        }

    if result_index >= len(results):
        result_index = 0  # fallback to cheapest

    selected = results[result_index]
    preferred = selected.get("flight_number", "")

    return auto_book_flight(
        origin=origin,
        destination=destination,
        depart_date=depart_date,
        adults=adults,
        preferred_flight=preferred,
        payment_method=payment_method,
        user_id=user_id,
    )
