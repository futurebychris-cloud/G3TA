"""Hotel data resolver — single entry point for the Housing Agent and the booking UI.

Resolution order:
    1. PRIMARY  — the multi-provider real hotel API system (Hotelbeds / Amadeus /
                  RapidAPI / Tongcheng / eLong), whichever has credentials set.
    2. FALLBACK — the Playwright Ctrip (携程) pipeline: search_hotels scrapes Ctrip
                  live and pipeline.search_and_filter applies the budget/preference
                  filters. Ctrip only resolves Chinese (domestic) cities, so this
                  tier is skipped entirely for international destinations.
    3. EMERGENCY — OpenStreetMap Overpass real lodging POIs (no auth, real names,
                  but no live price — Overpass carries no rate data at all).
    4. LAST RESORT — every tier above returned no *priced* option (typically an
                  international city with no API keys configured). Rather than
                  leave the traveler with no lodging recommendation, ask DeepSeek
                  to estimate a per-night price for the real OSM hotel names from
                  tier 3, clearly tagged as an AI estimate requiring verification —
                  same "labeled estimate when live data is unavailable" contract
                  the other five agents already follow (see README).

Every tier tags its results with `source` so the UI can show where data came from.

After search, Ctrip results are enriched with detail data (images, description,
lat/lng, room types, amenities) via the ctrip_detail scraper.
"""
from __future__ import annotations

from services.hotels_service import get_hotel_options
from services._ai import ESTIMATE_NOTE, generate_json, number, text
from booking.pipeline import search_and_filter, filter_results
from booking.schemas import HotelSearchRequest
from booking import ctrip, osm
from booking.ctrip_detail import enrich_hotels_batch

_PRICE_ESTIMATE_PROMPT = (
    "You are a hotel-pricing assistant for a trip planner. Every real hotel-rate source "
    "(provider APIs, Ctrip) was unavailable for this destination — likely because it is "
    "outside Ctrip's domestic-China coverage and no other provider key is configured. "
    "You are given a short list of REAL, currently-operating hotels/lodging (name, star "
    "rating, area) discovered via OpenStreetMap; they have no price attached. "
    "For EACH hotel in `hotels`, estimate a realistic price per night in the given currency "
    "based on its star rating, area, and the destination's typical lodging cost. "
    "Do not invent hotels — only estimate a price for each hotel exactly as given. "
    "Return ONLY JSON: {estimates: [{id, price_per_night}]}."
)


def _estimate_osm_prices(
    osm_options: list[dict],
    destination: str,
    currency: str = "USD",
) -> list[dict]:
    """Fill in a clearly-labeled DeepSeek price estimate for real OSM hotel names.

    Never invents a hotel — only adds a price to the real names OSM already found.
    Returns the same list with `price_per_night` filled in where an estimate was
    produced; entries the model skips keep `price_per_night = None`.
    """
    candidates = osm_options[:8]
    result = generate_json(_PRICE_ESTIMATE_PROMPT, {
        "destination": destination,
        "currency": currency,
        "hotels": [
            {"id": h["id"], "name": h["name"], "rating": h.get("rating"), "area": h.get("area")}
            for h in candidates
        ],
    }, temperature=0.4)

    estimates = {}
    for row in (result or {}).get("estimates", []) if result else []:
        if not isinstance(row, dict):
            continue
        price = number(row.get("price_per_night"), 0)
        if price > 0:
            estimates[row.get("id")] = price

    enriched = []
    for h in osm_options:
        if h["id"] in estimates:
            h = {
                **h,
                "price_per_night": estimates[h["id"]],
                "currency": text(h.get("currency"), currency),
                "source": "openstreetmap+deepseek_estimate",
                "verification_required": True,
                "estimate_note": ESTIMATE_NOTE,
            }
        enriched.append(h)
    return enriched


def _normalize_api(opts: list[dict]) -> list[dict]:
    for o in opts:
        o.setdefault("source", "api")
        o.setdefault("currency", "CNY")
        o.setdefault("url", "")
        o.setdefault("tags", [])
    return opts


