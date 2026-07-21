"""Lodging data source.

MVP: reads backend/mocks/mock_hotels.json.
TEAMMATE TODO: replace with a real API call (e.g. Booking.com, Expedia).
Must return the SAME shape:
    [{"id", "name", "price_per_night", "rating", "area", "lat", "lng", "tags"}]
"""
from ._loader import load_mock


def get_hotel_options(destination: str, dates: dict, max_price_per_night: float | None = None) -> list[dict]:
    """Return lodging options in `destination`, optionally filtered by nightly price cap."""
    data = load_mock("mock_hotels.json")
    options = data["options"]
    if max_price_per_night is not None:
        options = [o for o in options if o["price_per_night"] <= max_price_per_night]
        # If the cap excludes everything, fall back to the cheapest so the agent
        # always has something to reason about (and to flag as over-budget).
        if not options:
            options = sorted(data["options"], key=lambda o: o["price_per_night"])[:1]
    return options
