"""Food Agent v2 (Taste Editor).

Upgraded from LLM-only estimates:
1. Google Maps restaurant search via Playwright
2. Menu scraping from restaurant pages
3. Dish classification (main/starter/dessert/drink)
4. Taste profile filtering & cost calculation
5. Shared_meals database integration

Output: {"daily_meals": [...], "cost": number, "reasoning": str}
"""
from __future__ import annotations
import hashlib, json, re, time, urllib.parse
from .base import llm_reason, trip_days
from services.food_service import get_food_options, matches_cuisine_preferences

FOOD_DISCOVERY_PROMPT = (
    "You are the Food Agent (Taste Editor) in a multi-agent trip planner. "
    "Given restaurant search results and user preferences (cuisine type, taste profile, "
    "budget), select the best restaurants and specific dishes for each meal slot. "
    "Rules: 1 dish per meal slot per day, balanced within the daily food budget. "
    "Return ONLY JSON: {selections: [{day, date, slot, restaurant_name, dish_name, dish_category, price}]}"
)

MENU_DISH_PROMPT = (
    "You are analyzing restaurant menus. From the provided menu text, extract the top "
    "dishes categorized as: main, starter, dessert, drink. For each dish provide: "
    "name, category, estimated_price, popularity_score (0-10 based on menu prominence). "
    "Return ONLY JSON: {dishes: [{name, category, price, popularity}]}"
)

TASTE_PROFILES = {
    "spicy": {"辣", "spicy", "hot", "chili", "pepper", "mala"},
    "sweet": {"甜", "sweet", "dessert", "sugar", "honey"},
    "savory": {"咸", "savory", "salty", "umami", "soy"},
    "sour": {"酸", "sour", "vinegar", "lemon", "lime"},
    "mild": {"清淡", "mild", "light", "plain", "bland"},
    "rich": {"浓郁", "rich", "creamy", "heavy", "buttery"},
    "fresh": {"鲜", "fresh", "seafood", "vegetable", "salad"},
}

_SLOTS = ["breakfast", "lunch", "dinner"]
_SLOT_WEIGHTS = {"breakfast": 0.25, "lunch": 0.35, "dinner": 0.40}

# ---- Playwright browser ----

def _stealth_browser():
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = None
    for s in ["chrome", "chromium", None]:
        try:
            kw = {"channel": s, "headless": True} if s else {"headless": True}
            kw["args"] = ["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-gpu"]
            browser = pw.chromium.launch(**kw)
            break
        except Exception:
            continue
    if not browser:
        pw.stop()
        raise RuntimeError("No browser")
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/131.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
        locale="zh-CN",
    )
    page = ctx.new_page()
    page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    return pw, browser, page


# ---- Google Maps restaurant search ----

def _search_google_maps_restaurants(destination: str, cuisine: str = "") -> list[dict]:
    """Search Google Maps for restaurants in the destination city."""
    try:
        pw, browser, page = _stealth_browser()
        query = f"best {cuisine} restaurants in {destination}"
        url = f"https://www.google.com/maps/search/{urllib.parse.quote(query)}"
        page.goto(url, timeout=25000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)

        results = []
        # Google Maps renders results via JS; try to extract from page
        cards = page.query_selector_all("[role='article'], [class*='section-result'], [class*='Nv2PK']")
        for card in cards[:15]:
            try:
                name_el = card.query_selector("[class*='fontHeadlineSmall'], [class*='qBF1Pd'], h3, [aria-label]")
                name = name_el.inner_text().strip() if name_el else ""
                # Extract rating
                rating_text = card.inner_text() or ""
                rating_match = re.search(r"([\d.]+)\s*★", rating_text)
                rating = float(rating_match.group(1)) if rating_match else 0
                # Extract price level
                price_match = re.findall(r"[¥$€]{1,4}", rating_text)
                price_level = len(price_match) if price_match else 1

                if name and len(name) > 2:
                    results.append({
                        "name": name,
                        "cuisine_type": cuisine or "Local",
                        "rating": rating,
                        "price_level": price_level,
                        "estimated_price": price_level * 30,  # rough estimate
                        "source": "google_maps",
                    })
            except Exception:
                continue

        browser.close()
        pw.stop()
        return results
    except Exception as e:
        print(f"[food_agent] Google Maps search failed: {e}")
        return []


# ---- Menu scraping ----

