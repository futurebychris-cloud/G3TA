import json
import unittest
from datetime import date
from unittest.mock import patch

from services import train12306_service


class _FakeResponse:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self._raw


class _FakeOpener:
    def __init__(self, payload):
        self._payload = payload

    def open(self, request, timeout):
        return _FakeResponse(self._payload)


def _result_row(index, can_web_buy=True):
    fields = [""] * 33
    departure_minutes = 6 * 60 + index * 20
    arrival_minutes = departure_minutes + 60
    fields[0] = "secret"
    fields[1] = "预订" if can_web_buy else "列车停运"
    fields[2] = f"internal-{index}"
    fields[3] = f"G{index}"
    fields[4] = "HZH"
    fields[5] = "SHH"
    fields[6] = "HZH"
    fields[7] = "SHH"
    fields[8] = f"{departure_minutes // 60:02d}:{departure_minutes % 60:02d}"
    fields[9] = f"{arrival_minutes // 60:02d}:{arrival_minutes % 60:02d}"
    fields[10] = "01:00"
    fields[11] = "Y" if can_web_buy else "N"
    fields[16] = "01"
    fields[17] = "02"
    fields[23] = "有"
    fields[25] = "有"
    fields[26] = "有"
    return "|".join(fields)


class Train12306PriceCandidateTests(unittest.TestCase):
    def test_candidates_filter_unsaleable_then_sort_time_duration_and_type(self):
        query_fields = {
            "internal_train_no": "internal",
            "from_station_no": "01",
            "to_station_no": "02",
        }
        trains = [
            {
                **query_fields,
                "train_no": "G-late",
                "can_web_buy": True,
                "has_available_seat": True,
                "departure_time": "09:00",
                "duration": "01:00",
                "type_prefix": "G",
            },
            {
                **query_fields,
                "train_no": "G-no-seat",
                "can_web_buy": True,
                "has_available_seat": False,
                "departure_time": "06:00",
                "duration": "00:30",
                "type_prefix": "G",
            },
            {
                **query_fields,
                "train_no": "D-short",
                "can_web_buy": True,
                "has_available_seat": True,
                "departure_time": "08:00",
                "duration": "00:45",
                "type_prefix": "D",
            },
            {
                **query_fields,
                "train_no": "G-short",
                "can_web_buy": True,
                "has_available_seat": True,
                "departure_time": "08:00",
                "duration": "00:45",
                "type_prefix": "G",
            },
            {
                **query_fields,
                "train_no": "G-stopped",
                "can_web_buy": False,
                "has_available_seat": True,
                "departure_time": "05:00",
                "duration": "00:30",
                "type_prefix": "G",
            },
        ]

        selected = train12306_service._select_price_query_candidates(trains, limit=4)

        self.assertEqual(
            [train["train_no"] for train in selected],
            ["G-short", "D-short", "G-late"],
        )

    def test_search_limits_price_requests_and_keeps_result_contract(self):
        rows = [
            _result_row(index, can_web_buy=index < 30)
            for index in reversed(range(40))
        ]
        payload = {
            "status": True,
            "httpstatus": 200,
            "data": {
                "result": rows,
                "map": {"HZH": "杭州", "SHH": "上海"},
            },
        }

        with patch.object(
            train12306_service,
            "_get_12306_opener",
            return_value=_FakeOpener(payload),
        ), patch.object(
            train12306_service,
            "_query_ticket_price",
            return_value={"O": 73.0, "M": 117.0, "9": 219.0},
        ) as query_price:
            trains = train12306_service.search_trains(
                "杭州", "上海", date.today().isoformat()
            )

        self.assertEqual(len(trains), 40)
        self.assertEqual(
            query_price.call_count,
            train12306_service.MAX_PRICE_DETAIL_QUERIES,
        )
        self.assertEqual(
            [call.args[0] for call in query_price.call_args_list],
            [f"internal-{index}" for index in range(24)],
        )
        self.assertEqual([train["train_no"] for train in trains], [f"G{i}" for i in reversed(range(40))])
        self.assertEqual(
            sum(train["source"] == "12306_real_price" for train in trains),
            train12306_service.MAX_PRICE_DETAIL_QUERIES,
        )
        self.assertEqual(
            sum(train["source"] == "12306_estimated" for train in trains),
            40 - train12306_service.MAX_PRICE_DETAIL_QUERIES,
        )
        self.assertEqual(
            set(trains[0]),
            {
                "train_no",
                "type",
                "departure_time",
                "arrival_time",
                "duration",
                "from_station",
                "to_station",
                "start_station",
                "end_station",
                "price_second",
                "price_first",
                "price_business",
                "seats_second",
                "seats_first",
                "seats_business",
                "currency",
                "source",
                "from",
                "to",
            },
        )


if __name__ == "__main__":
    unittest.main()
