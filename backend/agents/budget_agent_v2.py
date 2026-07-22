"""Budget Agent v2 (Budget Architect) — Playwright-only real data.

ZERO mock. ZERO urllib+regex web scraping. ALL web data comes from Playwright.

What we do:
    1. LLM cost index via budget_service (DeepSeek estimates based on destination)
    2. Playwright search on Numbeo / travel cost sites for real market data
    3. LLM allocation (preference-weighted split of total budget)
    4. Fallback: deterministic weighted allocation IF LLM is completely unavailable
       (clearly labeled as "estimated", not scraped)

The REAL per-item costs come from the specialist agents (transport, housing,
food, activity). This agent's job is budget ARCHITECTURE — how the total should
be split — using the best available reference data.

Output: {"daily_caps": {...}, "warnings": [...], "pie_data": [...],
         "allocations": {...}, "web_search_costs": {...}}
"""
from __future__ import annotations

import hashlib
import json
import re
import time

from .base import llm_reason, trip_days
from services.budget_service import get_cost_index

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

PIE_COLORS = {
    "transportation": "#FF6384", "housing": "#36A2EB", "food": "#FFCE56",
    "activity": "#4BC0C0", "other": "#9966FF", "local_transport": "#FF9F40",
}
ALLOC_ORDER = ["transportation", "housing", "food", "activity", "other"]
DEFAULT_WEIGHTS = {
    "transportation": 0.30, "housing": 0.35, "food": 0.18,
    "activity": 0.12, "other": 0.05,
}

CATEGORY_DB_MAP = {
    "transportation": "transport",
    "housing": "hotel",
    "food": "dining",
    "activity": "activity",
    "other": "other",
}

BUDGET_SYSTEM_PROMPT = (
    "You are the Budget Architect in a multi-agent trip planner. You receive: "
    "total budget, currency, number of days, real web-scraped average costs "
    "for the destination, user preference weights, and a cost index. "
    "Allocate the budget into per-category caps and produce a pie chart data "
    "structure. "
    "Rules: "
    "1. Transportation (flights/trains) is allocated FIRST from the total budget "
    "2. Housing receives the next largest share "
    "3. Food and activities get weighted by user preferences "
    "4. If budget is too tight, generate warnings "
    "Return ONLY JSON: {daily_caps: {food, activity, housing, local_transport}, "
    "pie_data: [{label, value, color}], "
    "allocations: {transportation, housing, food, activity, other}, "
    "warnings: [string], reasoning: string}"
)


# --------------------------------------------------------------------------- #
# Playwright web search for real destination costs
# --------------------------------------------------------------------------- #

def _stealth_browser():
    """Get a stealth Playwright browser."""
    try:
        from booking.ctrip import _stealth_browser as ctrip_browser
        return ctrip_browser()
    except Exception:
        pass
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


def _scrape_numbeo_costs(destination: str) -> dict:
    """Scrape Numbeo cost-of-living for a city using Playwright.

    Numbeo (numbeo.com) is the largest crowd-sourced cost-of-living database.
    We search for "{destination} cost of living numbeo" and extract daily
    expense estimates from the search result snippets or the Numbeo page.

    Returns: {food, hotel, transport} daily averages, or {} on failure.
    """
    costs = {}
    pw = None
    try:
        pw, browser, page = _stealth_browser()
        query = f"{destination} cost of living travel daily budget"
        url = f"https://duckduckgo.com/?q={query}&ia=web"
        page.goto(url, timeout=15000, wait_until="domcontentloaded")
        time.sleep(2)

        text = page.inner_text("body").lower()

        # Extract USD amounts near food/meal/hotel/transport keywords
        for key, patterns in [
            ("food", [r"meal[s]?\s*(?:cost|price|avg).*?\$?\s*(\d+)",
                      r"food\s*(?:cost|budget|avg).*?\$?\s*(\d+)",
                      r"(\d+)\s*(?:per day|/day).*?(?:food|meal|dining)"]),
            ("hotel", [r"hotel\s*(?:cost|price|avg|night).*?\$?\s*(\d+)",
                       r"accommodation\s*(?:cost|avg).*?\$?\s*(\d+)",
                       r"(\d+)\s*(?:per night|/night).*?(?:hotel|room)"]),
            ("transport", [r"transport(?:ation)?\s*(?:cost|budget).*?\$?\s*(\d+)",
                           r"local\s+transport.*?\$?\s*(\d+)"]),
        ]:
            for pat in patterns:
                matches = re.findall(pat, text, re.IGNORECASE)
                if matches:
                    vals = [int(m) for m in matches if 1 < int(m) < 5000]
                    if vals:
                        costs[key] = sum(vals) / len(vals)
                        break

        print(f"[budget] Numbeo/DuckDuckGo search: {costs}")
    except Exception as e:
        print(f"[budget] Playwright web search failed: {e}")
    finally:
        if pw:
            try:
                pw.stop()
            except Exception:
                pass
    return costs


