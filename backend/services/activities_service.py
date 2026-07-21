"""Activities data source.

MVP: reads backend/mocks/mock_activities.json.
TEAMMATE TODO: replace with a real API call (e.g. GetYourGuide, Viator).
Must return the SAME shape:
    [{"id", "name", "style", "price", "duration", "area", "lat", "lng", "tags"}]
"""
from ._loader import load_mock


def get_activity_options(destination: str, activity_styles: list[str] | None = None) -> list[dict]:
    """Return activity options in `destination`.

    If `activity_styles` is provided, matching activities are returned first, but
    the full set is always returned so the agent has enough to fill the trip.
    """
    data = load_mock("mock_activities.json")
    options = data["options"]
    if not activity_styles:
        return options
    wanted = {s.lower() for s in activity_styles}
    preferred = [o for o in options if o["style"].lower() in wanted]
    rest = [o for o in options if o["style"].lower() not in wanted]
    return preferred + rest
