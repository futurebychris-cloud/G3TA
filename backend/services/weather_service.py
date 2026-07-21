"""Weather data source.

MVP: reads backend/mocks/mock_weather.json (a monthly climate template) and
expands it into a per-day forecast for the requested trip dates.
TEAMMATE TODO: replace with a real API call (e.g. OpenWeather, Tomorrow.io).
Must return the SAME shape:
    {"summary": str, "daily": [{"date", "condition", "high_c", "low_c", "rain_chance"}]}
"""
from datetime import date, timedelta

from ._loader import load_mock


def _parse(d: str) -> date:
    return date.fromisoformat(d)


def get_weather(destination: str, dates: dict) -> dict:
    """Return a per-day forecast for `destination` across the trip `dates`."""
    data = load_mock("mock_weather.json")
    monthly = data["monthly"]
    var = data.get("daily_variation_c", 2)

    start = _parse(dates["start"])
    end = _parse(dates["end"])
    if end < start:
        start, end = end, start

    daily = []
    cur = start
    i = 0
    while cur <= end:
        m = monthly[str(cur.month)]
        # Deterministic pseudo-variation so days differ without needing randomness.
        wobble = (i % 3) - 1  # -1, 0, +1 cycling
        daily.append({
            "date": cur.isoformat(),
            "condition": m["condition"],
            "high_c": m["high_c"] + wobble * (var // 2 or 1),
            "low_c": m["low_c"] + wobble,
            "rain_chance": m["rain_chance"],
        })
        cur += timedelta(days=1)
        i += 1

    conditions = {d["condition"] for d in daily}
    avg_high = round(sum(d["high_c"] for d in daily) / len(daily)) if daily else 0
    max_rain = max((d["rain_chance"] for d in daily), default=0)
    summary = (
        f"{destination}: {', '.join(sorted(conditions))}. "
        f"Avg high ~{avg_high}°C. "
        f"Rain likelihood up to {int(max_rain * 100)}% on some days."
    )
    return {"summary": summary, "daily": daily}