def _scrape_travel_cost_site(destination: str) -> dict:
    """Alternative: scrape budgetyourtrip.com for destination cost data.

    Falls back if Numbeo search fails.
    """
    costs = {}
    pw = None
    try:
        pw, browser, page = _stealth_browser()
        slug = destination.lower().replace(" ", "-")
        url = f"https://www.budgetyourtrip.com/{slug}"
        page.goto(url, timeout=15000, wait_until="domcontentloaded")
        time.sleep(2)

        text = page.inner_text("body").lower()

        # Extract daily cost estimates
        daily_match = re.search(
            r'(?:daily|per day|avg)\s*(?:cost|budget|spend).*?\$?\s*(\d+)',
            text, re.IGNORECASE
        )
        if daily_match:
            daily = int(daily_match.group(1))
            costs["total_daily"] = daily

        # Extract per-category costs
        for key, pattern in [
            ("food", r"food.*?(?:cost|budget).*?\$?\s*(\d+)"),
            ("hotel", r"(?:hotel|accommodation).*?\$?\s*(\d+)"),
            ("transport", r"(?:transport|getting around).*?\$?\s*(\d+)"),
        ]:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                val = int(m.group(1))
                if 1 < val < 5000:
                    costs[key] = val

        print(f"[budget] BudgetYourTrip scrape: {costs}")
    except Exception as e:
        print(f"[budget] BudgetYourTrip scrape failed: {e}")
    finally:
        if pw:
            try:
                pw.stop()
            except Exception:
                pass
    return costs


def _playwright_web_search_costs(destination: str) -> dict:
    """Get real destination costs using Playwright web search.

    Tries multiple sources in order:
        1. Numbeo via DuckDuckGo search
        2. BudgetYourTrip.com direct scrape
    Returns empty dict if all sources fail.
    """
    costs = _scrape_numbeo_costs(destination)
    if not costs:
        costs = _scrape_travel_cost_site(destination)
    return costs


# --------------------------------------------------------------------------- #
# Pie data builder
# --------------------------------------------------------------------------- #

def _build_pie_data(allocations: dict) -> list[dict]:
    """Build pie chart data from allocation dict."""
    return [
        {"label": k.replace("_", " ").title(), "value": round(v, 2),
         "color": PIE_COLORS.get(k, "#CCCCCC")}
        for k, v in allocations.items() if v > 0
    ]


# --------------------------------------------------------------------------- #
# Deterministic fallback (LLM unavailable — CLEARLY labeled as estimated)
# --------------------------------------------------------------------------- #

def _weighted_allocate(total: float, weights: dict, cost_index: dict,
                       num_days: int) -> dict:
    """Deterministic weighted budget allocation.

    NOTE: This is a FALLBACK for when the LLM is unavailable. The result is
    labeled as 'estimated' — NOT real scraped data.
    """
    flight_ref = cost_index.get("flight_reference", total * 0.25)
    remaining = max(total - flight_ref, 0)
    result = {"transportation": round(flight_ref, 2)}

    cat_map = {"housing": "housing", "food": "food", "activity": "activity"}
    daily_index = cost_index.get("daily_index", {})
    for cat, idx_key in cat_map.items():
        base_daily = daily_index.get(idx_key, weights.get(cat, 0.18) * 100)
        result[cat] = round(base_daily * num_days, 2)

    daily_cats_sum = sum(result.get(k, 0) for k in ["housing", "food", "activity"])
    if daily_cats_sum > 0 and sum(v for k, v in result.items()) > total:
        scale = remaining / daily_cats_sum if daily_cats_sum > 0 else 1
        for k in ["housing", "food", "activity"]:
            result[k] = round(result[k] * scale, 2)

    result["other"] = round(max(total - sum(result.values()), 0), 2)
    return result


