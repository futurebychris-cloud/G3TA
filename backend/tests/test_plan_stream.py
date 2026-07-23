import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main


class PlanStreamTests(unittest.TestCase):
    def test_budget_guidance_reaches_remaining_agents_before_completion(self):
        calls = []

        def run_agent(name, trip_input):
            calls.append((name, trip_input.get("_budget_caps")))
            if name == "budget":
                return {
                    "destination": "美国",
                    "allocations": {
                        "transportation": 1000,
                        "housing": 700,
                        "food": 300,
                        "activities": 250,
                    },
                }
            return {"destination": "美国", "agent": name}

        def guide(trip_input, _budget_output):
            return {**trip_input, "_budget_caps": {"transportation": 1000}}

        complete_result = {"destination": "美国", "summary": "Ready"}
        with patch.object(main.orchestrator, "run_single_agent", side_effect=run_agent), \
                patch.object(main.orchestrator, "with_budget_guidance", side_effect=guide), \
                patch.object(
                    main.orchestrator,
                    "reconcile_and_synthesize",
                    return_value=complete_result,
                ):
            response = TestClient(main.app).post("/plan/stream", json={
                "origin": "杭州",
                "location": "美国",
                "dates": {"start": "2026-08-01", "end": "2026-08-04"},
                "budget": {"total": 2500, "currency": "USD"},
                "preferences": {
                    "bites": [],
                    "transportation_type": ["flight"],
                    "activity_style": ["cultural"],
                },
            })

        self.assertEqual(response.status_code, 200)
        payloads = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        self.assertFalse(any(payload.get("type") == "error" for payload in payloads))
        self.assertEqual(payloads[-1], {"type": "complete", "result": complete_result})
        self.assertEqual(calls[0], ("budget", None))
        self.assertTrue(all(caps == {"transportation": 1000} for _, caps in calls[1:]))


if __name__ == "__main__":
    unittest.main()
