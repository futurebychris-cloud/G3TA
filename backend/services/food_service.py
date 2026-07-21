"""Restaurant / food data source.

MVP: reads backend/mocks/mock_food.json.
TEAMMATE TODO: replace with a real API call (e.g. Google Places, Yelp).
Must return the SAME shape:
    [{"id", "name", "cuisine", "price", "meal_type", "area", "rating", "tags"}]
"""
from ._loader import load_mock


def get_food_options(destination: str, cuisine_tags: list[str] | None = None) -> list[dict]:
    """Return restaurant options in `destination`.

    If `cuisine_tags` is provided, options matching any tag (by cuisine or tag list)
    are returned first, but the full set is always returned so the agent can still
    cover every meal slot.
    """
    data = load_mock("mock_food.json")
    options = data["options"]
    if not cuisine_tags:
        return options
    wanted = {t.lower() for t in cuisine_tags}

    def matches(o: dict) -> bool:
        hay = {o["cuisine"].lower(), *[t.lower() for t in o.get("tags", [])]}
        return bool(hay & wanted)

    preferred = [o for o in options if matches(o)]
    rest = [o for o in options if not matches(o)]
    return preferred + rest
