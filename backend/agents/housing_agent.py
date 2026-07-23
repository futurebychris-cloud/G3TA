"""Housing Agent.

Responsibility (PRD §7): recommend lodging within budget, near the planned activity zone.
Data source: configured hotel providers, then an authenticated local Ctrip
listing session. No lodging price is invented when providers are unavailable.
Output shape: {"options": [...], "recommended": {...}, "cost": number} (+ reasoning, nights).

Note: this agent recommends its *preferred* lodging. Whole-trip budget reconciliation
(and any forced downgrade) happens in the Orchestrator, which is where the auditable
"first pick rejected because it broke the budget cap" trade-off is recorded.
"""
from services.hotels_provider import resolve_hotels

from .base import report_progress, trip_days

SYSTEM_PROMPT = (
    "You are the Housing Agent in a multi-agent trip planner. From the given lodging options, "
    "pick the best single place to stay for the whole trip, weighing rating, provider price per "
    "night, area convenience, source confidence, and how it matches the "
    "traveler's activity style. "
    "Every option is for the exact supplied destination; never choose or mention another city. "
    "Use provider prices as-is and never invent availability. "
    "Return ONLY a JSON object with keys: recommended_id (the id of your pick) and reasoning "
    "(one sentence)."
)


def run(trip_input: dict) -> dict:
    nights = max(len(trip_days(trip_input)) - 1, 1)
    prefs = (trip_input.get("preferences", {}) or {})
    pref_list = prefs.get("bites", []) if isinstance(prefs, dict) else list(prefs)
    raw_nightly_cap = trip_input.get("_budget_caps", {}).get("housing")
    try:
        nightly_cap = max(float(raw_nightly_cap), 0) if raw_nightly_cap is not None else None
    except (TypeError, ValueError):
        nightly_cap = None
    report_progress(trip_input, "正在查询住宿价格与位置")
    raw_options = resolve_hotels(
        trip_input["location"],
        trip_input["dates"],
        max_price_per_night=nightly_cap,
        min_rating=None,
        preferences=pref_list,
        budget=trip_input.get("budget", {}),
    )

    # Provider prices only — never fabricate an estimated price.
    # A price counts as usable when it is a positive number below an absurd-cap sanity
    # bound (anything >= 100k CNY/night is treated as a scraping artifact / no price).
    _MAX_REALISTIC = 100000
    _city = trip_input["location"]

    real_options = [
        o for o in raw_options
        if o.get("price_per_night") is not None
        and 0 < float(o["price_per_night"]) < _MAX_REALISTIC
    ]

    if not real_options:
        # No real-time price could be scraped. Be honest: do NOT invent a number.
        return {
            "options": [],
            "recommended": None,
            "nights": nights,
            "cost": None,
            "reasoning": None,
            "destination": _city,
            "verification_required": True,
            "price_note": (
                "未能获取携程实时房价，预算中不包含住宿费用。"
                "请到携程平台核实真实价格后再预订（本结果不含任何估算价格）。"
            ),
        }

    options = real_options

    report_progress(trip_input, "正在按价格、评分和预算筛选住宿")

    # Selection is deterministic because all relevant facts are already
    # structured. The final orchestrator still explains cross-domain trade-offs.
    def _score(o):
        price = o.get("price_per_night") or 0
        rating = o.get("rating") or 0
        within_cap = nightly_cap is None or price <= nightly_cap
        return (1 if within_cap else 0, rating / max(price, 1), rating)

    recommended = max(options, key=_score)
    reasoning = "Best provider-priced rating-for-price option within the housing cap."

    price = recommended.get("price_per_night")
    cost = (price * nights) if price is not None else None

    return {
        "options": options,
        "recommended": recommended,
        "nights": nights,
        "cost": cost,
        "reasoning": reasoning,
        "destination": trip_input["location"],
        "verification_required": False,
        "price_note": None if price is not None else "实时房价缺失，请到携程核实。",
    }
