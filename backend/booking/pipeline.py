"""Operator-only Ctrip payment-checkpoint pipeline.

This is the layer the FastAPI endpoints call. It keeps the endpoint code thin and
keeps all scraping/DB logic in booking/ctrip.py and booking/db.py.

Inputs follow the user's spec:
  * budget      -> HotelSearchRequest.max_price_per_night (the Budget Agent's
                   housing cap, in CNY for Ctrip)
  * location    -> HotelSearchRequest.location (from the Planning Agent)
  * preferences -> HotelSearchRequest.preferences / min_rating (Planning Agent)
  * identity    -> BookingConfirmRequest.{id_number,name,phone} (one-time input)
  * payment     -> user picks wechat | alipay in the frontend; we stop at the
                   payment checkpoint because Ctrip can't be paid automatically.
"""
from . import ctrip, db
from .schemas import HotelSearchRequest, HotelResult, BookingConfirmRequest, BookingResult


# --------------------------------------------------------------------------- #
# Step 1+2: search Ctrip by location, then filter by budget + preferences
# --------------------------------------------------------------------------- #
def filter_results(raw: list[dict], req: HotelSearchRequest) -> list[dict]:
    """Apply the budget + preference filters and rank. Pure function on a raw list.

    Hard filters: per-night budget cap and minimum rating. If they wipe everything
    out, relax so the UI still gets results. Ranking: preference-tag hits, then
    rating, then (lower) price. Hotels with an unknown price rank by rating only.
    """
    filtered = []
    for h in raw:
        price = h.get("price_per_night")
        if req.max_price_per_night is not None and price is not None and price > req.max_price_per_night:
            continue
        if req.min_rating is not None and (h.get("rating") or 0) < req.min_rating:
            continue
        filtered.append(h)

    if not filtered and raw:
        filtered = raw

    prefs = {p.lower() for p in req.preferences}

    def score(h: dict) -> tuple:
        tag_hit = len(prefs & {t.lower() for t in h.get("tags", [])})
        price = h.get("price_per_night")
        # Prefer more preference matches, then higher rating, then lower price.
        if price is not None:
            return (tag_hit, h.get("rating") or 0, -price)
        return (tag_hit, h.get("rating") or 0, 0)

    filtered.sort(key=score, reverse=True)
    return filtered[:12]


def search_and_filter(req: HotelSearchRequest) -> list[HotelResult]:
    raw = ctrip.search_hotels(req)
    return [HotelResult(**h) for h in filter_results(raw, req)]


# --------------------------------------------------------------------------- #
# Step 3+4+5: submit selection -> reach payment checkpoint -> store audit route
# --------------------------------------------------------------------------- #
def confirm_booking(req: BookingConfirmRequest) -> BookingResult:
    # Use identity only for this provider request. Do not persist passport/ID or
    # phone data in the G3TA database.
    contact = {
        "name": req.name or "",
        "id_number": req.id_number,
        "phone": req.phone or "",
    }
    if not all(contact.values()):
        return BookingResult(
            status="failed",
            order_no=None,
            message="Name, ID/passport number, and phone are required for a provider booking attempt.",
            route=None,
        )

    # Step 4: drive Playwright to the Ctrip payment checkpoint.
    # In strict mode (default) a failed live booking raises in ctrip.book_hotel;
    # we catch it here and return a clean "failed" result WITHOUT persisting a
    # fake route. Only a real attempt that reaches the payment checkpoint is stored.
    try:
        booking = ctrip.book_hotel(
            selection=req.hotel,
            contact=contact,
            dates={"check_in": req.check_in, "check_out": req.check_out},
            guests={"rooms": req.rooms, "adults": req.adults, "children": req.children},
            payment_method=req.payment_method,
        )
    except Exception as exc:
        return BookingResult(
            status="failed",
            order_no=None,
            message=f"真实携程下单失败（未写入任何数据）：{exc}",
            route=None,
        )

    order_no = booking.get("order_no")

    # Only persist when the live attempt actually reached a bookable state.
    if booking["status"] not in ("pending_payment", "confirmed"):
        return BookingResult(
            status=booking["status"],
            order_no=order_no,
            message=booking.get("message", "下单未完成，未写入任何数据。"),
            route=None,
        )

    # Step 5: persist an audit route whose status reflects the payment checkpoint.
    route = db.save_route(
        user_id=None,
        hotel_name=req.hotel.name,
        hotel_id=req.hotel.id,
        hotel_url=req.hotel.url,
        check_in=req.check_in,
        check_out=req.check_out,
        rooms=req.rooms,
        adults=req.adults,
        children=req.children,
        room_type=req.hotel.room_type,
        price_total=req.hotel.price_total,
        currency=req.hotel.currency,
        payment_method=req.payment_method,
        status=booking["status"],
        order_no=order_no,
        raw=str({
            "status": booking.get("status"),
            "order_no": booking.get("order_no"),
            "provider": "ctrip",
        }),
    )

    return BookingResult(
        status=booking["status"],
        order_no=order_no,
        message=booking["message"],
        route=route,
    )


def record_payment_report(route_id: int, order_no: str | None = None) -> dict | None:
    """Record what the user reports without claiming provider verification.

    Only a provider callback or a verified provider lookup may set a booking to
    ``confirmed``. The current integration has neither, so this remains a
    clearly labeled audit note.
    """
    return db.update_route_status(route_id, "payment_reported", order_no)
