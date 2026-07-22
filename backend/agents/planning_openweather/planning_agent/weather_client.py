"""Thin OpenWeatherMap client: geocoding + forecast averaging + UV index.

A small in-memory TTL cache keeps the "real time" requirement from turning
into a rate-limit problem when the frontend polls a trip's plan repeatedly.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass
from typing import Optional

import requests

from . import config

_GEOCODE_PATH = "/geo/1.0/direct"
_FORECAST_PATH = "/data/2.5/forecast"
_CURRENT_PATH = "/data/2.5/weather"
_UVI_PATH = "/data/2.5/uvi"

_FORECAST_SLOTS_PER_DAY = 8  # OpenWeather 5-day/3-hour forecast granularity


@dataclass
class WeatherSnapshot:
    climate: str
    avg_weather: str
    avg_temp_c: float
    avg_humid_pct: float
    uv_index: Optional[float]


def _classify_climate(avg_temp_c: float, avg_humid_pct: float) -> str:
    if avg_temp_c < 0:
        return "polar / very cold"
    if avg_temp_c < 10:
        return "cold / continental"
    if avg_humid_pct >= 60 and avg_temp_c >= 20:
        return "tropical / humid"
    if avg_humid_pct < 30 and avg_temp_c >= 20:
        return "arid / dry"
    return "temperate"


class WeatherClient:
    def __init__(self, api_key: str = config.OPENWEATHER_API_KEY,
                 base_url: str = config.OPENWEATHER_BASE_URL,
                 cache_ttl_seconds: int = config.WEATHER_CACHE_TTL_SECONDS):
        self._api_key = api_key
        self._base_url = base_url
        self._ttl = cache_ttl_seconds
        self._cache: dict[tuple, tuple[float, dict]] = {}

    def _get(self, path: str, params: dict) -> dict:
        params = {**params, "appid": self._api_key}
        cache_key = (path, tuple(sorted(params.items())))
        now = time.time()
        cached = self._cache.get(cache_key)
        if cached and now - cached[0] < self._ttl:
            return cached[1]

        response = requests.get(f"{self._base_url}{path}", params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        self._cache[cache_key] = (now, data)
        return data

    def geocode(self, city: str, country: Optional[str] = None) -> tuple[float, float]:
        query = f"{city},{country}" if country else city
        results = self._get(_GEOCODE_PATH, {"q": query, "limit": 1})
        if not results:
            raise ValueError(f"OpenWeather geocoding found no match for '{query}'")
        return results[0]["lat"], results[0]["lon"]

    def get_forecast_snapshot(self, lat: float, lon: float, days: int = 1) -> WeatherSnapshot:
        """Average temp/humidity/condition over the trip window (max 5 days,
        OpenWeather's free-tier forecast horizon)."""
        data = self._get(_FORECAST_PATH, {"lat": lat, "lon": lon, "units": "metric"})
        slots = max(1, min(days, 5) * _FORECAST_SLOTS_PER_DAY)
        entries = data.get("list", [])[:slots]
        if not entries:
            return self.get_current_snapshot(lat, lon)

        temps = [e["main"]["temp"] for e in entries]
        humids = [e["main"]["humidity"] for e in entries]
        conditions = [e["weather"][0]["main"].lower() for e in entries]

        avg_temp = round(sum(temps) / len(temps), 1)
        avg_humid = round(sum(humids) / len(humids), 1)
        main_condition = Counter(conditions).most_common(1)[0][0]

        return WeatherSnapshot(
            climate=_classify_climate(avg_temp, avg_humid),
            avg_weather=main_condition,
            avg_temp_c=avg_temp,
            avg_humid_pct=avg_humid,
            uv_index=self.get_uv_index(lat, lon),
        )

    def get_current_snapshot(self, lat: float, lon: float) -> WeatherSnapshot:
        data = self._get(_CURRENT_PATH, {"lat": lat, "lon": lon, "units": "metric"})
        temp = round(data["main"]["temp"], 1)
        humid = round(data["main"]["humidity"], 1)
        condition = data["weather"][0]["main"].lower()
        return WeatherSnapshot(
            climate=_classify_climate(temp, humid),
            avg_weather=condition,
            avg_temp_c=temp,
            avg_humid_pct=humid,
            uv_index=self.get_uv_index(lat, lon),
        )

    def get_uv_index(self, lat: float, lon: float) -> Optional[float]:
        try:
            data = self._get(_UVI_PATH, {"lat": lat, "lon": lon})
            return data.get("value")
        except requests.HTTPError:
            # Some API plans/keys don't include the UVI endpoint — degrade gracefully;
            # callers fall back to inferring sun exposure from `avg_weather`.
            return None
        except requests.RequestException:
            return None

    def get_trip_weather(self, city: str, country: str, trip_duration_days: int) -> WeatherSnapshot:
        lat, lon = self.geocode(city, country)
        return self.get_forecast_snapshot(lat, lon, days=trip_duration_days)
