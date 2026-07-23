import unittest
from datetime import date
from unittest.mock import patch

import intake


class IntakeTests(unittest.TestCase):
    def test_normalizes_a_reviewable_draft_without_inventing_missing_values(self):
        result = intake.normalize_intake({
            "origin": "New York",
            "location": "Tokyo",
            "start_date": "2026-10-10",
            "end_date": "2026-10-14",
            "budget_total": "4000",
            "currency": "usd",
            "num_people": 2,
            "cuisines": ["Japanese", "Japanese"],
            "transportation": ["flight", "spaceship"],
            "activity_styles": ["cultural", "nightlife"],
            "must_go_sites": ["Senso-ji"],
            "time_constraints": ["quiet hotel", "step-free access"],
            "uncertain_fields": ["budget_total", "not_a_field"],
            "confirmation": "A five-day Tokyo trip for two.",
        })

        self.assertEqual(result["draft"]["budget"], {"total": 4000.0, "currency": "USD"})
        self.assertEqual(result["draft"]["preferences"]["transportation_type"], ["flight"])
        self.assertEqual(result["draft"]["preferences"]["activity_style"], ["cultural"])
        self.assertEqual(result["draft"]["preferences"]["bites"], ["Japanese"])
        self.assertEqual(result["draft"]["time_constraints"], "quiet hotel, step-free access")
        self.assertEqual(result["uncertain"], ["budget_total"])
        self.assertEqual(result["missing"], [])

    def test_invalid_or_reversed_dates_are_missing(self):
        result = intake.normalize_intake({
            "origin": "Paris",
            "location": "Lisbon",
            "start_date": "2026-08-20",
            "end_date": "2026-08-10",
            "budget_total": -1,
            "currency": "dollars",
        })
        self.assertIn("end_date", result["missing"])
        self.assertIn("budget_total", result["missing"])
        self.assertIn("currency", result["missing"])

    @patch.object(intake, "geocode_destination")
    def test_country_then_city_voice_answer_is_canonicalized(self, geocode):
        geocode.side_effect = lambda value: {
            "Milan": {"name": "Milan, Lombardy, Italy"},
            "Italy": {"name": "Italy"},
        }[value]

        result = intake.normalize_intake({"location": "Italy and Milan"})

        self.assertEqual(result["draft"]["location"], "Milan, Italy")

    @patch.object(intake, "chat_json")
    def test_parser_supplies_current_date_and_uses_low_temperature(self, chat_json):
        chat_json.return_value = {"location": "Kyoto"}
        result = intake.parse_intake("I want to travel to Kyoto next spring", date(2026, 7, 23))
        payload = chat_json.call_args.args[1]
        self.assertIn('"current_date": "2026-07-23"', payload)
        self.assertEqual(chat_json.call_args.kwargs["temperature"], 0.1)
        self.assertEqual(result["draft"]["location"], "Kyoto")
        self.assertIn("origin", result["missing"])

    @patch.object(intake, "chat_json")
    def test_chinese_voice_intake_requests_and_falls_back_to_a_chinese_confirmation(self, chat_json):
        chat_json.return_value = {
            "origin": "上海",
            "location": "北京",
            "start_date": "2026-10-10",
            "end_date": "2026-10-14",
            "budget_total": 8000,
            "currency": "CNY",
        }

        result = intake.parse_intake("我想从上海去北京旅行", language="zh-CN")
        payload = chat_json.call_args.args[1]

        self.assertIn('"preferred_response_language": "Chinese"', payload)
        self.assertEqual(result["summary"], "已创建旅行草案：从上海前往北京，日期为2026-10-10至2026-10-14，预算为CNY 8000。")


if __name__ == "__main__":
    unittest.main()
