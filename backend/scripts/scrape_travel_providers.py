#!/usr/bin/env python3
"""Scrape public Ctrip/Fliggy pages with Playwright and persist the result."""
from __future__ import annotations

import argparse
import json

from services.travel_market_scraper import scrape_and_persist_all


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--departure-date", required=True)
    parser.add_argument("--check-in")
    parser.add_argument("--check-out", required=True)
    parser.add_argument("--adults", type=int, default=1)
    parser.add_argument("--children", type=int, default=0)
    parser.add_argument("--rooms", type=int, default=1)
    parser.add_argument("--ttl-seconds", type=float, default=86_400)
    args = parser.parse_args()

    query = {
        "origin": args.origin,
        "destination": args.destination,
        "departure_date": args.departure_date,
        "check_in": args.check_in or args.departure_date,
        "check_out": args.check_out,
        "adults": args.adults,
        "children": args.children,
        "rooms": args.rooms,
    }
    payloads = scrape_and_persist_all(query, ttl_seconds=args.ttl_seconds)
    print(
        json.dumps(
            [
                {
                    "provider": item["provider"],
                    "category": item["category"],
                    "status": item["status"],
                    "result_count": item["result_count"],
                    "final_url": item["final_url"],
                    "error": item["error"],
                }
                for item in payloads
            ],
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
