import sys
import types
import unittest
from unittest.mock import patch

# Keep this focused suite runnable before optional project dependencies are installed.
try:
    import openai  # noqa: F401
except ModuleNotFoundError:
    openai_stub = types.ModuleType("openai")
    openai_stub.OpenAI = object
    sys.modules["openai"] = openai_stub

from agents import planning_agent
import orchestrator
from services import weather_service
from llm.easy_reading import EASY_READING_INSTRUCTION, with_easy_reading


class WeatherServiceTests(unittest.TestCase):
    def test_live_forecast_is_geocoded_and_normalized(self):
        def fake_get_json(url, params):
            if url == weather_service.GEOCODING_URL:
                self.assertEqual(params["name"], "Shanghai")
                return {"results": [{
                    "name": "Shanghai",
                    "country": "China",
                    "country_code": "CN",
                    "latitude": 31.22222,
                    "longitude": 121.45806,
                    "timezone": "Asia/Shanghai",
                }]}
            self.assertEqual(params["forecast_days"], 16)
            self.assertIn("precipitation_probability_max", params["daily"])
            return {
                "timezone": "Asia/Shanghai",
                "daily": {
                    "time": ["2026-07-22", "2026-07-23"],
                    "weather_code": [0, 95],
                    "temperature_2m_max": [32.4, 29.1],
                    "temperature_2m_min": [25.2, 24.0],
                    "precipitation_probability_max": [10, 80],
                    "precipitation_sum": [0, 12.5],
                    "snowfall_sum": [0, 0],
                    "wind_speed_10m_max": [12, 38],
                    "uv_index_max": [8.2, 4.1],
                },
            }

        with patch.object(weather_service, "_get_json", side_effect=fake_get_json), \
                patch.object(weather_service, "generate_json") as seasonal:
            result = weather_service.get_weather(
                "Shanghai", {"start": "2026-07-22", "end": "2026-07-23"}
            )

        seasonal.assert_not_called()
        self.assertEqual(result["source"], "open_meteo_forecast")
        self.assertFalse(result["verification_required"])
        self.assertEqual(result["location"]["latitude"], 31.22222)
        self.assertEqual(result["daily"][0]["condition"], "Clear sky")
        self.assertEqual(result["daily"][1]["rain_chance"], 0.8)
        self.assertEqual(result["daily"][1]["wind_speed_max_kmh"], 38.0)

    def test_dates_outside_live_response_use_labeled_seasonal_estimates(self):
        location = {
            "name": "Paris, Île-de-France, France",
            "latitude": 48.85,
            "longitude": 2.35,
            "timezone": "Europe/Paris",
        }
        live = {
            "2026-07-22": {
                "date": "2026-07-22", "condition": "Mainly clear", "weather_code": 1,
                "high_c": 25.0, "low_c": 16.0, "rain_chance": 0.1,
                "precipitation_mm": 0.0, "snowfall_cm": 0.0,
                "wind_speed_max_kmh": 10.0, "uv_index_max": 6.0,
                "source": "open_meteo_forecast",
            }
        }
        seasonal = {
            "summary": "AI seasonal estimate for Paris.",
            "daily": [{
                "date": "2026-07-23", "condition": "Seasonal conditions — verify",
                "weather_code": None, "high_c": 20.0, "low_c": 12.0, "rain_chance": 0.3,
                "precipitation_mm": None, "snowfall_cm": None,
                "wind_speed_max_kmh": None, "uv_index_max": None,
                "source": "deepseek_seasonal_estimate",
            }],
        }
        with patch.object(weather_service, "geocode_destination", return_value=location), \
                patch.object(weather_service, "_forecast", return_value=(live, "Europe/Paris")), \
                patch.object(weather_service, "_seasonal_estimate", return_value=seasonal) as fallback:
            result = weather_service.get_weather(
                "Paris", {"start": "2026-07-22", "end": "2026-07-23"}
            )

        fallback.assert_called_once()
        self.assertEqual(fallback.call_args.args[2], ["2026-07-23"])
        self.assertEqual(result["source"], "mixed")
        self.assertTrue(result["verification_required"])
        self.assertIn("outside the live forecast", result["summary"])
        self.assertEqual(result["daily"][1]["source"], "deepseek_seasonal_estimate")

    def test_open_meteo_failure_retains_seasonal_fallback(self):
        with patch.object(weather_service, "geocode_destination", side_effect=OSError("offline")), \
                patch.object(weather_service, "generate_json", return_value=None):
            result = weather_service.get_weather(
                "Reykjavik", {"start": "2026-12-01", "end": "2026-12-02"}
            )

        self.assertEqual(result["source"], "deepseek_seasonal_estimate")
        self.assertTrue(result["verification_required"])
        self.assertEqual(len(result["daily"]), 2)
        self.assertIn("AI seasonal estimate", result["summary"])


