import unittest
from unittest.mock import patch

from agents import transportation_agent_v2
from services import gaode_service


class TransportationAgentV2Tests(unittest.TestCase):
    def test_car_only_request_uses_amap_route_without_flight_or_train_scraping(self):
        trip = {
            "origin": "杭州",
            "location": "上海",
            "dates": {"start": "2026-08-01", "end": "2026-08-02"},
            "budget": {"total": 3000, "currency": "CNY"},
            "preferences": {"transportation_type": ["car"]},
        }
        road = {
            "source": "gaode",
            "distance_km": 176.2,
            "duration_min": 145,
            "estimated_cost_cny": 128.5,
            "cost_basis": "one-way fuel/energy and toll estimate",
            "coordinate_system": "GCJ-02",
            "origin_lat": 30.2741,
            "origin_lng": 120.1551,
            "destination_lat": 31.2304,
            "destination_lng": 121.4737,
        }

        with patch.object(
            transportation_agent_v2,
            "_scrape_ctrip_flights",
        ) as flight_search, patch.object(
            transportation_agent_v2,
            "_scrape_ctrip_trains",
        ) as train_search, patch(
            "services.gaode_service.get_intercity_driving",
            return_value=road,
        ), patch.object(
            transportation_agent_v2,
            "llm_reason",
            return_value={"recommended_id": "amap-driving-route"},
        ) as llm_reason, patch(
            "services.gaode_service.get_local_transport",
            return_value={"modes": [], "total_cost_cny": 0, "has_real_routing": True},
        ), patch("booking.shared_db.save_transport"):
            result = transportation_agent_v2.run(trip)

        flight_search.assert_not_called()
        train_search.assert_not_called()
        llm_reason.assert_not_called()
        self.assertEqual(result["recommended"]["mode"], "car")
        self.assertEqual(result["coverage"]["available_modes"], ["car"])
        self.assertEqual(result["route_summary"]["mode"], "car")
        self.assertEqual(len(result["route_points"]), 2)

    def test_live_option_keeps_amap_route_contract(self):
        trip = {
            "origin": "杭州",
            "location": "New York",
            "dates": {"start": "2026-08-01", "end": "2026-08-04"},
            "budget": {"total": 5000, "currency": "USD"},
            "preferences": {"transportation_type": ["flight", "train"]},
        }
        flight = {
            "id": "live-flight-1",
            "type": "flight",
            "carrier": "Example Air",
            "flight_number": "EA101",
            "from": "杭州",
            "to": "New York",
            "departure_airport": "HGH",
            "arrival_airport": "JFK",
            "departure_time": "09:00",
            "arrival_time": "21:00",
            "duration": "12h",
            "price": 4200,
            "currency": "CNY",
            "stops": 0,
            "coordinate_system": "GCJ-02",
            "departure_lat": 30.236,
            "departure_lng": 120.43,
            "arrival_lat": 40.6413,
            "arrival_lng": -73.7781,
        }

        with patch.object(
            transportation_agent_v2,
            "_scrape_ctrip_flights",
            return_value=([flight], None),
        ), patch.object(
            transportation_agent_v2,
            "llm_reason",
            return_value={"recommended_id": "live-flight-1"},
        ), patch(
            "services.gaode_service.get_local_transport",
            return_value={"modes": [], "total_cost_cny": 0, "has_real_routing": False},
        ), patch("booking.shared_db.save_transport") as save_transport:
            result = transportation_agent_v2.run(trip)

        self.assertEqual(result["route_summary"]["origin"], "杭州")
        self.assertEqual(result["route_summary"]["destination"], "New York")
        self.assertEqual([point["label"] for point in result["route_points"]], ["HGH", "JFK"])
        self.assertEqual(result["coverage"]["available_modes"], ["flight"])
        self.assertIn("train", result["coverage"]["note"])
        self.assertEqual(result["booking_result"]["status"], "comparison_only")
        self.assertEqual(save_transport.call_args.kwargs["booking_status"], "pending")
        self.assertEqual(save_transport.call_args.kwargs["booking_ref"], "")

    def test_beijing_to_shanghai_distance_uses_lat_lng_order(self):
        distance = gaode_service.city_distance_km("北京", "上海")

        self.assertGreater(distance, 1000)
        self.assertLess(distance, 1150)


if __name__ == "__main__":
    unittest.main()
