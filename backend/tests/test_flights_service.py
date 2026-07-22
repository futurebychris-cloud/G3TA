import unittest
from unittest.mock import patch

from services import flights_service


class FlightsServiceTests(unittest.TestCase):
    @patch.object(flights_service, "generate_json")
    def test_destination_aware_route_coordinates_are_preserved(self, generate_json):
        generate_json.return_value = {
            "options": [
                {
                    "origin": "New York",
                    "destination": "Shanghai",
                    "carrier": f"Carrier {index}",
                    "mode": "flight",
                    "price": 600 + index,
                    "duration": "12h",
                    "departure_time": "10:00",
                    "departure_airport": "JFK",
                    "departure_lat": 40.6413,
                    "departure_lng": -73.7781,
                    "arrival_airport": "PVG",
                    "arrival_lat": 31.1422,
                    "arrival_lng": 121.8126,
                    "coordinate_system": "GCJ-02",
                    "stops": 0,
                }
                for index in range(3)
            ]
        }

        options = flights_service.get_flight_options(
            "New York",
            "Shanghai",
            {"start": "2026-04-10", "end": "2026-04-14"},
            {"total": 2500, "currency": "USD"},
            ["flight"],
        )

        self.assertEqual(len(options), 3)
        self.assertEqual(options[0]["departure_airport"], "JFK")
        self.assertEqual(options[0]["departure_lat"], 40.6413)
        self.assertEqual(options[0]["arrival_lng"], 121.8126)
        self.assertEqual(options[0]["coordinate_system"], "GCJ-02")
        self.assertEqual(options[0]["destination"], "Shanghai")
        self.assertTrue(options[0]["verification_required"])

    @patch.object(flights_service, "generate_json")
    def test_invalid_coordinate_pairs_are_omitted(self, generate_json):
        generate_json.return_value = {
            "options": [
                {
                    "origin": "New York",
                    "destination": "Shanghai",
                    "carrier": f"Carrier {index}",
                    "mode": "flight",
                    "price": 600 + index,
                    "arrival_airport": "PVG",
                    "departure_lat": 140,
                    "departure_lng": -73.7,
                    "arrival_lat": "not-a-number",
                    "arrival_lng": 121.8,
                    "coordinate_system": "GCJ-02",
                }
                for index in range(3)
            ]
        }

        option = flights_service.get_flight_options(
            "New York",
            "Shanghai",
            {"start": "2026-04-10", "end": "2026-04-14"},
        )[0]

        self.assertNotIn("departure_lat", option)
        self.assertNotIn("arrival_lat", option)

    @patch.object(flights_service, "generate_json")
    def test_wrong_destination_or_malformed_options_use_safe_fallback(self, generate_json):
        generate_json.return_value = {
            "options": [
                {
                    "origin": "New York",
                    "destination": "London",
                    "carrier": "Wrong City Air",
                    "mode": "flight",
                    "price": 500,
                    "arrival_airport": "LHR",
                    "arrival_lat": 51.47,
                    "arrival_lng": -0.4543,
                    "coordinate_system": "GCJ-02",
                }
            ]
        }

        options = flights_service.get_flight_options(
            "New York",
            "Shanghai",
            {"start": "2026-04-10", "end": "2026-04-14"},
        )

        self.assertEqual(len(options), 3)
        self.assertTrue(all(option["destination"] == "Shanghai" for option in options))
        self.assertTrue(all("arrival_lat" not in option for option in options))

        generate_json.return_value = {"options": None}
        malformed = flights_service.get_flight_options(
            "New York",
            "Shanghai",
            {"start": "2026-04-10", "end": "2026-04-14"},
        )
        self.assertEqual(len(malformed), 3)

    @patch.object(flights_service, "generate_json")
    def test_tokyo_endpoint_never_replaces_hangzhou(self, generate_json):
        generate_json.return_value = {
            "options": [
                {
                    "origin": "杭州",
                    "destination": "美国",
                    "carrier": f"Wrong route {index}",
                    "mode": "flight",
                    "price": 500 + index,
                    "departure_airport": "NRT",
                    "departure_lat": 35.772,
                    "departure_lng": 140.3929,
                    "arrival_airport": "JFK",
                    "arrival_lat": 40.6413,
                    "arrival_lng": -73.7781,
                    "coordinate_system": "GCJ-02",
                }
                for index in range(3)
            ]
        }

        options = flights_service.get_flight_options(
            "杭州",
            "美国",
            {"start": "2026-08-01", "end": "2026-08-05"},
        )

        self.assertEqual(len(options), 3)
        self.assertTrue(all(option["origin"] == "杭州" for option in options))
        self.assertTrue(all(option["destination"] == "美国" for option in options))
        self.assertTrue(all(option["carrier"].startswith("Flight option") for option in options))
        self.assertTrue(all("departure_lat" not in option for option in options))

    @patch.object(flights_service, "generate_json")
    def test_tokyo_coordinates_are_removed_even_when_airport_label_says_hgh(self, generate_json):
        generate_json.return_value = {
            "options": [
                {
                    "origin": "杭州",
                    "destination": "美国",
                    "carrier": f"Coordinate check {index}",
                    "mode": "flight",
                    "price": 500 + index,
                    "departure_airport": "HGH",
                    "departure_lat": 35.772,
                    "departure_lng": 140.3929,
                    "arrival_airport": "JFK",
                    "arrival_lat": 40.6413,
                    "arrival_lng": -73.7781,
                    "coordinate_system": "GCJ-02",
                }
                for index in range(3)
            ]
        }

        options = flights_service.get_flight_options(
            "杭州",
            "美国",
            {"start": "2026-08-01", "end": "2026-08-05"},
        )

        self.assertEqual(len(options), 3)
        self.assertTrue(all("departure_lat" not in option for option in options))
        self.assertTrue(all(option["arrival_airport"] == "JFK" for option in options))
        self.assertTrue(all(option["arrival_lat"] == 40.6413 for option in options))

if __name__ == "__main__":
    unittest.main()
