"""Hotel data resolver — single entry point for the Housing Agent and the booking UI.

Resolution order (all REAL data, never hardcoded):
    1. PRIMARY  — the multi-provider real hotel API system (Hotelbeds / Amadeus /
                  RapidAPI / Tongcheng / eLong), whichever has credentials set.
    2. FALLBACK — the Playwright Ctrip (携程) pipeline: search_hotels scrapes Ctrip
                  live and pipeline.search_and_filter applies the budget/preference
                  filters. This is the user-specified fallback.
    3. EMERGENCY — OpenStreetMap Overpass real lodging POIs (no auth, no price).
                  Used only when both the API and Ctrip are unreachable, so the UI
                  always shows genuine hotels instead of an error.

Every tier tags its results with `source` so the UI can show where data came from.
The strict no-mock contract is preserved: a missing tier raises and the next tier
is tried; only Overpass (real data) ends the chain.

After search, Ctrip results are enriched with detail data (images, description,
lat/lng, room types, amenities) via the ctrip_detail scraper.
"""
from __future__ import annotations

from services.hotels_service import get_hotel_options
from booking.pipeline import search_and_filter, filter_results
from booking.schemas import HotelSearchRequest
from booking import ctrip, osm
from booking.ctrip_detail import enrich_hotels_batch


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
    return osm.search_osm_hotels(location, max_price_per_night, min_rating, preferences)


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
