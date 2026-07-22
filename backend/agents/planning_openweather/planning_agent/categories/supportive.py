"""SUPPORTIVE category:
  1a. weather-driven sickness/pest risk -> medicine & prep advice
  1b. UV/dryness -> sunscreen or lotion suggestions
  1c. hotel-amenity loop -> flag daily essentials the hotel doesn't provide
"""

from __future__ import annotations

from ..models import CategoryResult, ChecklistItem, UserProfile
from ..reference_data import DAILY_ESSENTIALS, GENERAL_SUPPORTIVE_ITEMS, SICKNESS_RISK_RULES
from ..weather_client import WeatherSnapshot


def _sickness_risk_items(weather: WeatherSnapshot, next_id_start: int) -> tuple[list[ChecklistItem], int]:
    items: list[ChecklistItem] = []
    next_id = next_id_start
    for rule in SICKNESS_RISK_RULES:
        if rule["condition"](weather.avg_temp_c, weather.avg_humid_pct, weather.avg_weather):
            for advice in rule["advice"]:
                items.append(ChecklistItem(
                    id=f"supportive-{next_id}", name=advice, checked=False,
                    note=f"Risk flagged: {rule['risk']}.",
                ))
                next_id += 1
    for advice in GENERAL_SUPPORTIVE_ITEMS:
        items.append(ChecklistItem(id=f"supportive-{next_id}", name=advice, checked=False, note="General precaution."))
        next_id += 1
    return items, next_id


def _sun_and_skin_items(weather: WeatherSnapshot, next_id_start: int) -> tuple[list[ChecklistItem], int]:
    items: list[ChecklistItem] = []
    next_id = next_id_start
    is_sunny = weather.avg_weather in ("clear",) or (weather.uv_index is not None and weather.uv_index >= 3)
    if is_sunny:
        uv_note = f"UV index ~{weather.uv_index}." if weather.uv_index is not None else "Clear/sunny conditions expected."
        for name in ["sunscreen (SPF 30+)", "sunglasses", "sun hat"]:
            items.append(ChecklistItem(id=f"supportive-{next_id}", name=name, checked=False, note=uv_note))
            next_id += 1
    if weather.avg_humid_pct < 30:
        items.append(ChecklistItem(
            id=f"supportive-{next_id}", name="body/face lotion", checked=False,
            note=f"Low humidity (~{weather.avg_humid_pct}%) can dry out skin.",
        ))
        next_id += 1
    return items, next_id


def _hotel_amenity_loop(user_profile: UserProfile, next_id_start: int) -> tuple[list[ChecklistItem], int]:
    provided = {a.strip().lower() for a in user_profile.hotel_amenities}
    items: list[ChecklistItem] = []
    next_id = next_id_start
    for essential in DAILY_ESSENTIALS:
        is_provided = any(essential.split(" / ")[0] in p or p in essential for p in provided)
        if is_provided:
            items.append(ChecklistItem(
                id=f"supportive-{next_id}", name=essential, checked=True,
                note="Provided by hotel — optional to bring your own.", status="provided_by_hotel",
            ))
        else:
            items.append(ChecklistItem(
                id=f"supportive-{next_id}", name=essential, checked=False,
                note="Not listed among hotel amenities — bring your own.", status="bring_your_own",
            ))
        next_id += 1
    return items, next_id


def build_supportive_category(user_profile: UserProfile, weather: WeatherSnapshot) -> CategoryResult:
    checklist: list[ChecklistItem] = []
    next_id = 0

    sickness_items, next_id = _sickness_risk_items(weather, next_id)
    checklist.extend(sickness_items)

    sun_items, next_id = _sun_and_skin_items(weather, next_id)
    checklist.extend(sun_items)

    amenity_items, next_id = _hotel_amenity_loop(user_profile, next_id)
    checklist.extend(amenity_items)

    missing = sum(1 for i in amenity_items if i.status == "bring_your_own")
    summary = f"{missing} daily essential(s) not provided by the hotel; {len(sickness_items) + len(sun_items)} health/weather advisories."
    return CategoryResult(category="supportive", summary=summary, items=checklist)
