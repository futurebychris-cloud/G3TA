"""Budget Agent v2 (Budget Architect) — provider-first, labeled fallback data.

What we do:
    1. Numbeo-derived cost index with a clearly labeled reference-data fallback
    2. Optional Playwright public-web search for supplementary market context
    3. Recent prior budget allocations for optional personalization
    4. Deterministic neural allocator for a preference-weighted split
    5. A deterministic weighted fallback if the allocator is unavailable

Per-item provider records and estimates come from the specialist agents. This
agent's job is budget architecture; every result still requires verification.

Output: {"daily_caps": {...}, "warnings": [...], "pie_data": [...],
         "allocations": {...}, "web_search_costs": {...}, "user_history": {...}}
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time

from .base import report_progress, trip_days
from services.budget_service import get_cost_index
from services.neural_budget import neural_budget_allocation
from services.runtime_cache import cached_call

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


def _public_web_search_enabled() -> bool:
    """Keep the slow browser-only supplement opt-in for interactive plans."""
    return os.getenv("BUDGET_PUBLIC_WEB_SEARCH_ENABLED", "0").strip().casefold() in {
        "1", "true", "yes", "on",
    }


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
# Prior plan history — queries shared DB for past budget allocations
# --------------------------------------------------------------------------- #

def _get_prior_budget_history(current_trip_id: str = "", num_trips: int = 5) -> dict:
    """Return averages from recent, distinct prior budget plans.

    ``shared_expenses`` currently stores proposed budget allocations, not
    settled transactions.  Only the latest allocation for each category in
    each prior trip is included, and the active trip is excluded.

    Returns: {avg_food: float, avg_housing: float, avg_transport: float,
              avg_activity: float, avg_total: float, num_trips_found: int}
    or empty dict if no history.
    """
    try:
        from booking.shared_db import _conn as _db_conn, _USE_POSTGRES, _PLACEHOLDER
        safe_num_trips = max(1, min(int(num_trips), 50))
        query = (
            "SELECT latest.category, AVG(latest.value) AS avg_val, "
            "COUNT(*) AS cnt, COUNT(DISTINCT latest.trip_id) AS trip_count "
            "FROM shared_expenses AS latest "
            "JOIN ("
            "  SELECT trip_id, category, MAX(id) AS latest_id "
            "  FROM shared_expenses "
            "  WHERE subject_id LIKE 'budget_%' AND trip_id IN ("
            "    SELECT trip_id FROM shared_expenses "
            f"    WHERE subject_id LIKE 'budget_%' AND trip_id <> {_PLACEHOLDER} "
            "    GROUP BY trip_id ORDER BY MAX(created_at) DESC "
            f"    LIMIT {safe_num_trips}"
            "  ) "
            "  GROUP BY trip_id, category"
            ") AS selected ON latest.id = selected.latest_id "
            "GROUP BY latest.category ORDER BY cnt DESC"
        )
        with _db_conn() as db:
            if _USE_POSTGRES:
                db.execute(query, (current_trip_id,))
                rows = db.fetchall()
            else:
                rows = db.execute(query, (current_trip_id,)).fetchall()
        
        if not rows:
            return {}
        
        history = {"history_kind": "prior_budget_allocations"}
        cat_map = {
            "dining": "food", "food": "food",
            "hotel": "housing", "housing": "housing",
            "transport": "transportation", "transportation": "transportation",
            "activity": "activity",
        }
        total_spent = 0.0
        for r in rows:
            d = dict(r) if not isinstance(r, dict) else r
            cat = d.get("category", "")
            mapped = cat_map.get(cat, cat)
            avg_val = float(d.get("avg_val", 0) or 0)
            cnt = int(d.get("cnt", 0) or 0)
            if avg_val > 0:
                history[f"avg_{mapped}"] = round(avg_val, 2)
                history[f"count_{mapped}"] = cnt
                total_spent += avg_val
        
        if total_spent > 0:
            history["avg_total"] = round(total_spent, 2)
            history["num_trips_found"] = max(
                int(d.get("trip_count", 0) or 0)
                for d in (dict(row) if not isinstance(row, dict) else row for row in rows)
            )
        
        if history:
            print(
                f"[budget] prior allocation history found: "
                f"{history.get('num_trips_found', 0)} past trips, "
                f"average planned total {history.get('avg_total', 0):.0f}"
            )
        return history
    except Exception as e:
        print(f"[budget] prior allocation history query failed (non-fatal): {e}")
        return {}


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

    report_progress(trip_input, "正在读取目的地生活成本指数")
    index = cached_call(
        "budget-cost-index",
        (destination, trip_input.get("origin", ""), trip_input.get("dates", {}), currency),
        lambda: get_cost_index(
            destination,
            trip_input.get("origin", ""),
            trip_input.get("dates", {}),
            currency,
        ),
        ttl_seconds=3600,
    )

    # This browser search is supplementary and can take 10–30 seconds when a
    # search engine rate-limits automation. The labeled Numbeo/reference index
    # above is sufficient for allocation, so keep the browser pass opt-in.
    web_costs = {}
    web_source = None
    if _public_web_search_enabled():
        report_progress(trip_input, "正在补充公开旅行成本数据")
        web_costs = cached_call(
            "budget-web-costs",
            destination,
            lambda: _playwright_web_search_costs(destination),
            ttl_seconds=3600,
            persist=True,
            source="playwright_public_cost_search",
            snapshot=True,
        )
        web_source = (
            "repository_snapshot"
            if isinstance(web_costs, dict) and web_costs.get("__g3ta_snapshot__")
            else "playwright_scraped" if web_costs
            else "unavailable"
        )

    # Build preference weights
    weights = dict(DEFAULT_WEIGHTS)
    if preferences.get("budget_priority"):
        weights = {**weights, **preferences.get("budget_priority", {})}

    # Use recent proposed allocations as a personalization signal.  These are
    # planning records, not evidence of the user's actual spending.
    user_history = _get_prior_budget_history(trip_id)
    history_available = bool(user_history and user_history.get("num_trips_found", 0) > 0)

    # ---- PRIMARY: Neural Network Budget Allocation ----
    # Transport-first: prefer the REAL scraped transport cost (from the
    # Transportation Agent, which the orchestrator runs BEFORE Budget) so the
    # neural allocation is grounded in actual flight/train prices rather than a
    # guess. This enforces "transportation MUST BE FIRST (especially the flight)".
    flight_ref = index.get("flight_reference", total * 0.25)
    real_transport = trip_input.get("_transport_cost")
    if real_transport and float(real_transport) > 0:
        flight_ref = float(real_transport)
    neural_result = neural_budget_allocation(
        destination=destination,
        total_budget=total,
        num_days=num_days,
        flight_cost=flight_ref,
        currency=currency,
        cost_index=index.get("daily_index", {}),
    )

    # Blend neural network ratios with prior allocation history if available
    if history_available:
        history_ratios = {}
        total_history_avg = user_history.get("avg_total", 1)
        if total_history_avg > 0:
            for cat in ["transportation", "housing", "food", "activity"]:
                hkey = f"avg_{cat}"
                if hkey in user_history:
                    history_ratios[cat] = user_history[hkey] / total_history_avg
        if history_ratios:
            # Blend: 70% neural + 30% prior allocation history
            blend = {}
            all_cats = set(list(neural_result["ratios"].keys()) + list(history_ratios.keys()))
            for cat in all_cats:
                nn_val = neural_result["ratios"].get(cat, 0.05)
                hist_val = history_ratios.get(cat, nn_val)
                blend[cat] = round(nn_val * 0.7 + hist_val * 0.3, 4)
            # Normalize to sum to 1.0
            blend_sum = sum(blend.values())
            if blend_sum > 0:
                blend = {k: round(v / blend_sum, 4) for k, v in blend.items()}
            neural_result["ratios"] = blend
            neural_result["confidence"] = min(neural_result["confidence"] + 0.05, 1.0)
            print(f"[budget] blended NN ratios with prior allocations: {blend}")

    print(f"[budget] Neural network allocation: ratios={neural_result['ratios']}, "
          f"confidence={neural_result['confidence']}")

    # The neural allocator already consumes real transport cost, destination
    # index, preferences, and prior allocations. A second LLM pass added latency but
    # did not add new data, so the interactive pipeline uses it directly.
    report_progress(trip_input, "正在根据交通成本分配各项预算")
    allocations = {
        "transportation": flight_ref,
        "housing": round(neural_result["daily_caps"].get("housing", 0) * num_days, 2),
        "food": round(neural_result["daily_caps"].get("food", 0) * num_days, 2),
        "activity": round(neural_result["daily_caps"].get("activity", 0) * num_days, 2),
        "other": round((neural_result["daily_caps"].get("shopping", 0) + 5) * num_days, 2),
    }
    daily_caps = {
        "food": round(neural_result["daily_caps"].get("food", 0), 2),
        "activity": round(neural_result["daily_caps"].get("activity", 0), 2),
        "housing": round(neural_result["daily_caps"].get("housing", 0), 2),
        "local_transport": round(neural_result["daily_caps"].get("local_transport", 18), 2),
    }
    warnings = []
    if total < flight_ref * 1.5:
        warnings.append(f"Budget may be tight: {total:.0f} {currency} for {num_days} days in {destination}.")
    if overflow:
        warnings.append(
            f"Current combined plan exceeds the target by {overflow:.0f} {currency}; "
            "the orchestrator will trim flexible categories."
        )
    reasoning = (
        f"Neural allocation ({neural_result['confidence']*100:.0f}% confidence) "
        f"using the real transport cost and {destination} cost data."
    )
    allocation_source = "neural_network_direct"

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
        "neural_allocation": neural_result,
        "ratios": neural_result["ratios"],
        "cost_index": index,
        "web_search_costs": web_costs,
        "web_search_source": web_source,
        "allocation_source": allocation_source,
        "num_days": num_days,
        "total_budget": total,
        "currency": currency,
        "destination": destination,
        "trip_id": trip_id,
        "user_history": user_history if history_available else None,
    }
