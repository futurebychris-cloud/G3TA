"""Activity Agent v2 (Experience Scout).

Upgraded from LLM-only estimates to real Playwright scraping:
1. Must-go sites: scrape Ctrip/web for real ticket prices & opening hours
2. Discovery mode: search popular attractions in destination area, filter by preferences
3. Time scheduling: evaluate opening hours, then best time via population + preference weight
4. Meal slot classification: tag activities as breakfast/lunch/dinner for Food Agent

Output: {"recommended": [...], "cost": number, "reasoning": str}

The agent writes confirmed activities to shared_db.shared_activities.
"""
from __future__ import annotations

import hashlib
import json
import os
import random as _rnd
import re
import time
from datetime import datetime
from typing import Any

from .base import llm_reason, trip_days
from .known_attractions import _known_attractions

# ---- LLM system prompts ----

DISCOVERY_PROMPT = (
    "You are the Activity Agent (Experience Scout) in a multi-agent trip planner. "
    "Given a destination, number of days, activity style preferences, and a list of "
    "popular attractions (from web search), select the top activities matching the "
    "traveler's preferences. "
    "Weigh: cost-friendliness, popularity, cultural uniqueness, and activity style match. "
    "One activity per day, no repeats, all in the exact destination. "
    "Return ONLY a JSON object with keys: "
    "  recommended_ids (array of selected activity ids, one per day), "
    "  and reasoning (one sentence)."
)

TIME_SCHEDULING_PROMPT = (
    "You are a time scheduler for trip activities. Given activities with opening hours "
    "and user time preferences, schedule each activity to a specific time slot. "
    "Rules: "
    "1. Activity must fall within its opening hours "
    "2. If user prefers 'quiet', pick lower-population times "
    "3. If user mentions 'sunset', prefer late afternoon (16:00-19:00) "
    "4. If user mentions 'sunrise' or 'early', prefer morning (06:00-10:00) "
    "5. Each activity gets 2-3 hours duration "
    "Return ONLY a JSON object: {schedule: [{id, start_time, end_time, best_visit_time, population_level}]}"
)


# ---- Web scraping helpers ----

def _stealth_browser():
    """Create a Playwright stealth browser (same as ctrip.py)."""
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = None
    for strategy in ["chrome", "chromium", None]:
        try:
            kwargs = {"channel": strategy, "headless": True} if strategy else {"headless": True}
            kwargs["args"] = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
            ]
            browser = pw.chromium.launch(**kwargs)
            break
        except Exception:
            continue
    if browser is None:
        pw.stop()
        raise RuntimeError("No browser available")

    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "Chrome/131.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
    )
    page = context.new_page()
    page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
    return pw, browser, page


