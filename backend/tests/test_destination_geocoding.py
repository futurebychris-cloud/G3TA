import unittest
from unittest.mock import patch

from agents import planning_agent_v2
from booking import osm
from services import hotels_service


class DestinationGeocodingTests(unittest.TestCase):
    @patch.object(planning_agent_v2.urllib.request, "urlopen", side_effect=OSError("offline"))
    def test_planning_geocoder_never_silently_uses_beijing(self, _urlopen):
        with self.assertRaisesRegex(RuntimeError, "Atlantis"):
            planning_agent_v2._geocode_city("Atlantis")

    @patch.object(hotels_service.urllib.request, "urlopen", side_effect=OSError("offline"))
    def test_hotel_geocoder_never_silently_uses_shanghai(self, _urlopen):
        with self.assertRaisesRegex(RuntimeError, "Atlantis"):
            hotels_service._geocode_hotelbeds("Atlantis")

    @patch.object(osm, "_geocode", return_value=(45.4642, 9.19))
    @patch.object(osm, "_overpass_query")
    def test_osm_superior_star_format_cannot_stop_hotel_results(self, overpass, _geocode):
        overpass.return_value = {
            "elements": [{
                "id": 42,
                "type": "node",
                "lat": 45.46,
                "lon": 9.19,
                "tags": {"name": "Milano Hotel", "stars": "5S", "addr:city": "Milan"},
            }],
        }

        hotels = osm.search_osm_hotels("Milan, Italy")

        self.assertEqual(hotels[0]["rating"], 5.0)
        self.assertIn("premium", hotels[0]["tags"])


if __name__ == "__main__":
    unittest.main()
