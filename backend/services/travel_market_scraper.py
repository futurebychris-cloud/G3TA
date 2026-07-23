"""Playwright collection for public Ctrip and Fliggy travel pages.

The collectors intentionally stop at login, CAPTCHA, and risk-control pages.
Every attempt returns a structured payload so both successful records and the
reason for an empty/blocked scrape can be persisted in ``shared_provider_cache``.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Callable

from booking import shared_db


_CITY_NAMES_ZH = {
    "new york": "纽约",
    "shanghai": "上海",
    "beijing": "北京",
    "guangzhou": "广州",
    "shenzhen": "深圳",
    "hangzhou": "杭州",
    "chengdu": "成都",
    "hong kong": "香港",
    "tokyo": "东京",
    "london": "伦敦",
    "paris": "巴黎",
}

_CITY_CODES = {
    "new york": "NYC",
    "shanghai": "SHA",
    "beijing": "BJS",
    "guangzhou": "CAN",
    "shenzhen": "SZX",
    "hangzhou": "HGH",
    "chengdu": "CTU",
    "hong kong": "HKG",
    "tokyo": "TYO",
    "london": "LON",
    "paris": "PAR",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _city_zh(name: str) -> str:
    return _CITY_NAMES_ZH.get(name.strip().casefold(), name.strip())


def _city_code(name: str) -> str:
    key = name.strip().casefold()
    if key in _CITY_CODES:
        return _CITY_CODES[key]
    return re.sub(r"[^A-Za-z]", "", name).upper()[:3]


def _query_key(query: dict) -> tuple[str, str]:
    query_json = json.dumps(
        query, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return query_json, hashlib.sha256(query_json.encode("utf-8")).hexdigest()


def _status_from_text(text: str, urls: list[str] | None = None) -> str:
    haystack = " ".join([text, *(urls or [])]).casefold()
    if any(
        marker in haystack
        for marker in (
            "_____tmd_____/punish",
            "captcha",
            "验证码拦截",
            "滑块验证",
            "安全验证",
            "whaleguard block",
            "http 432",
        )
    ):
        return "blocked"
    if any(
        marker in haystack
        for marker in ("passport.ctrip.com", "login.taobao.com", "redirect to login")
    ):
        return "blocked"
    return "empty"


def _payload(
    provider: str,
    category: str,
    query: dict,
    *,
    status: str,
    results: list[dict] | None = None,
    final_url: str = "",
    page_title: str = "",
    error: str | None = None,
    notes: list[str] | None = None,
) -> dict:
    return {
        "provider": provider,
        "category": category,
        "status": status,
        "query": query,
        "final_url": final_url,
        "page_title": page_title,
        "results": results or [],
        "result_count": len(results or []),
        "error": error,
        "notes": notes or [],
        "captured_at": _now_iso(),
    }


def _plain_browser():
    """Open an ordinary headless browser without solving or bypassing challenges."""
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = None
    for channel in ("chrome", "chromium", None):
        try:
            kwargs = {"headless": True}
            if channel:
                kwargs["channel"] = channel
            browser = pw.chromium.launch(**kwargs)
            break
        except Exception:
            continue
    if browser is None:
        pw.stop()
        raise RuntimeError("Playwright could not launch Chrome or Chromium")
    context = browser.new_context(
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        viewport={"width": 1440, "height": 1000},
    )
    return pw, browser, context.new_page()


def _close_browser(pw, browser) -> None:
    if browser:
        try:
            browser.close()
        except Exception:
            pass
    if pw:
        try:
            pw.stop()
        except Exception:
            pass


def _parse_money(text: str) -> list[float]:
    values = []
    for raw in re.findall(r"[¥￥]\s*([\d,]+(?:\.\d+)?)", text):
        try:
            values.append(float(raw.replace(",", "")))
        except ValueError:
            pass
    return values


def parse_fliggy_flight_cards(
    card_texts: list[str], origin: str, destination: str
) -> list[dict]:
    """Normalize rendered Fliggy flight-card text."""
    results = []
    for index, text in enumerate(card_texts):
        compact = " ".join(text.split())
        prices = _parse_money(compact)
        times = re.findall(r"\b([0-2]\d:[0-5]\d)\b", compact)
        flight_numbers = re.findall(r"\b([A-Z0-9]{2}\d{3,4})\b", compact)
        if not prices or len(times) < 2:
            continue
        results.append(
            {
                "id": f"fliggy_flight_{index}",
                "from": origin,
                "to": destination,
                "flight_number": flight_numbers[0] if flight_numbers else "",
                "departure_time": times[0],
                "arrival_time": times[1],
                "price": prices[0],
                "currency": "CNY",
                "source": "fliggy_live_public",
                "raw_text": compact[:1500],
            }
        )
    return results


def parse_fliggy_nearby_cards(card_texts: list[str]) -> list[dict]:
    """Parse public nearby-route recommendations shown beside flight results."""
    results = []
    for index, text in enumerate(card_texts):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        compact = " ".join(lines)
        prices = _parse_money(compact)
        if not prices:
            continue
        route = lines[0] if lines else ""
        result = {
            "id": f"fliggy_nearby_{index}",
            "result_type": "nearby_recommendation",
            "route": route,
            "prices": prices,
            "currency": "CNY",
            "source": "fliggy_live_public",
            "raw_text": compact[:1500],
        }
        if "票面" in compact:
            result["fare_price"] = prices[0]
        if "税费" in compact and len(prices) > 1:
            result["tax_price"] = prices[1]
            result["total_price"] = round(prices[0] + prices[1], 2)
        results.append(result)
    return results


def scrape_ctrip_flights(query: dict) -> dict:
    from agents.transportation_agent_v2 import (
        _detect_scope,
        _resolve_airport_code,
        _scrape_ctrip_flights,
    )

    if _detect_scope(query["origin"], query["destination"]) == "international":
        origin_code = _resolve_airport_code(query["origin"])
        destination_code = _resolve_airport_code(query["destination"])
        search_url = (
            "https://flights.ctrip.com/international/search/oneway-"
            f"{origin_code}-{destination_code}?"
            + urllib.parse.urlencode(
                {
                    "depdate": query["departure_date"],
                    "cabin": "y_s",
                    "adult": 1,
                    "child": 0,
                    "infant": 0,
                }
            )
        )
    else:
        search_url = (
            "https://flights.ctrip.com/international/search/domestic?"
            + urllib.parse.urlencode(
                {
                    "dcity": query["origin"],
                    "acity": query["destination"],
                    "ddate": query["departure_date"],
                }
            )
        )

    try:
        results, error = _scrape_ctrip_flights(
            query["origin"], query["destination"], query["departure_date"]
        )
        status = "ok" if results else _status_from_text(error or "")
        return _payload(
            "ctrip",
            "flights",
            query,
            status=status,
            results=results,
            final_url=search_url,
            error=error,
        )
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        return _payload(
            "ctrip",
            "flights",
            query,
            status=_status_from_text(message),
            final_url=search_url,
            error=message,
        )


def scrape_ctrip_hotels(query: dict) -> dict:
    from booking.ctrip import search_hotels
    from booking.schemas import HotelSearchRequest

    search_url = (
        "https://hotels.ctrip.com/hotels/list?"
        + urllib.parse.urlencode(
            {
                "city": query["destination"],
                "checkin": query["check_in"],
                "checkout": query["check_out"],
            }
        )
    )
    try:
        request = HotelSearchRequest(
            location=query["destination"],
            check_in=query["check_in"],
            check_out=query["check_out"],
            adults=query.get("adults", 1),
            children=query.get("children", 0),
            rooms=query.get("rooms", 1),
        )
        results = search_hotels(request)
        return _payload(
            "ctrip",
            "hotels",
            query,
            status="ok" if results else "empty",
            results=results,
            final_url=search_url,
        )
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        return _payload(
            "ctrip",
            "hotels",
            query,
            status=_status_from_text(message),
            final_url=search_url,
            error=message,
        )


def _fliggy_flight_url(query: dict) -> str:
    origin = query["origin"]
    destination = query["destination"]
    return (
        "https://sijipiao.fliggy.com/ie/flight_search_result.htm?"
        + urllib.parse.urlencode(
            {
                "searchBy": "1359",
                "_input_charset": "utf-8",
                "tripType": "0",
                "depCityName": _city_zh(origin),
                "depCity": _city_code(origin),
                "depDate": query["departure_date"],
                "arrCityName": _city_zh(destination),
                "arrCity": _city_code(destination),
            }
        )
    )


def scrape_fliggy_flights(query: dict) -> dict:
    url = _fliggy_flight_url(query)
    pw = browser = page = None
    observed_urls: list[str] = []
    try:
        pw, browser, page = _plain_browser()
        page.on("response", lambda response: observed_urls.append(response.url))
        page.goto(url, timeout=45_000, wait_until="domcontentloaded")
        page.wait_for_timeout(10_000)
        body = page.locator("body").inner_text()
        card_texts = page.locator(".flight-result .flight-item").all_inner_texts()
        results = parse_fliggy_flight_cards(
            card_texts, query["origin"], query["destination"]
        )
        nearby = parse_fliggy_nearby_cards(
            page.locator(".nearby-item").all_inner_texts()
        )
        status = "ok" if results else _status_from_text(body, observed_urls)
        notes = []
        if nearby:
            notes.append(
                "The route result was unavailable; public nearby-route offers "
                "visible on the same page were retained separately."
            )
        return _payload(
            "fliggy",
            "flights",
            query,
            status=status,
            results=[*results, *nearby],
            final_url=page.url,
            page_title=page.title(),
            error=(
                "Fliggy real-time flight endpoint required CAPTCHA verification."
                if status == "blocked"
                else None
            ),
            notes=notes,
        )
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        return _payload(
            "fliggy",
            "flights",
            query,
            status=_status_from_text(message, observed_urls),
            final_url=page.url if page else url,
            page_title=page.title() if page else "",
            error=message,
        )
    finally:
        _close_browser(pw, browser)


def scrape_fliggy_hotels(query: dict) -> dict:
    """Submit Fliggy's public hotel form and retain only dated hotel cards."""
    url = "https://www.fliggy.com/?_er_static=true"
    pw = browser = page = None
    observed_urls: list[str] = []
    try:
        pw, browser, page = _plain_browser()
        page.on("response", lambda response: observed_urls.append(response.url))
        page.goto(url, timeout=45_000, wait_until="domcontentloaded")
        page.wait_for_timeout(1_500)
        page.locator(".hotel-txt").click(timeout=5_000)

        destination_zh = _city_zh(query["destination"])
        page.locator(".domestic_cityselection").click(timeout=5_000)
        city_option = page.locator(
            f'[data-testid="popular-city-{destination_zh}"]'
        )
        if city_option.count():
            city_option.click(timeout=5_000)
        else:
            city_input = page.get_by_test_id("domestic-city-input")
            city_input.fill(destination_zh)
            page.wait_for_timeout(800)
            page.locator('[role="option"]').filter(
                has_text=destination_zh
            ).first.click(timeout=5_000)

        check_in = page.get_by_test_id("domestic-checkin-date-input")
        check_in.fill(query["check_in"])
        page.wait_for_timeout(300)
        checkout_display = page.get_by_test_id("domestic-checkout-display")
        checkout_display.click(force=True, timeout=3_000)
        checkout_cell = page.locator(
            f'[data-testid="calendar-cell-{query["check_out"]}"]'
            ".ant-picker-cell-in-view"
        )
        if checkout_cell.count():
            checkout_cell.click(force=True, timeout=3_000)

        page.get_by_test_id("domestic-search-button").click(
            force=True, no_wait_after=True, timeout=5_000
        )
        page.wait_for_timeout(8_000)
        body = page.locator("body").inner_text()

        cards = page.locator(
            '[data-agent-type="hotel-card"], .hotel-card, '
            '[class*="hotel-list"] [class*="hotel-item"]'
        ).all_inner_texts()
        results = []
        for index, text in enumerate(cards[:30]):
            compact = " ".join(text.split())
            prices = _parse_money(compact)
            if not prices:
                continue
            results.append(
                {
                    "id": f"fliggy_hotel_{index}",
                    "name": compact.split(" ¥", 1)[0][:200],
                    "price_per_night": prices[0],
                    "currency": "CNY",
                    "source": "fliggy_live_public",
                    "raw_text": compact[:1500],
                }
            )

        status = "ok" if results else _status_from_text(body, observed_urls)
        error = None
        if not results:
            error = (
                "Fliggy's public hotel form did not expose dated hotel cards "
                "to the unauthenticated browser."
            )
        return _payload(
            "fliggy",
            "hotels",
            query,
            status=status,
            results=results,
            final_url=page.url,
            page_title=page.title(),
            error=error,
        )
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        return _payload(
            "fliggy",
            "hotels",
            query,
            status=_status_from_text(message, observed_urls),
            final_url=page.url if page else url,
            page_title=page.title() if page else "",
            error=message,
        )
    finally:
        _close_browser(pw, browser)