def resolve_hotels(
    location: str,
    dates: dict,
    max_price_per_night: float | None = None,
    min_rating: float | None = None,
    preferences: list[str] | None = None,
    budget: dict | None = None,
) -> list[dict]:
    # 1) PRIMARY: real hotel API system.
    try:
        opts = get_hotel_options(location, dates, max_price_per_night, budget, preferences)
        if opts:
            return _normalize_api(opts)
    except Exception as exc:
        print(f"[provider] primary API unavailable ({exc}); -> Ctrip fallback.")

    # 2) FALLBACK (user-specified): Playwright Ctrip pipeline.
    try:
        req = HotelSearchRequest(
            location=location,
            check_in=dates["start"],
            check_out=dates["end"],
            max_price_per_night=max_price_per_night,
            min_rating=min_rating,
            preferences=preferences or [],
        )
        results = [h.model_dump() for h in search_and_filter(req)]

        # Enrich with detail data
        try:
            check_in = dates.get("start", "")
            check_out = dates.get("end", "")
            nights = _nights_between(check_in, check_out)
            results = enrich_hotels_batch(results, check_in, check_out, nights, max_enrich=3)
        except Exception as exc:
            print(f"[provider] detail enrichment failed (non-fatal): {exc}")

        return results
    except Exception as exc:
        print(f"[provider] Ctrip Playwright fallback failed ({exc}); -> OpenStreetMap.")

    # 3) EMERGENCY: real OpenStreetMap lodging (no price, clearly labeled).
    osm_options = osm.search_osm_hotels(location, max_price_per_night, min_rating, preferences)
    if any(o.get("price_per_night") for o in osm_options):
        return osm_options

    # 4) LAST RESORT: real hotel names, but no tier above could price them (typically
    # an international destination outside Ctrip's domestic coverage, with no other
    # provider key configured). Ask DeepSeek to estimate — never invent — a price for
    # each real name, clearly tagged so the UI/agent can flag it for verification.
    currency = (budget or {}).get("currency", "USD")
    try:
        enriched = _estimate_osm_prices(osm_options, location, currency)
        if any(o.get("price_per_night") for o in enriched):
            return enriched
    except Exception as exc:
        print(f"[provider] DeepSeek price-estimate fallback failed ({exc}); returning unpriced OSM list.")
    return osm_options


def _nights_between(start: str, end: str) -> int:
    """Calculate number of nights between two date strings YYYY-MM-DD."""
    from datetime import date as _date
    try:
        d0 = _date.fromisoformat(start)
        d1 = _date.fromisoformat(end)
        return max(1, (d1 - d0).days)
    except Exception:
        return 1


def raw_search(
    location: str,
    dates: dict,
    max_price_per_night: float | None = None,
    min_rating: float | None = None,
    preferences: list[str] | None = None,
) -> tuple[list[dict], str]:
    """Return (raw_hotels, source_tag) from the first reachable real source.

    Used by the streaming booking endpoint so it can emit a 'search' stage before
    the 'filtering' stage. Raises only if every real source is unreachable.

    For Ctrip results, hotel detail data (images, description, lat/lng, rooms,
    amenities) is enriched via the ctrip_detail scraper.
    """
    check_in = dates.get("start", "")
    check_out = dates.get("end", "")
    nights = _nights_between(check_in, check_out)

    # 1) PRIMARY API
    try:
        opts = get_hotel_options(location, dates, max_price_per_night, None, preferences)
        if opts:
            return _normalize_api(opts), "api"
    except Exception as exc:
        print(f"[provider] primary API unavailable ({exc}); -> Ctrip.")

    # 2) Playwright Ctrip (returns unfiltered raw cards)
    try:
        req = HotelSearchRequest(
            location=location,
            check_in=check_in,
            check_out=check_out,
            max_price_per_night=max_price_per_night,
            min_rating=min_rating,
            preferences=preferences or [],
        )
        hotels = ctrip.search_hotels(req)

        # Enrich Ctrip results with detail data
        try:
            hotels = enrich_hotels_batch(hotels, check_in, check_out, nights, max_enrich=3)
        except Exception as exc:
            print(f"[provider] detail enrichment failed (non-fatal): {exc}")

        return hotels, "ctrip"
    except Exception as exc:
        print(f"[provider] Ctrip Playwright failed ({exc}); -> OpenStreetMap.")

    # 3) OpenStreetMap
    return osm.search_osm_hotels(location, max_price_per_night, min_rating, preferences), "openstreetmap"
