"""Budget / cost-index data source.

MVP: reads backend/mocks/mock_budget_db.json (a static per-destination cost index).
TEAMMATE TODO: replace with a real cost-of-living API (e.g. Numbeo).
Must return the SAME shape:
    {"currency", "cost_level", "daily_index": {"food","activity","housing","local_transport"},
     "flight_reference"}
"""
from ._loader import load_mock


def get_cost_index(destination: str) -> dict:
    """Return the per-day cost index for `destination`, falling back to a default."""
    data = load_mock("mock_budget_db.json")
    destinations = data["destinations"]
    # Case-insensitive match on the destination's leading token (e.g. "Tokyo, Japan").
    key = destination.split(",")[0].strip()
    for name, entry in destinations.items():
        if name.lower() == key.lower():
            return entry
    return destinations["default"]
