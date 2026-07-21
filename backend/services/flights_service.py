"""Flights data source.

MVP: reads backend/mocks/mock_flights.json.
TEAMMATE TODO: replace the body with a real API call (e.g. Amadeus, Skyscanner).
Must return the SAME shape so no agent code has to change:
    [{"id", "carrier", "price", "duration", "departure_time", "arrival_airport", "stops"}]
"""
from ._loader import load_mock


def get_flight_options(origin: str, destination: str, dates: dict) -> list[dict]:
    """Return a list of flight options from `origin` to `destination` for `dates`.

    Args:
        origin: departure city/airport, e.g. "New York".
        destination: arrival city, e.g. "Tokyo".
        dates: {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}.

    Returns:
        list of option dicts (see module docstring for the required keys).
    """
    data = load_mock("mock_flights.json")
    # MVP mock ignores origin/dates and returns the static Tokyo option set.
    # A real implementation would pass origin/destination/dates to the provider.
    return data["options"]
