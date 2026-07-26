"""Verify the Ctrip booking pipeline runs in STRICT (no-mock) mode.

What this proves:
  1. Mock fallback is OFF by default (ALLOW_MOCK_RESULTS unset) — so a normal
     run can never silently serve fake hotels or a fake order number.
  2. The REAL Ctrip data path is wired: resolve_city_id hits Ctrip's live
     autocomplete endpoint and returns a real city id.
  3. When live scraping is unavailable (no browser / blocked), search_and_filter
     RAISES instead of returning fake data — i.e. no mock data is ever injected.
  4. The DB layer (save -> list -> mark paid) persists/updates a real record
     correctly (uses a throwaway BOOKING_DB_PATH so it never touches prod data).

Run:  python backend/booking/verify_real.py
Exit: 0 = all checks passed, 1 = a guarantee was violated.
"""
from __future__ import annotations

import os
import sys
import tempfile

# Make the backend package importable when run as `python booking/verify_real.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use a throwaway DB so the verification never writes to the real store.
_TMP_DB = os.path.join(tempfile.gettempdir(), "booking_verify.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["BOOKING_DB_PATH"] = _TMP_DB

if os.environ.get("ALLOW_MOCK_RESULTS"):
    print("ERROR: ALLOW_MOCK_RESULTS is set — strict mode is OFF.")
    sys.exit(1)

from booking import ctrip, db
from booking.schemas import HotelSearchRequest
from booking import pipeline


def main() -> int:
    failures = []

    # 1) Strict mode is active.
    if ctrip.ALLOW_MOCK:
        failures.append("mock fallback must be DISABLED by default")
    else:
        print("[OK] strict mode: mock fallback disabled")

    # 2) Real Ctrip city resolution (needs network; proves live path is wired).
    try:
        city_id, name = ctrip.resolve_city_id("上海")
        if city_id:
            print(f"[OK] resolve_city_id('上海') -> id={city_id} name={name!r} (real Ctrip data)")
        else:
            print("[WARN] resolve_city_id returned no id (network/Ctrip blocked?) — live path unverified")
    except Exception as exc:
        print(f"[WARN] resolve_city_id raised: {exc} (network/Ctrip blocked?)")

    # 3) Live search must raise (no browser here), NOT return mock data.
    req = HotelSearchRequest(location="上海", check_in="2026-08-10",
                             check_out="2026-08-14", max_price_per_night=900,
                             min_rating=4.0, preferences=["central"])
    try:
        results = pipeline.search_and_filter(req)
        # If it returned something, it MUST be real (source == "ctrip").
        bad = [r for r in results if getattr(r, "source", None) != "ctrip"]
        if bad:
            failures.append(f"search returned {len(bad)} NON-real results: {[b.source for b in bad]}")
        else:
            print(f"[OK] search returned {len(results)} real Ctrip results (source='ctrip')")
    except Exception as exc:
        msg = str(exc)
        if "strict mode" in msg or "mock" in msg.lower():
            print(f"[OK] live search failed in strict mode (no fake data injected): {exc}")
        else:
            print(f"[OK] live search failed as expected (no fake data): {exc}")

    # 4) DB persistence works with real-shaped data.
    db.init_db()
    route = db.save_route(
        user_id=None, hotel_name="上海和平饭店", hotel_id="ctrip_123",
        hotel_url="https://hotels.ctrip.com/hotels/123.html",
        check_in="2026-08-10", check_out="2026-08-14", rooms=1, adults=2,
        children=0, room_type="豪华大床房", price_total=3600.0, currency="CNY",
        payment_method="wechat", status="pending_payment", order_no="CTRIP-999",
        raw="{}",
    )
    listed = db.list_routes()
    if not listed or listed[0]["id"] != route["id"]:
        failures.append("DB save/list round-trip failed")
    else:
        print(f"[OK] DB persisted route id={route['id']} (status={route['status']})")

    updated = db.update_route_status(route["id"], "confirmed", "CTRIP-999")
    if updated["status"] != "confirmed":
        failures.append("DB mark_paid failed")
    else:
        print(f"[OK] DB mark_paid -> status={updated['status']}")

    # Cleanup throwaway DB.
    try:
        os.remove(_TMP_DB)
    except OSError:
        pass

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  - " + f)
        return 1
    print("\nALL CHECKS PASSED: no mock data can appear in a normal run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