def _scrape_restaurant_menu(restaurant_name: str, city: str) -> list[dict]:
    """Try to find and scrape a restaurant's menu online."""
    try:
        pw, browser, page = _stealth_browser()
        query = f"{restaurant_name} {city} menu 菜单 推荐菜"
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        page.goto(url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Extract text snippets that look like menu items
        text = page.inner_text("body") or ""
        # Look for dish-like patterns
        dish_patterns = re.findall(
            r'([^。！？\n]{2,20}(?:鱼|肉|鸡|鸭|牛|羊|虾|蟹|面|饭|汤|菜|锅|堡|烤|蒸|炒|炸|煮|炖|烧)[^。！？\n]{0,10})',
            text,
        )
        # Also look for price patterns like ¥XX or $XX
        price_matches = re.findall(r'[¥$](\d+)', text)

        dishes = []
        seen = set()
        for d in dish_patterns[:12]:
            clean = re.sub(r'<[^>]+>', '', d).strip()
            if clean and clean not in seen and len(clean) >= 2:
                seen.add(clean)
                dishes.append({"name": clean, "category": "main", "price": 0, "popularity": 5})

        browser.close()
        pw.stop()

        # Try LLM classification of scraped dishes
        if dishes:
            result = llm_reason(MENU_DISH_PROMPT, {
                "restaurant": restaurant_name,
                "raw_dishes": dishes,
            })
            if result and result.get("dishes"):
                return result["dishes"]

        return dishes
    except Exception as e:
        print(f"[food_agent] Menu scrape failed: {e}")
        return []


# ---- Dish classification ----

def _classify_dish_category(name: str) -> str:
    """Classify a dish as main, starter, dessert, or drink."""
    n = name.lower()
    dessert_kw = ["dessert", "cake", "ice cream", "pudding", "sweet", "甜点", "蛋糕", "冰淇淋", "布丁"]
    drink_kw = ["tea", "coffee", "juice", "soda", "beer", "wine", "cocktail", "茶", "咖啡", "果汁", "酒", "可乐"]
    starter_kw = ["salad", "soup", "appetizer", "snack", "沙拉", "汤", "小菜", "凉菜", "前菜", "小吃"]
    for kw in dessert_kw:
        if kw in n:
            return "dessert"
    for kw in drink_kw:
        if kw in n:
            return "drink"
    for kw in starter_kw:
        if kw in n:
            return "starter"
    return "main"


def _match_taste_profile(dish_name: str, cuisine: str, taste_prefs: list[str]) -> bool:
    """Check if a dish matches user's taste preferences."""
    if not taste_prefs:
        return True
    text = (dish_name + " " + cuisine).lower()
    for pref in taste_prefs:
        profile = TASTE_PROFILES.get(pref.lower(), set())
        if profile and any(kw in text for kw in profile):
            return True
    # If no match found and preferences are set, still include (not strict exclusion)
    return True


# ---- Main agent ----

def run(trip_input: dict) -> dict:
    destination = trip_input["location"]
    cuisine_tags = trip_input.get("preferences", {}).get("bites", [])
    taste_prefs = trip_input.get("preferences", {}).get("taste", [])
    raw_daily_cap = trip_input.get("_budget_caps", {}).get("food")
    if raw_daily_cap is None:
        raw_daily_cap = trip_input.get("preferences", {}).get("food_budget")
    try:
        daily_food_cap = max(float(raw_daily_cap), 0) if raw_daily_cap is not None else None
    except (TypeError, ValueError):
        daily_food_cap = None
    days = trip_days(trip_input)
    trip_id = trip_input.get("trip_id", hashlib.sha256(
        f"{destination}{trip_input['dates']['start']}".encode()
    ).hexdigest()[:12])
    currency = trip_input["budget"].get("currency", "CNY")

    # ---- Step 1: Try real Google Maps restaurant search ----
    real_restaurants = []
    target_cuisines = cuisine_tags if cuisine_tags else ["local", destination]
    for cuisine in target_cuisines[:3]:  # Search top 3 cuisines
        found = _search_google_maps_restaurants(destination, cuisine)
        real_restaurants.extend(found)
        if len(real_restaurants) >= 12:
            break

    # ---- Step 2: Get LLM food options as fallback/enrichment ----
    all_options = get_food_options(
        destination, cuisine_tags,
        num_days=len(days),
        budget=trip_input.get("budget", {}),
        preferences=trip_input.get("preferences", {}),
        time_constraints=trip_input.get("time_constraints", ""),
        daily_budget=daily_food_cap,
    )

    # Merge real results with LLM options
    enriched_options = list(all_options)
    existing_names = {o["name"].casefold() for o in enriched_options}
    for r in real_restaurants:
        if r["name"].casefold() not in existing_names:
            enriched_options.append({
                "id": f"food_google_{len(enriched_options)}",
                "name": r["name"],
                "cuisine": r.get("cuisine_type", "Local"),
                "cuisine_family": r.get("cuisine_type", "Local"),
                "price": r.get("estimated_price", 30),
                "meal_type": "dinner",  # default; will be adjusted
                "area": destination,
                "rating": r.get("rating", 0),
                "tags": [r.get("cuisine_type", "local").lower(), "google_maps"],
                "source": "google_maps",
            })

    # ---- Step 3: Scrape menus for top restaurants ----
    dish_map = {}
    for opt in enriched_options[:5]:  # Scrape top 5
        if opt.get("source") == "google_maps":
            dishes = _scrape_restaurant_menu(opt["name"], destination)
            if dishes:
                for d in dishes:
                    d["category"] = d.get("category") or _classify_dish_category(d["name"])
                    d["price"] = d.get("price", opt.get("price", 30) * 0.6)
                dish_map[opt["name"]] = dishes
                print(f"[food_agent] scraped {len(dishes)} dishes for {opt['name']}")

    # ---- Step 4: Validate against cuisine preferences ----
    matched = [o for o in enriched_options if matches_cuisine_preferences(o, cuisine_tags)] if cuisine_tags else []
    eligible = matched or enriched_options
    # With only one or two selected cuisines, an exclusively-matched pool makes
    # every single meal that cuisine and the whole trip report reads as a food
    # tour. Blend in a few local options so the planner has variety material;
    # preference order still leads via the prompt.
    if matched and len(cuisine_tags) < 3:
        local_extras = [o for o in enriched_options if o not in matched][:6]
        eligible = matched + local_extras
    used_preference_fallback = bool(cuisine_tags and not matched)
    if daily_food_cap is not None:
        affordable = [
            option for option in eligible
            if float(option.get("price", 0)) <= round(
                daily_food_cap * _SLOT_WEIGHTS.get(option.get("meal_type", "dinner"), 0.40),
                2,
            )
        ]
        if affordable:
            eligible = affordable

    # ---- Step 5: LLM meal planning ----
    result = llm_reason(
        "You are the Food Agent (Taste Editor). Build a meal plan from ONLY the supplied options. "
        "The traveler's selected_cuisines are ordered by preference; the first choice should lead, "
        "but do NOT make every meal the same cuisine — when only one or two cuisines are selected, "
        "include local/destination food for roughly one meal per day so the trip stays varied. "
        "Balance cost against the total trip budget, respect meal slots, and do not repeat a venue "
        "while unused eligible choices remain. Every venue must be in the exact destination. "
        "Return ONLY JSON: {meal_plan: [{date, meals: [{slot, option_id, dish_name, dish_category}]}], reasoning}.",
        {
            "destination": destination,
            "dates": trip_input["dates"],
            "num_days": len(days),
            "total_budget": trip_input["budget"],
            "food_budget_per_day": daily_food_cap,
            "hard_budget_rule": (
                "Breakfast, lunch, and dinner combined must not exceed food_budget_per_day."
                if daily_food_cap is not None else None
            ),
            "selected_cuisines": cuisine_tags,
            "taste_preferences": taste_prefs,
            "all_preferences": trip_input.get("preferences", {}),
            "eligible_options": eligible,
            "dish_map": {k: v for k, v in list(dish_map.items())[:10]},
        },
    )

    # ---- Step 6: Build daily meal plan ----
    # Slots per day
    buckets = {slot: [o for o in eligible if o["meal_type"] == slot] for slot in _SLOTS}
    for slot in _SLOTS:
        if not buckets[slot]:
            buckets[slot] = eligible
        if daily_food_cap is not None:
            slot_cap = round(daily_food_cap * _SLOT_WEIGHTS[slot], 2)
            affordable = [o for o in buckets[slot] if float(o.get("price", 0)) <= slot_cap]
            if affordable:
                buckets[slot] = affordable

    # Build picks from LLM result
    model_picks = {}
    if result and isinstance(result.get("meal_plan"), list):
        eligible_by_id = {o["id"]: o for o in eligible}
        for day_plan in result["meal_plan"]:
            if not isinstance(day_plan, dict):
                continue
            for meal in day_plan.get("meals", []):
                slot = meal.get("slot")
                option = eligible_by_id.get(meal.get("option_id"))
                if slot in _SLOTS and option:
                    model_picks[(day_plan.get("date", ""), slot)] = {
                        "option": option,
                        "dish_name": meal.get("dish_name", ""),
                        "dish_category": meal.get("dish_category", ""),
                    }

    daily_meals = []
    total = 0.0
    used_ids = set()
    meal_index = 0

    for day_idx, day in enumerate(days):
        meals = []
        for slot_idx, slot in enumerate(_SLOTS):
            pool = buckets[slot]

            # Get model pick or fallback
            pick = model_picks.get((day, slot))
            option = None
            dish_name = ""
            dish_category = ""

            if pick:
                option = pick["option"]
                dish_name = pick.get("dish_name", "")
                dish_category = pick.get("dish_category", "")

            if not option or option["id"] in used_ids:
                unused = [o for o in pool if o["id"] not in used_ids]
                if unused:
                    option = unused[meal_index % len(unused)]

            if option:
                used_ids.add(option["id"])

                # Get dish from scraped menu if available
                if not dish_name and option["name"] in dish_map:
                    menu_dishes = dish_map[option["name"]]
                    slot_dishes = [d for d in menu_dishes if _match_taste_profile(
                        d["name"], option.get("cuisine", ""), taste_prefs
                    )]
                    if slot_dishes:
                        best = max(slot_dishes, key=lambda d: d.get("popularity", 0))
                        dish_name = best["name"]
                        dish_category = best.get("category", "main")

                if not dish_name:
                    dish_name = f"{option.get('cuisine', '')} {slot}"
                    dish_category = _classify_dish_category(dish_name)

                price = option.get("price", 25)
                meals.append({
                    "slot": slot,
                    "name": dish_name,
                    "restaurant": option["name"],
                    "cuisine": option.get("cuisine", option.get("cuisine_family", "Local")),
                    "dish_category": dish_category,
                    "price": price,
                    "area": option.get("area", destination),
                    "source": option.get("source", "llm"),
                })
                total += price

            meal_index += 1

        daily_meals.append({"date": day, "meals": meals})

    # ---- Step 7: Store to shared database ----
    try:
        from booking.shared_db import save_meal
        for daily in daily_meals:
            for m in daily["meals"]:
                save_meal(
                    trip_id=trip_id,
                    date=daily["date"],
                    meal_slot=m["slot"],
                    restaurant_name=m["restaurant"],
                    restaurant_location=m.get("area", destination),
                    cuisine_type=m["cuisine"],
                    taste_profile=",".join(taste_prefs) if taste_prefs else "",
                    dish_name=m["name"],
                    dish_category=m.get("dish_category", ""),
                    dish_price=m["price"],
                    dish_popularity=7.0 if m.get("source") == "google_maps" else 5.0,
                    currency=currency,
                    status="confirmed",
                )
        print(f"[food_agent] saved {sum(len(d['meals']) for d in daily_meals)} meals to shared DB")
    except Exception as e:
        print(f"[food_agent] DB save failed (non-fatal): {e}")

    # ---- Build output ----
    chosen_cuisines = []
    for daily in daily_meals:
        for meal in daily["meals"]:
            if meal["cuisine"] not in chosen_cuisines:
                chosen_cuisines.append(meal["cuisine"])

    real_count = sum(1 for d in daily_meals for m in d["meals"] if m.get("source") == "google_maps")
    reasoning = (
        f"Planned {len(days)*3} meals across {len(days)} day(s) in {destination}. "
        f"{real_count} meals sourced from Google Maps, "
        f"{len(dish_map)} menus scraped for dish details. "
        f"Total food estimate: {total:.0f} {currency}. "
        f"Cuisines: {', '.join(chosen_cuisines[:5])}."
    ) if not used_preference_fallback else (
        f"No {', '.join(cuisine_tags)} options available from current data source; "
        f"used closest available restaurants."
    )

    return {
        "daily_meals": daily_meals,
        "cost": round(total, 2),
        "reasoning": reasoning,
        "destination": destination,
        "verification_required": True,
        "daily_budget_cap": daily_food_cap,
        "trip_id": trip_id,
    }
