"""PlanningAgent: aggregates activity/budget subagent outputs, user preferences,
and live weather into the 5 packing categories (items, clothing, supportive,
legal, devices) plus flight/travel restriction reminders.
"""

from __future__ import annotations

from .categories.clothing import build_clothing_category
from .categories.devices import build_devices_category
from .categories.items import build_items_category
from .categories.legal import build_legal_category
from .categories.supportive import build_supportive_category
from .models import BudgetSummary, CategoryResult, ChecklistItem, PackingSummary, PlanningRequest, PlanningResponse, WeatherSummary
from .reference_data import FLIGHT_INFO_NOTES
from .storage import save_plan
from .weather_client import WeatherClient


def _build_packing_list(categories: list[CategoryResult]) -> tuple[list[ChecklistItem], PackingSummary]:
    """Flatten the 5 category checklists into one master packing list, tagging
    each item with its source category so the frontend can still group/filter."""
    packing_list = [
        item.model_copy(update={"category": category.category})
        for category in categories
        for item in category.items
    ]
    checked = sum(1 for item in packing_list if item.checked)
    summary = PackingSummary(
        total_items=len(packing_list),
        checked_items=checked,
        remaining_items=len(packing_list) - checked,
    )
    return packing_list, summary


class PlanningAgent:
    def __init__(self, weather_client: WeatherClient | None = None):
        self._weather_client = weather_client or WeatherClient()

    def generate_plan(self, request: PlanningRequest, persist: bool = True) -> PlanningResponse:
        profile = request.user_profile

        weather = self._weather_client.get_trip_weather(
            city=profile.destination_city,
            country=profile.destination_country,
            trip_duration_days=profile.trip_duration_days,
        )

        items_category, spent = build_items_category(request.activity_output, request.budget_output, request.preference)
        clothing_category = build_clothing_category(profile, weather)
        supportive_category = build_supportive_category(profile, weather)
        legal_category = build_legal_category(profile)
        devices_category = build_devices_category(profile)

        total_available = request.budget_output.shopping_budget + request.budget_output.leftover
        budget_summary = BudgetSummary(
            shopping_budget=request.budget_output.shopping_budget,
            leftover=request.budget_output.leftover,
            total_available=total_available,
            total_allocated=spent,
            remaining=round(total_available - spent, 2),
        )

        categories = [items_category, clothing_category, supportive_category, legal_category, devices_category]
        packing_list, packing_summary = _build_packing_list(categories)

        response = PlanningResponse(
            trip_id=request.trip_id,
            weather=WeatherSummary(
                climate=weather.climate,
                avg_weather=weather.avg_weather,
                avg_temp_c=weather.avg_temp_c,
                avg_humid_pct=weather.avg_humid_pct,
                uv_index=weather.uv_index,
            ),
            budget_summary=budget_summary,
            categories=categories,
            packing_list=packing_list,
            packing_summary=packing_summary,
            flight_info=FLIGHT_INFO_NOTES,
        )

        if persist:
            save_plan(response)
        return response
