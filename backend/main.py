"""FastAPI app for the multi-agent trip planner.

Endpoints:
    GET  /                 health check
    POST /intake/parse     turn guided answers into a reviewable form draft
    POST /speech/synthesize render accessible speech with local Piper
    POST /agents/{name}    run one specialist agent (modularity / debugging)
    POST /plan             run the full orchestration, return the final itinerary
    POST /plan/stream      same, but stream per-agent progress as Server-Sent Events

Run from the backend/ directory:
    uvicorn main:app --reload
"""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

# Load .env from project root or backend dir.
# Try the parent directory first (when running from backend/), then cwd.
import os as _os
_env_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".env")
if _os.path.exists(_env_path):
    load_dotenv(_env_path)
else:
    load_dotenv(find_dotenv(usecwd=True))

from agents import AGENT_ORDER  # noqa: E402
import orchestrator  # noqa: E402

# Booking pipeline (Ctrip Playwright + filter + confirm + store).
from booking import pipeline, db  # noqa: E402
from booking.schemas import (  # noqa: E402
    HotelSearchRequest,
    HotelResult,
    RoomInfo,
    BookingConfirmRequest,
    BookingResult,
)
from booking.shared_db import init_shared_db  # noqa: E402
from booking.auto_book import (  # noqa: E402
    auto_book_hotel, auto_book_flight, auto_book_train, auto_book_restaurant,
    store_credentials, get_stored_credentials, book_item,
    search_flights, search_trains, book_flight_by_index,
)
from services import hotels_provider  # noqa: E402
from services import piper_service  # noqa: E402
from services import whisper_service  # noqa: E402
from intake import parse_intake  # noqa: E402

db.init_db()  # create users + confirmed_routes tables on startup
init_shared_db()  # create shared agent data tables

app = FastAPI(title="Multi-Agent AI Trip Planner", version="0.1.0")

# Frontend dev server (Vite) runs on a different port; allow it during MVP.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Dates(BaseModel):
    start: str
    end: str


class Budget(BaseModel):
    total: float
    currency: str = "USD"


class Preferences(BaseModel):
    bites: list[str] = Field(default_factory=list)
    transportation_type: list[str] = Field(default_factory=list)
    activity_style: list[str] = Field(default_factory=list)
    taste: list[str] = Field(default_factory=list)
    food_budget: float = 0
    budget_priority: dict[str, float] = Field(default_factory=dict)


class AccessibilityPreferences(BaseModel):
    easy_reading: bool = False
    preset: str = "standard"


class TripInput(BaseModel):
    location: str
    origin: str = "New York"
    dates: Dates
    budget: Budget
    preferences: Preferences = Field(default_factory=Preferences)
    accessibility: AccessibilityPreferences = Field(default_factory=AccessibilityPreferences)
    time_constraints: str = ""
    must_go_sites: list[str] = Field(default_factory=list)
    num_people: int = Field(default=1, ge=1, le=100)
    is_group: bool = False


class IntakeRequest(BaseModel):
    description: str = Field(min_length=10, max_length=2500)
    language: str = Field(default="en", max_length=16)


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12_000)
    language: str = Field(default="en", max_length=16)
    speed: float = Field(default=1.0, ge=0.6, le=1.5)


@app.get("/")
@app.get("/health")
def health():
    return {"status": "ok", "service": "trip-planner", "agents": AGENT_ORDER}


@app.post("/intake/parse")
def intake_parse(request: IntakeRequest):
    """Extract a reviewable form draft; this endpoint never starts planning."""
    try:
        return parse_intake(request.description, language=request.language)
    except RuntimeError:
        raise HTTPException(
            status_code=503,
            detail="The guided assistant is temporarily unavailable. Your description is still safe to edit, and the normal form remains available.",
        )
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="The trip assistant could not understand that description. Your text is still available to edit.",
        )