def persist_scrape(payload: dict, ttl_seconds: float = 86_400) -> dict:
    if not shared_db._USE_POSTGRES:
        raise RuntimeError(
            "Remote PostgreSQL is required for provider scrape storage. "
            "Set DATABASE_URL to a hosted PostgreSQL connection string "
            "(for example Supabase or Neon). GitHub itself is not a SQL host, "
            "and this collector will not fall back to local SQLite."
        )
    query_json, cache_key = _query_key(payload["query"])
    namespace = f"market-scrape:{payload['provider']}:{payload['category']}"
    shared_db.save_provider_cache(
        namespace,
        cache_key,
        query_json,
        payload,
        source=f"{payload['provider']}_playwright_{payload['category']}",
        ttl_seconds=ttl_seconds,
    )
    return payload


def scrape_and_persist_all(query: dict, ttl_seconds: float = 86_400) -> list[dict]:
    """Run all public provider collectors and persist each attempt immediately."""
    if not shared_db._USE_POSTGRES:
        raise RuntimeError(
            "DATABASE_URL is missing or is not PostgreSQL. Refusing to scrape "
            "because the requested remote-only storage policy forbids SQLite."
        )
    shared_db.init_shared_db()
    collectors: tuple[Callable[[dict], dict], ...] = (
        scrape_ctrip_flights,
        scrape_ctrip_hotels,
        scrape_fliggy_flights,
        scrape_fliggy_hotels,
    )
    payloads = []
    for collector in collectors:
        payload = collector(query)
        persist_scrape(payload, ttl_seconds=ttl_seconds)
        payloads.append(payload)
        print(
            f"[market-scrape] {payload['provider']}/{payload['category']}: "
            f"{payload['status']} ({payload['result_count']} records)"
        )
    return payloads