class EasyReadingPromptTests(unittest.TestCase):
    def test_prompt_requires_every_factual_detail_to_be_preserved(self):
        prompt = with_easy_reading("Base prompt", True)
        self.assertIn("Preserve every date, time, price, location, warning, duration", prompt)
        self.assertIn("flight number", prompt)
        self.assertIn("Do not add facts", prompt)
        self.assertTrue(prompt.endswith(EASY_READING_INSTRUCTION))

    def test_prompt_is_unchanged_when_easy_reading_is_disabled(self):
        self.assertEqual(with_easy_reading("Base prompt", False), "Base prompt")


class PlanningWeatherTests(unittest.TestCase):
    def test_weather_essentials_are_kept_even_with_llm_packing(self):
        weather = {
            "summary": "Open-Meteo forecast for Montreal.",
            "source": "open_meteo_forecast",
            "location": {"name": "Montreal, Quebec, Canada"},
            "verification_required": False,
            "daily": [{
                "date": "2026-07-22", "condition": "Snow", "high_c": 28.0, "low_c": -2.0,
                "rain_chance": 0.7, "snowfall_cm": 2.0, "precipitation_mm": 5.0,
                "wind_speed_max_kmh": 42.0, "uv_index_max": 8.0,
                "source": "open_meteo_forecast",
            }],
        }
        trip = {
            "location": "Montreal", "dates": {"start": "2026-07-22", "end": "2026-07-22"},
            "preferences": {"activity_style": ["adventure"]},
        }
        with patch.object(planning_agent, "get_weather", return_value=weather), \
                patch.object(planning_agent, "llm_reason", return_value={
                    "packing_list": ["Camera"], "pacing_notes": "Keep the day flexible."
                }):
            result = planning_agent.run(trip)

        self.assertEqual(result["packing_list"][0], "Camera")
        for item in (
            "Compact umbrella", "Thermal base layers", "Insulated waterproof boots",
            "Windproof outer layer", "Broad-spectrum sunscreen",
        ):
            self.assertIn(item, result["packing_list"])
        self.assertIn("2026-07-22", result["pacing_notes"])
        self.assertEqual(result["weather_source"], "open_meteo_forecast")

    def test_outdoor_activity_is_moved_to_clearest_day(self):
        days = ["2026-07-22", "2026-07-23"]
        outdoor = {"name": "Riverfront bike ride", "style": "adventure", "tags": ["cycling"]}
        indoor = {"name": "City art museum", "style": "cultural", "tags": ["museum"]}
        weather = [
            {"date": days[0], "condition": "Heavy rain", "high_c": 24.0, "low_c": 18.0,
             "rain_chance": 0.9, "precipitation_mm": 20.0, "wind_speed_max_kmh": 30.0,
             "source": "open_meteo_forecast"},
            {"date": days[1], "condition": "Clear sky", "high_c": 26.0, "low_c": 17.0,
             "rain_chance": 0.05, "precipitation_mm": 0.0, "wind_speed_max_kmh": 8.0,
             "source": "open_meteo_forecast"},
        ]
        synth = {"schedule": [
            {"date": days[0], "items": [{"time": "10:00", "type": "activity",
                                           "title": outdoor["name"], "detail": "Bike outside."}]},
            {"date": days[1], "items": [{"time": "10:00", "type": "activity",
                                           "title": indoor["name"], "detail": "See exhibits."}]},
        ]}
        outputs = {
            "activity": {"recommended": [outdoor, indoor]},
            "planning": {"daily_weather": weather},
        }
        trip = {"dates": {"start": days[0], "end": days[1]}}

        orchestrator._apply_weather_activity_order(synth, trip, outputs)

        activity_by_date = {
            day["date"]: next(item for item in day["items"] if item["type"] == "activity")
            for day in synth["schedule"]
        }
        self.assertEqual(activity_by_date[days[0]]["title"], indoor["name"])
        self.assertEqual(activity_by_date[days[1]]["title"], outdoor["name"])
        self.assertIn("Weather (forecast): Clear sky", activity_by_date[days[1]]["detail"])


if __name__ == "__main__":
    unittest.main()