@app.post("/speech/synthesize")
def speech_synthesize(request: SpeechRequest):
    """Render text with Piper; never fall back to an operating-system voice."""
    language = "zh" if request.language.casefold().startswith("zh") else "en"
    try:
        audio = piper_service.synthesize_speech(
            text=request.text,
            language=language,
            speed=request.speed,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@app.post("/speech/transcribe")
async def speech_transcribe(request: Request):
    """Transcribe a short recording and report Whisper's detected language."""
    audio = await request.body()
    content_type = request.headers.get("content-type", "audio/webm").split(";", 1)[0]
    try:
        return whisper_service.transcribe_speech(audio, content_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/agents/{name}")
def run_agent(name: str, trip: TripInput):
    try:
        return orchestrator.run_single_agent(name, trip.model_dump())
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown agent '{name}'. Valid: {AGENT_ORDER}")
    except RuntimeError as e:  # missing API key
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/plan")
def plan(trip: TripInput):
    try:
        return orchestrator.plan(trip.model_dump())
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


# --------------------------------------------------------------------------- #
# Booking pipeline endpoints
# --------------------------------------------------------------------------- #
class MarkPaidRequest(BaseModel):
    route_id: int
    order_no: str | None = None


@app.post("/booking/search")
def booking_search(req: HotelSearchRequest):
    """Stream the 4-stage hotel search: search -> filtering -> outputting -> cards.

    Emits SSE events:
        {type:'booking_stage', stage:'search'|'filtering'|'outputting', status, source?, count?}
        {type:'booking_results', hotels:[HotelResult...]}
        {type:'error', message}
    """
    def generate():
        yield _sse({"type": "booking_stage", "stage": "search", "status": "running"})
        try:
            raw, source = hotels_provider.raw_search(
                req.location,
                {"start": req.check_in, "end": req.check_out},
                req.max_price_per_night,
                req.min_rating,
                req.preferences,
            )
        except Exception as exc:
            yield _sse({"type": "error", "message": f"Hotel search failed: {exc}"})
            return
        yield _sse({"type": "booking_stage", "stage": "search", "status": "done", "source": source})

        yield _sse({"type": "booking_stage", "stage": "filtering", "status": "running"})
        filtered = pipeline.filter_results(raw, req)
        yield _sse({"type": "booking_stage", "stage": "filtering", "status": "done", "count": len(filtered)})

        yield _sse({"type": "booking_stage", "stage": "outputting", "status": "running"})
        results = [HotelResult(**h).model_dump() for h in filtered[:12]]
        yield _sse({"type": "booking_stage", "stage": "outputting", "status": "done"})

        yield _sse({"type": "booking_results", "hotels": results})

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/booking/confirm")
def booking_confirm(req: BookingConfirmRequest) -> BookingResult:
    """Confirm a selected hotel: drive Playwright to Ctrip's payment checkpoint.

    Fills the traveler's name/ID/phone (from the DB users table), selects the room,
    picks 微信/支付宝, and stops at pending_payment with an order number. The
    confirmed route is stored; it flips to 'confirmed' only after the user pays and
    calls /booking/mark_paid.
    """
    return pipeline.confirm_booking(req)


@app.post("/booking/mark_paid")
def booking_mark_paid(req: MarkPaidRequest):
    """Mark a stored route as paid (user paid in their own WeChat/Alipay)."""
    route = pipeline.mark_paid(req.route_id, req.order_no)
    if route is None:
        raise HTTPException(status_code=404, detail="Route not found")
    return route


@app.get("/booking/routes")
def booking_routes():
    """List all stored confirmed routes (audit trail)."""
    return db.list_routes()


# --------------------------------------------------------------------------- #
# Auto-booking pipeline endpoints (hotel, flight, train, restaurant)
# --------------------------------------------------------------------------- #


class AutoBookHotelRequest(BaseModel):
    hotel_id: str
    hotel_name: str
    hotel_url: str = ""
    check_in: str
    check_out: str
    rooms: int = 1
    adults: int = 1
    children: int = 0
    room_type: str | None = None
    price_total: float | None = None
    currency: str = "CNY"
    payment_method: str = "wechat"


class AutoBookFlightRequest(BaseModel):
    origin: str
    destination: str
    depart_date: str
    return_date: str = ""
    adults: int = 1
    preferred_flight: str = ""
    max_price: float | None = None
    payment_method: str = "wechat"


class AutoBookTrainRequest(BaseModel):
    origin_station: str
    dest_station: str
    depart_date: str
    preferred_train: str = ""
    seat_class: str = "second"
    adults: int = 1


class AutoBookRestaurantRequest(BaseModel):
    restaurant_name: str
    date: str
    time_slot: str = "19:00"
    party_size: int = 2
    phone: str = ""


class FlightSearchRequest(BaseModel):
    """Search flights and return top results for customer review."""
    origin: str
    destination: str
    depart_date: str
    return_date: str = ""
    adults: int = 1
    max_price: float | None = None


class TrainSearchRequest(BaseModel):
    """Search trains and return top results for customer review."""
    origin_station: str
    dest_station: str
    depart_date: str


class BookFlightByIndexRequest(BaseModel):
    """Search + book Nth cheapest flight result."""
    origin: str
    destination: str
    depart_date: str
    result_index: int = 0
    adults: int = 1
    payment_method: str = "wechat"


class StoreCredentialsRequest(BaseModel):
    name: str
    id_number: str
    phone: str


@app.post("/booking/auto/hotel")
def auto_hotel(req: AutoBookHotelRequest):
    """Auto-book a hotel via Ctrip Playwright. Uses stored credentials from DB."""
    return auto_book_hotel(
        hotel_id=req.hotel_id,
        hotel_name=req.hotel_name,
        hotel_url=req.hotel_url,
        check_in=req.check_in,
        check_out=req.check_out,
        rooms=req.rooms,
        adults=req.adults,
        children=req.children,
        room_type=req.room_type,
        price_total=req.price_total,
        currency=req.currency,
        payment_method=req.payment_method,
    )


@app.post("/booking/auto/flight")
def auto_flight(req: AutoBookFlightRequest):
    """Auto-book a flight via Ctrip Playwright. Uses stored credentials from DB."""
    return auto_book_flight(
        origin=req.origin,
        destination=req.destination,
        depart_date=req.depart_date,
        return_date=req.return_date,
        adults=req.adults,
        preferred_flight=req.preferred_flight,
        max_price=req.max_price,
        payment_method=req.payment_method,
    )


@app.post("/booking/auto/train")
def auto_train(req: AutoBookTrainRequest):
    """Auto-book a train ticket via 12306. Uses stored credentials from DB."""
    return auto_book_train(
        origin_station=req.origin_station,
        dest_station=req.dest_station,
        depart_date=req.depart_date,
        preferred_train=req.preferred_train,
        seat_class=req.seat_class,
        adults=req.adults,
    )


@app.post("/booking/auto/restaurant")
def auto_restaurant(req: AutoBookRestaurantRequest):
    """Auto-book a restaurant reservation. Uses stored credentials from DB."""
    return auto_book_restaurant(
        restaurant_name=req.restaurant_name,
        date=req.date,
        time_slot=req.time_slot,
        party_size=req.party_size,
        phone=req.phone,
    )


@app.post("/booking/credentials")
def save_credentials(req: StoreCredentialsRequest):
    """Store traveler identity credentials for auto-booking."""
    uid = store_credentials(req.name, req.id_number, req.phone)
    return {"user_id": uid, "message": "Credentials stored successfully."}


# --------------------------------------------------------------------------- #
# Search-first booking endpoints — show top results before customer commits
# --------------------------------------------------------------------------- #

@app.post("/booking/search/flights")
def search_flights_endpoint(req: FlightSearchRequest):
    """Search flights and return top 5 results by price for customer review.

    Customer sees price, airline, flight number, times for each option.
    They pick one, then call POST /booking/auto/flight with preferred_flight.
    """
    return search_flights(
        origin=req.origin,
        destination=req.destination,
        depart_date=req.depart_date,
        return_date=req.return_date,
        adults=req.adults,
        max_price=req.max_price,
    )


@app.post("/booking/search/trains")
def search_trains_endpoint(req: TrainSearchRequest):
    """Search 12306 trains and return top 5 results (HSR first) for customer review.

    Customer sees train number, type, departure/arrival times, estimated price.
    They pick one, then call POST /booking/auto/train with preferred_train.
    """
    return search_trains(
        origin_station=req.origin_station,
        dest_station=req.dest_station,
        depart_date=req.depart_date,
    )


@app.post("/booking/book-flight-by-index")
def book_flight_index(req: BookFlightByIndexRequest):
    """One-shot: search flights, pick Nth cheapest, auto-book to payment checkpoint.

    Convenience endpoint for "book the cheapest flight" flow.
    result_index=0 books the cheapest, 1 the second-cheapest, etc.
    """
    return book_flight_by_index(
        origin=req.origin,
        destination=req.destination,
        depart_date=req.depart_date,
        result_index=req.result_index,
        adults=req.adults,
        payment_method=req.payment_method,
    )


@app.post("/plan/stream")
def plan_stream(trip: TripInput):
    """Run agents one at a time and stream progress so the UI can show a live checklist."""
    trip_input = orchestrator.prepare_trip_input(trip.model_dump())

    def generate():
        outputs = {}
        try:
            # Budget must finish first so every recommendation agent receives the
            # category limits it is expected to respect.
            yield _sse({"type": "agent_start", "agent": "budget"})
            outputs["budget"] = orchestrator.run_single_agent("budget", trip_input)
            yield _sse({"type": "agent_done", "agent": "budget", "output": outputs["budget"]})

            guided_input = orchestrator.with_budget_guidance(trip_input, outputs["budget"])
            remaining_agents = [name for name in AGENT_ORDER if name != "budget"]
            for name in remaining_agents:
                yield _sse({"type": "agent_start", "agent": name})
            with ThreadPoolExecutor(max_workers=len(remaining_agents)) as executor:
                futures = {
                    executor.submit(orchestrator.run_single_agent, name, guided_input): name
                    for name in remaining_agents
                }
                for future in as_completed(futures):
                    name = futures[future]
                    outputs[name] = future.result()
                    yield _sse({"type": "agent_done", "agent": name, "output": outputs[name]})

            yield _sse({"type": "agent_start", "agent": "orchestrator"})
            result = orchestrator.reconcile_and_synthesize(trip_input, outputs)
            result["trip_id"] = trip_input["trip_id"]
            yield _sse({"type": "agent_done", "agent": "orchestrator"})
            yield _sse({"type": "complete", "result": result})
        except RuntimeError as e:
            yield _sse({"type": "error", "message": str(e)})
        except Exception as e:  # noqa: BLE001 — surface anything else to the UI
            yield _sse({"type": "error", "message": f"Unexpected error: {e}"})

    return StreamingResponse(generate(), media_type="text/event-stream")