# --------------------------------------------------------------------------- #
# Main agent
# --------------------------------------------------------------------------- #

def run(trip_input: dict, overflow: float | None = None) -> dict:
    destination = trip_input["location"]
    days = trip_days(trip_input)
    num_days = len(days)
    total = float(trip_input["budget"]["total"])
    currency = trip_input["budget"].get("currency", "CNY")
    trip_id = trip_input.get("trip_id", hashlib.sha256(
        f"{destination}{trip_input['dates']['start']}".encode()
    ).hexdigest()[:12])
    preferences = trip_input.get("preferences", {})

    # Get cost index from LLM-based service (DeepSeek estimates)
    index = get_cost_index(destination, trip_input.get("origin", ""),
                           trip_input.get("dates", {}), currency)

    # Web search for real destination costs via Playwright
    web_costs = _playwright_web_search_costs(destination)
    web_source = "playwright_scraped" if web_costs else "unavailable"

    # Build preference weights
    weights = dict(DEFAULT_WEIGHTS)
    if preferences.get("budget_priority"):
        weights = {**weights, **preferences.get("budget_priority", {})}

    # LLM reasoning for smart allocation
    payload = {
        "total_budget": total, "currency": currency, "num_days": num_days,
        "destination": destination,
        "estimated_flight_cost": index.get("flight_reference"),
        "destination_daily_cost_index": index["daily_index"],
        "web_scraped_costs": web_costs,
        "web_data_source": web_source,
        "cost_level": index.get("cost_level"),
        "preference_weights": weights,
        "all_preferences": preferences,
    }
    if overflow:
        payload["overflow_to_trim"] = overflow
        payload["instruction"] = "Plan is OVER budget. Tighten daily caps to fit."

    result = llm_reason(BUDGET_SYSTEM_PROMPT, payload)

    # Build allocations
    if result and "allocations" in result:
        allocations = result["allocations"]
        daily_caps = result.get("daily_caps", {})
        warnings = result.get("warnings", [])
        reasoning = result.get("reasoning", "")
        allocation_source = "llm_reasoned"
    else:
        allocations = _weighted_allocate(total, weights, index, num_days)
        daily_caps = {
            "food": round(allocations.get("food", 0) / num_days, 2) if num_days else 0,
            "activity": round(allocations.get("activity", 0) / num_days, 2) if num_days else 0,
            "housing": round(allocations.get("housing", 0) / num_days, 2) if num_days else 0,
            "local_transport": round(
                index["daily_index"].get("local_transport", 18), 2
            ),
        }
        warnings = []
        if total < index.get("flight_reference", 0) * 1.5:
            warnings.append(
                f"Budget may be tight: {total:.0f} {currency} for "
                f"{num_days} days in {destination}."
            )
        reasoning = (
            f"Deterministic allocation (LLM unavailable) based on "
            f"{destination} cost index. All amounts are ESTIMATES — "
            f"verify with real-time booking sites."
        )
        allocation_source = "deterministic_fallback"

    # Build pie chart data
    pie_data = _build_pie_data(allocations)

    # Store to shared database
    try:
        from booking.shared_db import add_expense
        for cat, val in allocations.items():
            if val > 0:
                db_cat = CATEGORY_DB_MAP.get(cat, "other")
                add_expense(
                    trip_id=trip_id, category=db_cat,
                    subject_id=f"budget_{cat}",
                    subject_name=f"{cat} allocation",
                    date=days[0], value=val, currency=currency,
                    notes=f"Budget allocation ({allocation_source})",
                )
    except Exception as e:
        print(f"[budget] DB save failed (non-fatal): {e}")

    return {
        "daily_caps": daily_caps,
        "warnings": warnings,
        "reasoning": reasoning,
        "allocations": allocations,
        "pie_data": pie_data,
        "cost_index": index,
        "web_search_costs": web_costs,
        "web_search_source": web_source,
        "allocation_source": allocation_source,
        "num_days": num_days,
        "total_budget": total,
        "currency": currency,
        "destination": destination,
        "trip_id": trip_id,
    }
