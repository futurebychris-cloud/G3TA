import unittest

import orchestrator


TRIP = {"location": "美国", "origin": "杭州"}


def _output(destination="美国", **extra):
    return {"destination": destination, **extra}


class OrchestratorGeographyTests(unittest.TestCase):
    def test_model_summary_must_name_the_requested_destination(self):
        self.assertIsNone(
            orchestrator._safe_model_summary("Shanghai", "A relaxed Tokyo weekend.")
        )
        self.assertEqual(
            orchestrator._safe_model_summary(
                "Shanghai",
                "A balanced five-day Shanghai trip with a flexible pace.",
            ),
            "A balanced five-day Shanghai trip with a flexible pace.",
        )

    def test_allows_tokyo_text_in_reasoning_connection_and_local_venue_name(self):
        outputs = {
            "transportation": _output(
                route_summary={"origin": "杭州", "destination": "美国"},
                options=[{
                    "id": "transport_1",
                    "origin": "杭州",
                    "destination": "美国",
                    "carrier": "Connection via Tokyo/NRT",
                }],
                reasoning="A Tokyo/NRT connection may be compared before booking.",
            ),
            "food": _output(
                daily_meals=[{
                    "date": "2026-08-01",
                    "meals": [{"name": "Tokyo Sushi House", "area": "New York"}],
                }],
            ),
        }

        self.assertIsNone(orchestrator._validate_agent_geography(TRIP, outputs))

    def test_rejects_polluted_structured_route_origin(self):
        outputs = {
            "transportation": _output(
                route_summary={"origin": "Tokyo", "destination": "美国"},
            ),
        }

        with self.assertRaisesRegex(ValueError, r"route_summary\.origin"):
            orchestrator._validate_agent_geography(TRIP, outputs)

    def test_rejects_tokyo_as_a_strong_route_endpoint(self):
        outputs = {
            "transportation": _output(
                recommended={
                    "id": "transport_1",
                    "origin": "杭州",
                    "destination": "美国",
                    "departure_airport": "NRT",
                    "arrival_airport": "JFK",
                },
                route_summary={"origin": "杭州", "destination": "美国"},
            ),
        }

        with self.assertRaisesRegex(ValueError, r"recommended\.departure_airport"):
            orchestrator._validate_agent_geography(TRIP, outputs)

    def test_rejects_tokyo_coordinates_hidden_behind_hgh_label(self):
        outputs = {
            "transportation": _output(
                recommended={
                    "id": "transport_1",
                    "origin": "杭州",
                    "destination": "美国",
                    "departure_airport": "HGH",
                    "arrival_airport": "JFK",
                },
                route_summary={"origin": "杭州", "destination": "美国"},
                route_points=[{
                    "label": "HGH",
                    "role": "departure",
                    "lat": 35.772,
                    "lng": 140.3929,
                }],
            ),
        }

        with self.assertRaisesRegex(ValueError, r"route_points\[0\]"):
            orchestrator._validate_agent_geography(TRIP, outputs)

    def test_rejects_nested_wrong_destination(self):
        outputs = {
            "activity": _output(
                recommended=[{"id": "activity_1", "destination": "Tokyo"}],
            ),
        }

        with self.assertRaisesRegex(ValueError, r"recommended\[0\]\.destination"):
            orchestrator._validate_agent_geography(TRIP, outputs)

    def test_rejects_missing_top_level_destination(self):
        with self.assertRaisesRegex(ValueError, "missing its required destination"):
            orchestrator._validate_agent_geography(TRIP, {"planning": {"reasoning": "ok"}})

    def test_rejects_exact_retired_tokyo_demo_record(self):
        outputs = {
            "activity": _output(
                recommended=[{
                    "id": "activity_1",
                    "name": "Culture walk",
                    "area": "Shibuya District",
                    "destination": "美国",
                }],
            ),
        }

        with self.assertRaisesRegex(ValueError, "retired Tokyo demo data"):
            orchestrator._validate_agent_geography(TRIP, outputs)

    def test_allows_nested_layover_destination(self):
        outputs = {
            "transportation": _output(
                recommended={
                    "id": "transport_1",
                    "origin": "杭州",
                    "destination": "美国",
                    "departure_airport": "HGH",
                    "arrival_airport": "JFK",
                    "segments": [{"destination": "Tokyo", "airport": "NRT"}],
                },
                route_summary={"origin": "杭州", "destination": "美国"},
            ),
        }

        self.assertIsNone(orchestrator._validate_agent_geography(TRIP, outputs))

    def test_rejects_tokyo_area_even_with_a_generic_food_name(self):
        outputs = {
            "food": _output(
                daily_meals=[{
                    "date": "2026-08-01",
                    "meals": [{"name": "Local breakfast", "area": "Tokyo"}],
                }],
            ),
        }

        with self.assertRaisesRegex(ValueError, r"meals\[0\]\.area"):
            orchestrator._validate_agent_geography(TRIP, outputs)

    def test_allows_tokyo_when_it_is_the_requested_destination(self):
        trip = {"location": "Tokyo", "origin": "杭州"}
        outputs = {
            "transportation": _output(
                "Tokyo",
                route_summary={"origin": "杭州", "destination": "Tokyo"},
                reasoning="Direct route to Tokyo.",
            ),
            "activity": _output(
                "Tokyo",
                recommended=[{"id": "ac_senso", "destination": "Tokyo"}],
            ),
        }

        self.assertIsNone(orchestrator._validate_agent_geography(trip, outputs))

    def test_synthesis_rejects_invented_lodging(self):
        trip = {
            **TRIP,
            "dates": {"start": "2026-08-01", "end": "2026-08-01"},
        }
        outputs = {
            "activity": {"recommended": [{"name": "Central Park walk"}]},
            "food": {"daily_meals": [{
                "date": "2026-08-01",
                "meals": [{"name": "Neighborhood breakfast"}],
            }]},
            "housing": {"recommended": {"name": "New York Central Hotel"}},
        }
        synth = {
            "schedule": [{
                "day": 1,
                "date": "2026-08-01",
                "title": "New York",
                "items": [
                    {"type": "hotel", "title": "Shinjuku Granbell Hotel"},
                    {"type": "meal", "title": "Neighborhood breakfast"},
                    {"type": "activity", "title": "Central Park walk"},
                ],
            }],
        }

        self.assertFalse(orchestrator._valid_synthesis(trip, synth, outputs))


if __name__ == "__main__":
    unittest.main()
