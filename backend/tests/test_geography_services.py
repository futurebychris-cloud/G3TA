import unittest
from unittest.mock import patch

from services import _geography, activities_service, food_service, hotels_service


class GeographyServiceTests(unittest.TestCase):
    @patch.object(activities_service, "generate_json")
    def test_activity_service_discards_retired_tokyo_places(self, generate_json):
        generate_json.return_value = {
            "options": [{
                "name": "Culture walk",
                "style": "cultural",
                "price": 0,
                "duration": "2h",
                "area": "Shibuya District",
            }] * 4,
        }

        for destination in ("美国", "Yokohama"):
            options = activities_service.get_activity_options(destination, ["cultural"], 4)

            self.assertEqual(len(options), 4)
            self.assertTrue(all(option["destination"] == destination for option in options))
            self.assertTrue(all("Shibuya" not in option["area"] for option in options))

    def test_tokyo_coordinate_guard_does_not_cover_ibaraki_airport(self):
        self.assertFalse(_geography.coordinates_are_tokyo_endpoint(36.181, 140.415))

    def test_hotel_service_discards_retired_tokyo_places(self):
        provider_options = [{
                "name": "Shinjuku Granbell Hotel",
                "price_per_night": 100,
                "rating": 4.5,
                "area": "Shinjuku",
            }, {
                "name": "Hudson River Hotel",
                "price_per_night": 180,
                "rating": 4.4,
                "area": "New York",
            }]

        with patch.object(
            hotels_service,
            "_DISPATCH",
            {name: lambda *_args: provider_options for name in hotels_service._PROVIDERS},
        ):
            options = hotels_service.get_hotel_options(
                "美国", {"start": "2026-08-01", "end": "2026-08-03"},
            )

        self.assertEqual(len(options), 1)
        self.assertTrue(all(option["area"] != "Shinjuku" for option in options))

    @patch.object(food_service, "generate_json")
    def test_food_service_allows_tokyo_brand_but_rejects_tokyo_area(self, generate_json):
        options = []
        for index in range(12):
            options.append({
                "name": f"Tokyo Sushi House {index}",
                "cuisine": "Japanese",
                "cuisine_family": "Japanese",
                "price": 20,
                "meal_type": ("breakfast", "lunch", "dinner")[index % 3],
                "area": "New York" if index else "Tokyo",
            })
        generate_json.return_value = {"options": options}

        result = food_service.get_food_options("美国", ["Japanese"], num_days=4)

        self.assertEqual(len(result), 12)
        self.assertTrue(all(option["area"] != "Tokyo" for option in result))
        self.assertTrue(any(option["name"].startswith("Tokyo Sushi House") for option in result))


if __name__ == "__main__":
    unittest.main()
