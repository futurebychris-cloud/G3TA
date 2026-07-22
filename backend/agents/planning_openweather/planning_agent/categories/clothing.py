"""CLOTHING category: cultural/traditional suggestions + weather-driven garments."""

from __future__ import annotations

from ..culture import CultureAdvisor
from ..models import CategoryResult, ChecklistItem, UserProfile
from ..reference_data import HUMIDITY_ADDONS, TEMPERATURE_BANDS, WEATHER_CONDITION_ADDONS
from ..weather_client import WeatherSnapshot

_advisor = CultureAdvisor()


def _garments_for_temp(avg_temp_c: float) -> list[str]:
    for band in TEMPERATURE_BANDS:
        if avg_temp_c < band["max_c"]:
            return band["garments"]
    return TEMPERATURE_BANDS[-1]["garments"]


def _humidity_addons(avg_humid_pct: float) -> list[str]:
    addons: list[str] = []
    for _, (threshold, garments) in HUMIDITY_ADDONS.items():
        if _ == "high" and avg_humid_pct >= threshold:
            addons.extend(garments)
        if _ == "low" and avg_humid_pct <= threshold:
            addons.extend(garments)
    return addons


def _condition_addons(avg_weather: str) -> list[str]:
    for keyword, garments in WEATHER_CONDITION_ADDONS.items():
        if keyword in avg_weather:
            return garments
    return []


def build_clothing_category(user_profile: UserProfile, weather: WeatherSnapshot) -> CategoryResult:
    checklist: list[ChecklistItem] = []
    next_id = 0

    def add(name: str, note: str) -> None:
        nonlocal next_id
        checklist.append(ChecklistItem(id=f"clothing-{next_id}", name=name, note=note, checked=False))
        next_id += 1

    culture = _advisor.lookup(user_profile.destination_country)
    for wear in culture.traditional_wear:
        add(wear, "Traditional/local option — optional, based on local culture.")
    for norm in culture.fashion_norms:
        add(norm, "Local fashion norm for " + user_profile.destination_country + ".")
    for note in culture.modesty_notes:
        add(note, "Modesty/etiquette reminder.")

    weather_note = f"Based on {weather.avg_temp_c}°C avg / {weather.avg_humid_pct}% humidity, {weather.avg_weather} conditions."
    for garment in _garments_for_temp(weather.avg_temp_c):
        add(garment, weather_note)
    for garment in _humidity_addons(weather.avg_humid_pct):
        add(garment, weather_note)
    for garment in _condition_addons(weather.avg_weather):
        add(garment, weather_note)

    summary = f"Climate: {weather.climate}. {len(checklist)} clothing recommendation(s)."
    return CategoryResult(category="clothing", summary=summary, items=checklist)
