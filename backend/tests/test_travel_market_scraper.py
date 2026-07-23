import pytest

from booking import shared_db
from services.travel_market_scraper import (
    _status_from_text,
    parse_fliggy_flight_cards,
    parse_fliggy_nearby_cards,
    persist_scrape,
)


def test_status_detects_fliggy_captcha_response_url():
    status = _status_from_text(
        "航班数据读取中",
        ["https://sijipiao.fliggy.com/query/_____tmd_____/punish?captcha=1"],
    )
    assert status == "blocked"


def test_status_detects_ctrip_whaleguard():
    assert _status_from_text("whaleguard block HTTP 432") == "blocked"


def test_persist_refuses_local_sqlite(monkeypatch):
    monkeypatch.setattr(shared_db, "_USE_POSTGRES", False)
    with pytest.raises(RuntimeError, match="Remote PostgreSQL is required"):
        persist_scrape(
            {
                "provider": "ctrip",
                "category": "flights",
                "query": {"origin": "New York", "destination": "Shanghai"},
            }
        )


def test_parse_fliggy_flight_card():
    results = parse_fliggy_flight_cards(
        ["中国东方航空 MU588 16:25 19:10 ¥3985 含税"],
        "New York",
        "Shanghai",
    )
    assert results == [
        {
            "id": "fliggy_flight_0",
            "from": "New York",
            "to": "Shanghai",
            "flight_number": "MU588",
            "departure_time": "16:25",
            "arrival_time": "19:10",
            "price": 3985.0,
            "currency": "CNY",
            "source": "fliggy_live_public",
            "raw_text": "中国东方航空 MU588 16:25 19:10 ¥3985 含税",
        }
    ]


def test_parse_fliggy_nearby_offer_keeps_fare_and_tax():
    results = parse_fliggy_nearby_cards(
        ["纽约 - 杭州\n07-30 周四(去)\n¥1969 票面 + ¥2016 税费"]
    )
    assert results[0]["route"] == "纽约 - 杭州"
    assert results[0]["fare_price"] == 1969
    assert results[0]["tax_price"] == 2016
    assert results[0]["total_price"] == 3985
