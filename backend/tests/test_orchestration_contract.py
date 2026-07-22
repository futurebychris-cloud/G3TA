import asyncio
import threading
import unittest
from unittest.mock import patch

import orchestrator


TRIP = {
    "location": "Shanghai",
    "origin": "New York",
    "dates": {"start": "2026-08-22", "end": "2026-08-25"},
    "budget": {"total": 2500, "currency": "USD"},
    "preferences": {},
}


class OrchestrationContractTests(unittest.TestCase):
    def test_japanese_cuisine_does_not_trigger_tokyo_geography_guard(self):
        trip = {**TRIP, "location": "Milan, Italy"}
        outputs = {
            "food": {
                "destination": "Milan, Italy",
                "reasoning": "The traveler requested Japanese cuisine.",
                "daily_meals": [{
                    "meals": [{
                        "name": "Tokyo Sushi Milano",
                        "cuisine": "Japanese",
                        "area": "Brera, Milan",
                    }],
                }],
            },
            "activity": {
                "destination": "Milan, Italy",
                "recommended": [{"name": "Duomo", "location": "Milan, Italy"}],
            },
        }

        orchestrator._validate_agent_geography(trip, outputs)

    def test_actual_tokyo_location_is_still_rejected_for_milan(self):
        trip = {**TRIP, "location": "Milan, Italy"}
        outputs = {
            "activity": {
                "destination": "Milan, Italy",
                "recommended": [{"name": "Demo attraction", "location": "Tokyo, Japan"}],
            },
        }

        with self.assertRaisesRegex(ValueError, "stale Tokyo/Japan data"):
            orchestrator._validate_agent_geography(trip, outputs)

    def test_budget_guidance_is_attached_without_mutating_public_input(self):
        guided = orchestrator.with_budget_guidance(
            TRIP,
            {"daily_caps": {"food": 40, "housing": 120}},
        )

        self.assertNotIn("_budget_caps", TRIP)
        self.assertEqual(guided["_budget_caps"], {"food": 40, "housing": 120})

    def test_plan_runs_budget_first_and_guides_every_other_agent(self):
        calls = []
        lock = threading.Lock()

        def run_agent(name, trip_input):
            with lock:
                calls.append((name, trip_input))
            if name == "budget":
                return {"daily_caps": {"food": 35, "housing": 110}}
            return {"destination": trip_input["location"]}

        prepared = {**TRIP, "trip_id": "stable-trip-id"}
        with patch.object(orchestrator, "prepare_trip_input", return_value=prepared), \
                patch.object(orchestrator, "run_single_agent", side_effect=run_agent), \
                patch.object(orchestrator, "reconcile_and_synthesize", return_value={"schedule": []}):
            result = orchestrator.plan(TRIP)

        self.assertEqual(calls[0][0], "budget")
        remaining = calls[1:]
        self.assertEqual({name for name, _ in remaining}, set(orchestrator._AGENTS) - {"budget"})
        for _, agent_input in remaining:
            self.assertEqual(agent_input["_budget_caps"], {"food": 35, "housing": 110})
        self.assertEqual(result["trip_id"], "stable-trip-id")

    def test_streaming_endpoint_reaches_complete_after_budget_guidance(self):
        import main

        prepared = {**TRIP, "trip_id": "stream-trip-id"}

        def run_agent(name, _trip_input):
            if name == "budget":
                return {"daily_caps": {"food": 35}}
            return {"destination": TRIP["location"]}

        final_result = {
            "destination": TRIP["location"],
            "dates": TRIP["dates"],
            "schedule": [],
            "cost": {"currency": "USD", "total": 0, "within_budget": True},
        }
        with patch.object(main.orchestrator, "prepare_trip_input", return_value=prepared), \
                patch.object(main.orchestrator, "run_single_agent", side_effect=run_agent), \
                patch.object(main.orchestrator, "reconcile_and_synthesize", return_value=final_result):
            response = main.plan_stream(main.TripInput(**TRIP))

            async def collect_body():
                chunks = []
                async for chunk in response.body_iterator:
                    chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
                return "".join(chunks)

            body = asyncio.run(collect_body())

        self.assertIn('"type": "complete"', body)
        self.assertIn('"trip_id": "stream-trip-id"', body)


if __name__ == "__main__":
    unittest.main()
