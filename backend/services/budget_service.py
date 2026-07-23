"""Budget references — primary Numbeo page data, then labeled static estimates.

Includes shopping budget as an additional category.

Usage:
    get_cost_index(destination, origin, dates, currency)
    → {currency, cost_level, daily_index: {food, activity, housing, local_transport, shopping},
       flight_reference, reasoning, source, verification_required}
"""
from services.numbeo_service import get_cost_index as numbeo_get_cost_index
from services.neural_budget import neural_budget_allocation


def get_cost_index(
    destination: str,
    origin: str = "",
    dates: dict | None = None,
    currency: str = "USD",
) -> dict:
    """Get a Numbeo-derived or clearly labeled estimated destination cost index.

    Returns shopping budget as an additional daily category.
    """
    dates = dates or {}
    start = dates.get("start", "")
    end = dates.get("end", "")

    # Primary: current Numbeo page data; the service labels static fallbacks.
    result = numbeo_get_cost_index(destination, origin, dates, currency)

    # Ensure shopping is included in daily_index
    daily = result.get("daily_index", {})
    if "shopping" not in daily:
        daily["shopping"] = round(daily.get("food", 55) * 0.3, 2)

    result["daily_index"] = daily
    result["source"] = result.get("source", "numbeo_database")
    result["verification_required"] = not result.get("source", "").startswith("numbeo_scraped")

    return result