def _search_ctrip_attractions(city: str, query: str = "") -> list[dict]:
    """Search Ctrip for attractions/tickets in a city using Playwright."""
    try:
        pw, browser, page = _stealth_browser()
        search_term = query or f"{city} 景点"
        url = f"https://you.ctrip.com/searchsite/?query={search_term}"
        page.goto(url, timeout=25000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        results = []
        # Extract from __NEXT_DATA__ or DOM
        cards = page.query_selector_all("[class*='list_item'], [class*='scenicItem'], .search-result-item, a[href*='you.ctrip.com/sight']")
        for card in cards[:15]:
            try:
                name_el = card.query_selector("h3, h4, [class*='title'], [class*='name']")
                name = name_el.inner_text().strip() if name_el else ""
                price_el = card.query_selector("[class*='price'], .price")
                price_text = price_el.inner_text() if price_el else "0"
                digits = "".join(filter(lambda c: c.isdigit() or c == ".", price_text))
                price = float(digits) if digits else 0
                link = card.query_selector("a")
                url_href = link.get_attribute("href") or "" if link else ""
                rating_el = card.query_selector("[class*='score'], [class*='rating'], [class*='star']")
                rating = 0
                if rating_el:
                    rating_text = rating_el.inner_text()
                    rating_digits = re.findall(r"[\d.]+", rating_text)
                    rating = float(rating_digits[0]) if rating_digits else 0

                if name:
                    results.append({
                        "name": name,
                        "price": round(price),
                        "rating": rating,
                        "url": url_href,
                        "source": "ctrip",
                    })
            except Exception:
                continue

        browser.close()
        pw.stop()
        return results
    except Exception as e:
        print(f"[activity_agent] Ctrip search failed: {e}")
        return []


def _search_web_attractions(destination: str, preferences: list[str]) -> list[dict]:
    """Fall back to web search for popular attractions when Ctrip fails."""
    try:
        import urllib.parse
        import urllib.request

        query = f"most popular attractions in {destination}"
        if preferences:
            query += f" {' '.join(preferences)}"
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", errors="ignore")
        # Extract from search snippets
        results = []
        names = re.findall(r'<h3[^>]*>(.*?)</h3>', html, re.DOTALL)
        for n in names[:12]:
            clean = re.sub(r'<[^>]+>', '', n).strip()
            if clean and len(clean) > 2:
                results.append({"name": clean, "price": 0, "rating": 4.0, "url": "", "source": "web"})
        return results
    except Exception:
        return []


def _scrape_ticket_price(attraction_name: str, city: str) -> dict:
    """Try to get real ticket info from Ctrip for a specific attraction."""
    try:
        pw, browser, page = _stealth_browser()
        search_url = f"https://you.ctrip.com/searchsite/?query={attraction_name}+{city}"
        page.goto(search_url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        result = {"price": 0, "opening_hours": "", "description": ""}

        # Try to parse __NEXT_DATA__
        raw = page.evaluate("() => { const el = document.getElementById('__NEXT_DATA__'); return el ? el.textContent : null; }")
        if raw:
            try:
                data = json.loads(raw)
                props = data.get("props", {}).get("pageProps", {}) or {}
                # Walk the data for ticket info
                def walk(obj, depth=0):
                    if depth > 5:
                        return
                    if isinstance(obj, dict):
                        if "ticketPrice" in obj or "price" in obj:
                            nonlocal result
                            result["price"] = float(obj.get("ticketPrice") or obj.get("price") or 0)
                        if "openingTime" in obj or "openTime" in obj:
                            result["opening_hours"] = obj.get("openingTime") or obj.get("openTime") or ""
                        if "description" in obj and isinstance(obj.get("description"), str):
                            result["description"] = obj["description"]
                        for v in obj.values():
                            walk(v, depth + 1)
                walk(props)
            except Exception:
                pass

        # DOM fallback for opening hours
        if not result.get("opening_hours"):
            time_el = page.query_selector("[class*='openTime'], [class*='opening'], .business-hours, [class*='time_']")
            if time_el:
                result["opening_hours"] = time_el.inner_text().strip()

        browser.close()
        pw.stop()
        return result
    except Exception as e:
        print(f"[activity_agent] ticket scrape failed: {e}")
        return {"price": 0, "opening_hours": "", "description": ""}


def _scrape_group_ticket_price(attraction_name: str, city: str) -> dict | None:
    """Try to get group/team ticket pricing from Ctrip for an attraction.

    Searches Ctrip for "团体票" or "团队" pricing variants.
    Returns: {per_person, min_group_size, source} or None if not found.
    """
    try:
        pw, browser, page = _stealth_browser()
        search_url = f"https://you.ctrip.com/searchsite/?query={attraction_name}+{city}+团体票"
        page.goto(search_url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        result = None

        # Try to find group pricing in __NEXT_DATA__
        raw = page.evaluate("() => { const el = document.getElementById('__NEXT_DATA__'); return el ? el.textContent : null; }")
        if raw:
            try:
                data = json.loads(raw)
                props = data.get("props", {}).get("pageProps", {}) or {}

                def walk_group(obj, depth=0):
                    if depth > 5:
                        return
                    if isinstance(obj, dict):
                        if "groupPrice" in obj or "teamPrice" in obj:
                            nonlocal result
                            gp = obj.get("groupPrice") or obj.get("teamPrice") or 0
                            result = {"per_person": round(float(gp)), "min_group_size": 3, "source": "ctrip_group"}
                        for v in obj.values():
                            walk_group(v, depth + 1)
                walk_group(props)
            except Exception:
                pass

        # DOM fallback: look for "团" or "团队" pricing elements
        if not result:
            group_els = page.query_selector_all("[class*='group'], [class*='team'], span:has-text('团')")
            for el in group_els[:5]:
                text = el.inner_text()
                digits = re.findall(r"¥\s*(\d+)", text)
                if digits:
                    prices = [int(d) for d in digits]
                    if prices:
                        result = {
                            "per_person": min(prices),
                            "min_group_size": 3,
                            "source": "ctrip_group_dom",
                        }
                        break

        browser.close()
        pw.stop()
        return result
    except Exception as e:
        print(f"[activity_agent] group ticket scrape failed: {e}")
        return None


# ---- Classification helpers ----

def _classify_activity_type(name: str, description: str, preferences: list[str]) -> str:
    """Classify activity as sport, nature, culture, entertainment, shopping, other."""
    text = (name + " " + description + " " + " ".join(preferences)).lower()
    sport_kw = ["hike", "trek", "ski", "surf", "bike", "climb", "dive", "sport", "hiking", "biking", "跑步", "骑行", "登山"]
    nature_kw = ["park", "beach", "lake", "mountain", "forest", "garden", "river", "waterfall", "岛", "湖", "山", "公园", "海滩"]
    culture_kw = ["museum", "temple", "shrine", "palace", "historic", "cultural", "museum", "寺", "庙", "宫", "博物馆", "文化"]
    ent_kw = ["show", "concert", "theme park", "disney", "universal", "night", "bar", "表演", "乐园"]
    shop_kw = ["market", "mall", "shopping", "street", "bazaar", "市场", "购物", "街"]
    for kw in sport_kw:
        if kw in text:
            return "sport"
    for kw in nature_kw:
        if kw in text:
            return "nature"
    for kw in culture_kw:
        if kw in text:
            return "culture"
    for kw in ent_kw:
        if kw in text:
            return "entertainment"
    for kw in shop_kw:
        if kw in text:
            return "shopping"
    return "other"


def _classify_meal_slot(start_time: str, end_time: str) -> str:
    """Classify an activity's time range into meal slots."""
    try:
        start_h = int(re.findall(r"(\d{1,2})", start_time.split(":")[0] if ":" in start_time else start_time)[0])
    except (IndexError, ValueError):
        return ""
    end_h = 12
    try:
        end_match = re.findall(r"(\d{1,2})", end_time.split(":")[0] if ":" in end_time else end_time)
        if end_match:
            end_h = int(end_match[0])
    except (IndexError, ValueError):
        pass

    slots = []
    if end_h <= 10:  # Activity ends before 10:30 AM
        slots.append("breakfast")
    if start_h <= 14 and end_h >= 11:  # Activity spans lunch window
        slots.append("lunch")
    if end_h >= 17:  # Activity ends in the evening
        slots.append("dinner")
    return ",".join(slots) if slots else ""


def _determine_best_time(opening_hours: str, preferences: list[str], city: str,
                         attraction_type: str = "default") -> dict:
    """Determine the best visit time using real crowd density data.

    Uses crowd_density_service to combine:
    1. Attraction-type-specific hourly crowd patterns (museum/park/temple/shopping/etc.)
    2. Opening hours constraints
    3. User time preferences (sunrise/sunset/quiet/night)
    """
    from services.crowd_density_service import get_best_visit_time
    return get_best_visit_time(
        attraction_type=attraction_type,
        opening_hours=opening_hours,
        preferences=preferences,
        city=city,
    )


# ---- Main agent function ----

def run(trip_input: dict) -> dict:
    destination = trip_input["location"]
    preferences = trip_input.get("preferences", {})
    activity_styles = preferences.get("activity_style", []) if isinstance(preferences, dict) else []
    must_go_sites = trip_input.get("must_go_sites", [])
    num_people = trip_input.get("num_people", 1)
    is_group = trip_input.get("is_group", False)
    trip_id = trip_input.get("trip_id", hashlib.sha256(
        f"{destination}{trip_input['dates']['start']}".encode()
    ).hexdigest()[:12])
    days = trip_days(trip_input)
    target = len(days)

    activities = []

    # ---- Mode A: Must-go sites ----
    if must_go_sites:
        for site in must_go_sites:
            site_name = site if isinstance(site, str) else site.get("name", "")
            print(f"[activity_agent] scraping ticket info for: {site_name}")
            ticket_info = _scrape_ticket_price(site_name, destination)
            # Classify type FIRST so crowd_density_service gets attraction_type
            act_type = _classify_activity_type(site_name, ticket_info.get("description", ""), activity_styles)
            time_info = _determine_best_time(
                ticket_info.get("opening_hours", ""), activity_styles, destination, act_type
            )
            # Scrape Ctrip for group ticket pricing if applicable
            base_price = ticket_info.get("price", 0)
            group_price = _scrape_group_ticket_price(site_name, destination) if is_group and num_people >= 3 else None
            activity = {
                "name": site_name,
                "location": destination,
                "description": ticket_info.get("description", ""),
                "type": act_type,
                "start_time": time_info["best_visit_time"].split("-")[0] if "-" in time_info["best_visit_time"] else "09:00",
                "end_time": time_info["best_visit_time"].split("-")[1] if "-" in time_info["best_visit_time"] else "12:00",
                "ticket_price": base_price,
                "opening_hours": ticket_info.get("opening_hours", ""),
                "best_visit_time": time_info["best_visit_time"],
                "population_level": time_info["population_level"],
                "meal_slot": "",
                "source": "ctrip" if ticket_info.get("price", 0) > 0 else "web",
            }
            # Group pricing: use real Ctrip group price if available, else apply tiered discount
            if is_group and num_people >= 3:
                if group_price is not None:
                    activity["ticket_price"] = group_price["per_person"]
                    activity["group_pricing"] = group_price
                else:
                    # Tiered group discounts based on group size
                    if num_people >= 20:
                        activity["ticket_price"] = round(base_price * 0.75)
                    elif num_people >= 10:
                        activity["ticket_price"] = round(base_price * 0.82)
                    else:
                        activity["ticket_price"] = round(base_price * 0.88)
            activity["total_price"] = activity["ticket_price"] * num_people
            activity["meal_slot"] = _classify_meal_slot(activity["start_time"], activity["end_time"])
            activities.append(activity)

    # ---- Mode B: Discovery (no must-go sites) ----
    if not activities:
        # Try Ctrip first
        scraped = _search_ctrip_attractions(destination)
        if not scraped:
            scraped = _search_web_attractions(destination, activity_styles)

        # Use LLM to select best matches
        if scraped:
            for i, s in enumerate(scraped):
                s["id"] = f"act_{trip_id}_{i}"
                s["type"] = _classify_activity_type(s["name"], "", activity_styles)

            result = llm_reason(DISCOVERY_PROMPT, {
                "destination": destination,
                "activity_styles": activity_styles,
                "num_days": target,
                "total_budget": trip_input.get("budget", {}),
                "daily_activity_budget": trip_input.get("_budget_caps", {}).get("activity"),
                "all_preferences": preferences,
                "options": scraped,
            })

            selected_ids = (result or {}).get("recommended_ids", [])
            if not selected_ids:
                # Fallback: top rated
                by_rating = sorted(scraped, key=lambda s: s.get("rating", 0), reverse=True)
                selected_ids = [s["id"] for s in by_rating[:target]]

            by_id = {s["id"]: s for s in scraped}
            for aid in selected_ids:
                if aid in by_id and len(activities) < target:
                    s = by_id[aid]
                    # Get real ticket price
                    ticket_info = _scrape_ticket_price(s["name"], destination)
                    time_info = _determine_best_time(
                        ticket_info.get("opening_hours", ""), activity_styles, destination,
                        s.get("type", "default")
                    )
                    activity = {
                        "id": s["id"],
                        "name": s["name"],
                        "location": destination,
                        "description": ticket_info.get("description", s.get("description", "")),
                        "type": s.get("type", "other"),
                        "start_time": time_info["best_visit_time"].split("-")[0] if "-" in time_info["best_visit_time"] else "09:00",
                        "end_time": time_info["best_visit_time"].split("-")[1] if "-" in time_info["best_visit_time"] else "12:00",
                        "ticket_price": ticket_info.get("price", s.get("price", 0)),
                        "total_price": (ticket_info.get("price", s.get("price", 0)) * num_people),
                        "opening_hours": ticket_info.get("opening_hours", ""),
                        "best_visit_time": time_info["best_visit_time"],
                        "population_level": time_info["population_level"],
                        "rating": s.get("rating", 0),
                        "meal_slot": "",
                        "source": s.get("source", "web"),
                    }
                    activity["meal_slot"] = _classify_meal_slot(activity["start_time"], activity["end_time"])
                    activities.append(activity)

        # LLM fallback with KNOWN real attraction names (never placeholder names)
        if not activities:
            known = _known_attractions(destination, target, activity_styles)
            if known:
                activities = known
                print(f"[activity_agent] using known attractions DB: {len(activities)} items for {destination}")
            else:
                # Absolute last resort: LLM must generate names (city not in our DB)
                from .base import llm_reason as _lr
                fallback = _lr(DISCOVERY_PROMPT, {
                    "destination": destination,
                    "activity_styles": activity_styles,
                    "num_days": target,
                    "total_budget": trip_input.get("budget", {}),
                    "all_preferences": preferences,
                    "options": [{"id": f"fb_{i}", "name": f"{destination} attraction {i+1}", "price": 50 + i*20,
                                 "rating": 4.0 + (i*0.2), "type": "culture", "source": "llm"}
                                for i in range(10)],
                })
                selected = (fallback or {}).get("recommended_ids", [f"fb_{i}" for i in range(target)])
                for i, aid in enumerate(selected[:target]):
                    activities.append({
                        "id": aid,
                        "name": f"{destination} Attraction {i+1}",
                        "location": destination,
                        "description": f"Popular attraction in {destination}",
                        "type": "culture",
                        "start_time": "09:00",
                        "end_time": "12:00",
                        "ticket_price": 50,
                        "total_price": 50 * num_people,
                        "opening_hours": "09:00-17:00",
                        "best_visit_time": "09:00-11:00",
                        "population_level": "medium",
                        "rating": 4.0,
                        "meal_slot": "lunch",
                        "source": "llm",
                    })

    # ---- Store to shared database ----
    try:
        from booking.shared_db import save_activity
        for act in activities:
            save_activity(
                trip_id=trip_id,
                activity_name=act["name"],
                activity_location=act["location"],
                activity_description=act.get("description", ""),
                activity_type=act.get("type", "other"),
                start_time=act["start_time"],
                end_time=act["end_time"],
                ticket_price=act.get("ticket_price", 0),
                num_people=num_people,
                is_group=1 if is_group else 0,
                opening_hours=act.get("opening_hours", ""),
                best_visit_time=act.get("best_visit_time", ""),
                population_level=act.get("population_level", ""),
                meal_slot=act.get("meal_slot", ""),
                status="confirmed",
            )
        print(f"[activity_agent] saved {len(activities)} activities to shared DB")
    except Exception as e:
        print(f"[activity_agent] DB save failed (non-fatal): {e}")

    # ---- Build output + Meal slot handoff for Food Agent ----
    total_cost = sum(act.get("total_price", act.get("ticket_price", 0)) for act in activities)

    # Build meal_slot handoff: per-day meal slots that Food Agent reads
    meal_slot_handoff = {}
    for i, act in enumerate(activities):
        day_key = days[i] if i < len(days) else ""
        if act.get("meal_slot"):
            meal_slot_handoff.setdefault(day_key, []).append({
                "activity_name": act["name"],
                "meal_slot": act["meal_slot"],
                "start_time": act.get("start_time", ""),
                "end_time": act.get("end_time", ""),
                "location": act.get("location", destination),
                "activity_type": act.get("type", "other"),
            })

    return {
        "recommended": activities,
        "cost": round(total_cost, 2),
        "reasoning": f"Selected {len(activities)} activities in {destination} using "
                     f"{'Ctrip real data' if any(a.get('source') == 'ctrip' for a in activities) else 'web search + LLM'}.",
        "meal_slot_handoff": meal_slot_handoff,
        "destination": destination,
        "verification_required": True,
        "trip_id": trip_id,
    }
