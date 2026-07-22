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

    @patch.object(intake, "chat_json")
    def test_parser_supplies_current_date_and_uses_low_temperature(self, chat_json):
        chat_json.return_value = {"location": "Kyoto"}
        result = intake.parse_intake("I want to travel to Kyoto next spring", date(2026, 7, 23))
        payload = chat_json.call_args.args[1]
        self.assertIn('"current_date": "2026-07-23"', payload)
        self.assertEqual(chat_json.call_args.kwargs["temperature"], 0.1)
        self.assertEqual(result["draft"]["location"], "Kyoto")
        self.assertIn("origin", result["missing"])


if __name__ == "__main__":
    unittest.main()
