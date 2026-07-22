"""Transportation Agent.

Responsibility (PRD §7): recommend flight/train/car option(s) within budget.
Data source: destination-aware AI transportation estimates.
Output shape keeps the original options/recommended/cost/reasoning contract and
adds route metadata that the frontend can draw without geocoding airport names.
"""
import math

from services.flights_service import get_flight_options

from .base import llm_reason

SYSTEM_PROMPT = (
    "You are the Transportation Agent in a multi-agent trip planner. From the given flight "
    "options, pick the single best one for the traveler, balancing price, duration, and number "
    "of stops against their total budget and preferences. "
    "Return ONLY a JSON object with keys: recommended_id (the id of your pick), and reasoning "
    "(one sentence on why). Choose an option that leaves room in the budget for lodging, food, "
    "and activities. The route MUST start at the supplied origin and end at the supplied exact "
    "destination; reject anything for another city or country. Treat schedules and prices as "
    "estimates requiring verification."
)


def _route_point(option: dict, prefix: str, label: str, role: str) -> dict | None:
    """Build one optional airport map point without making coordinates mandatory."""
    lat = option.get(f"{prefix}_lat")
    lng = option.get(f"{prefix}_lng")
    coordinate_system = str(option.get("coordinate_system") or "").casefold().replace("_", "-").replace(" ", "")
    if (
        coordinate_system not in {"gcj-02", "gcj02", "amap", "amap-compatible"}
        or
        isinstance(lat, bool)
        or isinstance(lng, bool)
        or not isinstance(lat, (int, float))
        or not isinstance(lng, (int, float))
        or not math.isfinite(lat)
        or not math.isfinite(lng)
        or not -90 <= lat <= 90
        or not -180 <= lng <= 180
    ):
        return None
    return {
        "label": label,
        "type": "transport",
        "role": role,
        "lat": lat,
        "lng": lng,
        "coordinate_system": "GCJ-02",
    }


def _route_metadata(origin: str, destination: str, recommended: dict) -> tuple[list[dict], dict]:
    departure_airport = recommended.get("departure_airport") or origin
    arrival_airport = recommended.get("arrival_airport") or destination
    points = [
        _route_point(recommended, "departure", departure_airport, "departure"),
        _route_point(recommended, "arrival", arrival_airport, "arrival"),
    ]
    return [point for point in points if point], {
        "mode": recommended.get("mode") or "flight",
        "origin": origin,
        "destination": destination,
        "departure_airport": departure_airport,
        "arrival_airport": arrival_airport,
        "carrier": recommended.get("carrier"),
        "departure_time": recommended.get("departure_time"),
        "duration": recommended.get("duration"),
        "stops": recommended.get("stops", 0),
    }


def run(trip_input: dict) -> dict:
    origin = trip_input.get("origin", "New York")
    destination = trip_input["location"]
    transport_types = trip_input.get("preferences", {}).get("transportation_type", [])
    options = get_flight_options(
        origin,
        destination,
        trip_input["dates"],
        trip_input.get("budget", {}),
        transport_types,
    )

    payload = {
        "origin": origin,
        "destination": destination,
        "total_budget": trip_input["budget"],
        "preferences": trip_input.get("preferences", {}),
        "dates": trip_input["dates"],
        "time_constraints": trip_input.get("time_constraints", ""),
        "options": options,
    }
    result = llm_reason(SYSTEM_PROMPT, payload)

    recommended = None
    reasoning = None
    if result and result.get("recommended_id"):
        recommended = next((o for o in options if o["id"] == result["recommended_id"]), None)
        reasoning = result.get("reasoning")
    if recommended is None:
        # Fallback: cheapest non-stop if available, else cheapest overall.
        nonstop = [o for o in options if o.get("stops", 0) == 0]
        pool = nonstop or options
        recommended = min(pool, key=lambda o: o["price"])
        reasoning = "Cheapest suitable option selected (LLM reasoning unavailable)."

    route_points, route_summary = _route_metadata(origin, destination, recommended)
    requested_modes = transport_types or ["flight"]
    available_modes = list(dict.fromkeys(
        str(option.get("mode") or "flight").strip().lower()
        for option in options
        if str(option.get("mode") or "flight").strip()
    ))
    unsupported = [mode for mode in requested_modes if mode.lower() not in available_modes]

    return {
        "options": options,
        "recommended": recommended,
        "cost": recommended["price"],
        "reasoning": reasoning,
        "destination": destination,
        "verification_required": True,
        "route_points": route_points,
        "route_summary": route_summary,
        "coverage": {
            "requested_modes": requested_modes,
            "available_modes": available_modes,
            "note": (
                f"No generated option is currently available for: {', '.join(unsupported)}. Verify with a live provider."
                if unsupported else None
            ),
        },
    }
