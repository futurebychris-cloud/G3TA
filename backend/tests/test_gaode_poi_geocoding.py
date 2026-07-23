import unittest
from unittest.mock import patch

from services import gaode_service


class GaodePoiGeocodingTests(unittest.TestCase):
    def test_bilingual_pois_use_city_limited_place_search_and_remain_distinct(self):
        locations = {
            "外滩": "121.492127,31.233516",
            "豫园": "121.492497,31.227714",
        }

        def place_response(path, params, timeout=8):
            self.assertEqual(path, "/place/text")
            self.assertEqual(params["city"], "310000")
            self.assertEqual(params["citylimit"], "true")
            return {
                "status": "1",
                "pois": [{"name": params["keywords"], "location": locations[params["keywords"]]}],
            }

        with (
            patch.object(gaode_service, "GAODE_KEY", "test-web-service-key"),
            patch.object(gaode_service, "_gaode_city_filter", return_value="310000"),
            patch.object(gaode_service, "_gaode_json", side_effect=place_response),
        ):
            bund = gaode_service.geocode_poi("The Bund (外滩)", "Shanghai")
            garden = gaode_service.geocode_poi("Yu Garden (豫园)", "Shanghai")

        self.assertEqual(bund, (31.233516, 121.492127))
        self.assertEqual(garden, (31.227714, 121.492497))
        self.assertNotEqual(bund, garden)

    def test_failed_poi_lookup_does_not_impersonate_the_city_center(self):
        with (
            patch.object(gaode_service, "GAODE_KEY", "test-web-service-key"),
            patch.object(gaode_service, "_geocode_poi_text", return_value=None),
            patch.object(gaode_service, "_geocode_single", return_value=None),
            patch.object(gaode_service, "geocode_city", return_value=(31.2304, 121.4737)),
        ):
            result = gaode_service.geocode_poi("Unknown attraction", "Shanghai")

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
