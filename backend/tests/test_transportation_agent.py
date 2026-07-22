import unittest
from unittest.mock import patch

from agents import transportation_agent


TRIP = {
    "location": "Tokyo",
    "origin": "New York",
    "dates": {"start": "2026-04-10", "end": "2026-04-14"},
    "budget": {"total": 2500, "currency": "USD"},
    "preferences": {"transportation_type": ["flight"]},
}

OPTIONS = [
    {
        "id": "transport_direct",
        "carrier": "Estimate Air",
        "mode": "flight",
        "price": 700,
        "duration": "12h",
        "departure_time": "10:00",
        "departure_airport": "JFK",
        "departure_lat": 40.6413,
        "departure_lng": -73.7781,
        "arrival_airport": "NRT",
        "arrival_lat": 35.772,
        "arrival_lng": 140.3929,
        "coordinate_system": "GCJ-02",
        "stops": 0,
        "destination": "Tokyo",
        "source": "deepseek_estimate",
        "verification_required": True,
    },
    {
        "id": "transport_connect",
        "carrier": "Connection Air",
        "mode": "flight",
        "price": 620,
        "duration": "15h",
        "departure_time": "08:00",
        "departure_airport": "JFK",
        "departure_lat": 40.6413,
        "departure_lng": -73.7781,
        "arrival_airport": "HND",
        "arrival_lat": 35.5494,
        "arrival_lng": 139.7798,
        "coordinate_system": "GCJ-02",
        "stops": 1,
        "destination": "Tokyo",
        "source": "deepseek_estimate",
        "verification_required": True,
    },
]


class TransportationAgentTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(transportation_agent, "get_flight_options", return_value=OPTIONS)
        self.get_options = patcher.start()
        self.addCleanup(patcher.stop)

    @patch.object(transportation_agent, "llm_reason", return_value=None)
    def test_fallback_keeps_original_contract_and_adds_route_metadata(self, _reason):
        result = transportation_agent.run(TRIP)

        self.assertEqual(result["recommended"]["id"], "transport_direct")
        self.assertEqual(result["cost"], 700)
        self.assertIn("options", result)
        self.assertIn("reasoning", result)
        self.assertEqual([point["label"] for point in result["route_points"]], ["JFK", "NRT"])
        self.assertEqual(result["route_summary"]["origin"], "New York")
        self.assertEqual(result["route_summary"]["destination"], "Tokyo")
        self.assertEqual(result["destination"], "Tokyo")
        self.assertTrue(result["verification_required"])
        self.assertEqual(result["recommended"]["source"], "deepseek_estimate")
        self.get_options.assert_called_once_with(
            "New York", "Tokyo", TRIP["dates"], TRIP["budget"], ["flight"]
        )

    @patch.object(transportation_agent, "llm_reason", return_value={"recommended_id": "transport_connect", "reasoning": "Best estimate for this trip."})
    def test_valid_llm_choice_is_preserved(self, _reason):
        result = transportation_agent.run(TRIP)

        self.assertEqual(result["recommended"]["id"], "transport_connect")
        self.assertEqual(result["reasoning"], "Best estimate for this trip.")
        self.assertEqual(result["route_summary"]["arrival_airport"], "HND")

    @patch.object(transportation_agent, "llm_reason", return_value={"recommended_id": "unknown"})
    def test_missing_coordinates_and_unknown_choice_fall_back_safely(self, _reason):
        self.get_options.return_value = [{
            "id": "legacy",
            "carrier": "Legacy Air",
            "mode": "flight",
            "price": 500,
            "duration": "10h",
            "departure_time": "09:00",
            "arrival_airport": "NRT",
            "stops": 0,
        }]

        result = transportation_agent.run(TRIP)

        self.assertEqual(result["recommended"]["id"], "legacy")
        self.assertEqual(result["route_points"], [])
        self.assertEqual(result["cost"], 500)

    @patch.object(transportation_agent, "llm_reason", return_value=None)
    def test_invalid_provider_coordinates_never_reach_the_map(self, _reason):
        self.get_options.return_value = [{
            **OPTIONS[0],
            "departure_lat": float("nan"),
            "arrival_lat": 140,
        }]

        result = transportation_agent.run(TRIP)

        self.assertEqual(result["route_points"], [])

    @patch.object(transportation_agent, "llm_reason", return_value=None)
    def test_unlabeled_coordinate_system_never_reaches_amap(self, _reason):
        self.get_options.return_value = [{
            **OPTIONS[0],
            "coordinate_system": None,
        }]

        result = transportation_agent.run(TRIP)

        self.assertEqual(result["route_points"], [])

    @patch.object(transportation_agent, "llm_reason", return_value=None)
    def test_available_and_unsupported_requested_modes_are_reported(self, _reason):
        trip = {**TRIP, "preferences": {"transportation_type": ["train", "car"]}}
        self.get_options.return_value = [
            OPTIONS[0],
            {
                **OPTIONS[1],
                "id": "transport_train",
                "carrier": "Rail estimate",
                "mode": "train",
                "price": 400,
            },
        ]

        result = transportation_agent.run(trip)

        self.assertEqual(result["coverage"]["available_modes"], ["flight", "train"])
        self.assertNotIn("train", result["coverage"]["note"])
        self.assertIn("car", result["coverage"]["note"])


if __name__ == "__main__":
    unittest.main()
