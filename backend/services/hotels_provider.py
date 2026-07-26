"""Hotel data resolver — single entry point for the Housing Agent and the booking UI.

Resolution order:
    1. PRIMARY  — the configured hotel API system (Hotelbeds / Amadeus /
                  RapidAPI / Tongcheng / eLong), whichever has credentials set.
    2. FALLBACK — the Playwright Ctrip (携程) pipeline when an authenticated local
                  session exists: search_hotels reads listings and
                  pipeline.search_and_filter applies budget/preference filters.
    3. EMERGENCY — OpenStreetMap Overpass lodging POIs (no auth, no live price),
                  used only by the explicit comparison UI. Planning skips this
                  slow source because it cannot contribute a verified rate.

Every tier tags its results with `source` so the UI can show where data came from.
Offline demo records, when explicitly enabled, are tagged as mock data.

After search, Ctrip results are enriched with detail data (images, description,
lat/lng, room types, amenities) via the ctrip_detail scraper.
"""
from __future__ import annotations

from services.hotels_service import get_hotel_options
from booking.pipeline import search_and_filter
from booking.schemas import HotelSearchRequest
from booking import ctrip, osm
from booking.ctrip_detail import enrich_hotels_batch
from services.runtime_cache import cached_call


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
    return cached_call(
        "hotel-planning-search",
        (
            location,
            dates,
            max_price_per_night,
            min_rating,
            tuple(preferences or []),
        ),
        lambda: _resolve_hotels_uncached(
            location,
            dates,
            max_price_per_night,
            min_rating,
            preferences,
            budget,
        ),
        ttl_seconds=900,
        persist=True,
        source="hotel_provider_or_ctrip_playwright",
        snapshot=True,
    )


def _resolve_hotels_uncached(
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

        # Keep the planning path fast: detail pages, galleries, rooms and
        # amenities are loaded only from the explicit booking/search flow.
        return results
    except Exception as exc:
        print(f"[provider] Ctrip Playwright fallback failed ({exc}); -> OpenStreetMap.")

    # OpenStreetMap has no rate or availability. The planning agent only accepts
    # priced lodging, so querying several Overpass endpoints here would add a
    # long delay without changing its result. The explicit stay-comparison flow
    # below still uses OSM as a place-record fallback.
    return []


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
    """Return (raw_hotels, source_tag) from the first reachable source.

    Used by the streaming booking endpoint so it can emit a 'search' stage before
    the 'filtering' stage.

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

        source = (
            "mock"
            if hotels and all(hotel.get("source") == "mock" for hotel in hotels)
            else "ctrip"
        )
        return hotels, source
    except Exception as exc:
        print(f"[provider] Ctrip Playwright failed ({exc}); -> OpenStreetMap.")

    # 3) OpenStreetMap
    return osm.search_osm_hotels(location, max_price_per_night, min_rating, preferences), "openstreetmap"
