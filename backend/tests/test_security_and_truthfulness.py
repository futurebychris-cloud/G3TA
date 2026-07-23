import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
import orchestrator
from agents import activity_agent_v2, budget_agent_v2, planning_agent_v2
from booking import auto_book, ctrip
from booking.schemas import HotelSearchRequest
from booking import shared_db
from plan_runtime import finish_plan, register_plan
from security import cors_allowed_origins


TRIP = {
    "origin": "Hangzhou",
    "location": "Shanghai",
    "dates": {"start": "2026-08-01", "end": "2026-08-03"},
    "budget": {"total": 6000, "currency": "CNY"},
    "preferences": {},
    "request_id": "request-security-test",
}


class SecurityBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def test_cors_defaults_to_local_origins_and_rejects_implicit_wildcard(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIn("http://127.0.0.1:5173", cors_allowed_origins())
        with patch.dict(
            os.environ,
            {"CORS_ALLOWED_ORIGINS": "*", "ALLOW_INSECURE_CORS": "0"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "Wildcard CORS"):
                cors_allowed_origins()

    def test_sensitive_booking_endpoints_are_disabled_by_default(self):
        with patch.dict(os.environ, {"BOOKING_AUTOMATION_ENABLED": "0"}, clear=False):
            response = self.client.post(
                "/booking/mark_paid",
                json={"route_id": 1},
            )
        self.assertEqual(response.status_code, 503)
        self.assertIn("disabled", response.json()["detail"].lower())

    def test_legacy_auto_booking_is_honest_even_with_operator_token(self):
        with patch.dict(
            os.environ,
            {
                "BOOKING_AUTOMATION_ENABLED": "1",
                "BOOKING_API_TOKEN": "operator-secret",
            },
            clear=False,
        ):
            response = self.client.post(
                "/booking/auto/flight",
                headers={"X-G3TA-Booking-Token": "operator-secret"},
                json={
                    "origin": "Hangzhou",
                    "destination": "Shanghai",
                    "depart_date": "2026-08-01",
                },
            )
        self.assertEqual(response.status_code, 501)
        self.assertIn("comparison only", response.json()["detail"])

    def test_booking_module_cannot_bypass_disabled_server_boundary(self):
        with patch.dict(os.environ, {"BOOKING_AUTOMATION_ENABLED": "0"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "disabled"):
                auto_book.book_item(
                    "flight",
                    origin="Hangzhou",
                    destination="Shanghai",
                    date="2026-08-01",
                )

    def test_mock_mode_never_creates_a_simulated_order(self):
        selection = SimpleNamespace(id="hotel-1")
        with patch.object(ctrip, "ALLOW_MOCK", True), patch.object(
            ctrip,
            "_book_hotel_live",
            side_effect=RuntimeError("provider blocked"),
        ):
            with self.assertRaisesRegex(RuntimeError, "No simulated order"):
                ctrip.book_hotel(
                    selection,
                    {"id_number": "one-time", "name": "Traveler", "phone": "10086"},
                    {"check_in": "2026-08-01", "check_out": "2026-08-03"},
                    {"rooms": 1, "adults": 1, "children": 0},
                    "wechat",
                )

    def test_ctrip_skips_slow_browser_without_authenticated_session(self):
        request = HotelSearchRequest(
            location="Shanghai",
            check_in="2026-08-01",
            check_out="2026-08-03",
        )
        with patch.dict(os.environ, {"CTRIP_COOKIE": ""}, clear=False), \
                patch.object(ctrip, "_search_via_ctrip_api", return_value=None), \
                patch.object(ctrip, "_has_authenticated_ctrip_session", return_value=False), \
                patch.object(ctrip, "_stealth_browser") as browser:
            with self.assertRaisesRegex(RuntimeError, "skipping the slow login"):
                ctrip._search_hotels_live(request)
        browser.assert_not_called()

    def test_health_reports_configuration_without_returning_secret_values(self):
        with patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "never-return-me", "GAODE_KEY": "also-secret"},
            clear=False,
        ):
            response = self.client.get("/health")
        body = response.json()
        self.assertEqual(body["dependencies"]["deepseek"], "configured")
        self.assertEqual(body["dependencies"]["amap_web_service"], "configured")
        self.assertNotIn("never-return-me", response.text)
        self.assertNotIn("also-secret", response.text)


class PlanningLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def test_cancel_endpoint_targets_one_registered_request(self):
        event = register_plan("cancel-me")
        try:
            response = self.client.post("/plan/cancel/cancel-me")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(event.is_set())
        finally:
            finish_plan("cancel-me")

    def test_invalid_date_range_is_rejected_before_agents_run(self):
        response = self.client.post(
            "/plan",
            json={
                **TRIP,
                "dates": {"start": "2026-08-03", "end": "2026-08-01"},
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("End date", response.text)

    def test_finalize_existing_result_does_not_rerun_agents(self):
        existing = {
            "destination": "Shanghai",
            "reasoning_log": [],
            "cost": {"budget": 6000, "breakdown": {"food": 900}},
        }
        with patch.object(orchestrator, "plan") as full_plan:
            response = self.client.post(
                "/plan/finalize",
                json={
                    "trip": TRIP,
                    "existing_result": existing,
                    "adjusted_budget": {"food": 1200, "housing": 2500},
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(full_plan.called)
        self.assertEqual(response.json()["budget_targets"]["food"], 1200)
        self.assertIn("without rerunning", response.json()["reasoning_log"][-1]["note"])

    def test_provenance_keeps_live_and_estimated_sources_separate(self):
        summary = orchestrator.summarize_data_provenance({
            "transportation": {
                "options": [
                    {"source": "12306_live_real_price"},
                    {"source": "deepseek_estimate"},
                ],
            },
            "planning": {"weather_source": "open-meteo"},
        })
        self.assertEqual(summary["mode"], "mixed")
        self.assertIn("open-meteo", summary["live_sources"])
        self.assertIn("deepseek_estimate", summary["estimated_or_unverified_sources"])

    def test_provider_place_guard_rejects_a_different_city(self):
        with self.assertRaisesRegex(ValueError, "out-of-city"):
            orchestrator._selected_place_guard(
                "Food",
                "food.daily_meals[0].meals[0]",
                {
                    "source": "gaode_poi",
                    "lat": 39.9042,
                    "lng": 116.4074,
                    "area": "北京",
                },
                "Shanghai",
                "Hangzhou → Shanghai",
                include_name=False,
            )

    def test_fallback_schedule_uses_the_selected_transport_mode(self):
        outputs = {
            "activity": {"recommended": []},
            "food": {"daily_meals": []},
            "housing": {"recommended": None},
            "transportation": {
                "recommended": {
                    "mode": "car",
                    "carrier": "AMap driving route",
                    "from": "Hangzhou",
                },
            },
            "planning": {
                "daily_weather": [],
                "weather_summary": "weather unavailable",
            },
        }

        result = orchestrator._fallback_schedule(TRIP, outputs)

        first_item = result["schedule"][0]["items"][0]
        last_item = result["schedule"][-1]["items"][-1]
        self.assertIn("AMap driving route", first_item["title"])
        self.assertEqual(last_item["detail"], "Begin the return drive.")


class BudgetHistoryTruthfulnessTests(unittest.TestCase):
    def test_slow_optional_enrichment_is_disabled_by_default(self):
        with patch.dict(
            os.environ,
            {
                "BUDGET_PUBLIC_WEB_SEARCH_ENABLED": "0",
                "ACTIVITY_PUBLIC_WEB_SEARCH_ENABLED": "0",
                "PLANNING_LLM_PACKING_ENABLED": "0",
            },
            clear=False,
        ):
            self.assertFalse(budget_agent_v2._public_web_search_enabled())
            self.assertFalse(activity_agent_v2._public_discovery_enabled())
            self.assertFalse(planning_agent_v2._llm_packing_enabled())

    def test_history_uses_latest_prior_allocations_and_excludes_active_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "shared.db")
            with patch.object(shared_db, "DB_PATH", db_path):
                shared_db.init_shared_db()
                shared_db.add_expense(
                    "prior-1", "dining", "budget_food", "food allocation",
                    "2026-07-01", 100, "CNY",
                )
                shared_db.add_expense(
                    "prior-1", "dining", "budget_food", "food allocation",
                    "2026-07-01", 150, "CNY",
                )
                shared_db.add_expense(
                    "prior-2", "dining", "budget_food", "food allocation",
                    "2026-07-02", 250, "CNY",
                )
                shared_db.add_expense(
                    "active-trip", "dining", "budget_food", "food allocation",
                    "2026-07-03", 999, "CNY",
                )

                history = budget_agent_v2._get_prior_budget_history(
                    "active-trip",
                    num_trips=50,
                )

        self.assertEqual(history["history_kind"], "prior_budget_allocations")
        self.assertEqual(history["num_trips_found"], 2)
        self.assertEqual(history["count_food"], 2)
        self.assertEqual(history["avg_food"], 200)


if __name__ == "__main__":
    unittest.main()
