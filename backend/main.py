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
import time
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4
from concurrent.futures import (
    FIRST_COMPLETED,
    ThreadPoolExecutor,
    TimeoutError as FutureTimeoutError,
    wait,
)

from dotenv import find_dotenv, load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator

# Load shared defaults, then ignored machine-local overrides.
import os as _os
_project_root = Path(__file__).resolve().parent.parent
_env_path = _project_root / ".env"
_local_env_path = _project_root / ".env.local"
if _env_path.exists():
    load_dotenv(_env_path)
if _local_env_path.exists():
    load_dotenv(_local_env_path, override=True)
if not _env_path.exists() and not _local_env_path.exists():
    load_dotenv(find_dotenv(usecwd=True))

from agents import AGENT_ORDER  # noqa: E402
import orchestrator  # noqa: E402

# Hotel comparison plus an operator-only Ctrip payment-checkpoint experiment.
from booking import pipeline, db, ctrip  # noqa: E402
from booking.schemas import (  # noqa: E402
    HotelSearchRequest,
    HotelResult,
    HotelSelection,
    BookingConfirmRequest,
    BookingResult,
)
from booking.shared_db import init_shared_db, get_checklist_by_trip, set_checklist_packed  # noqa: E402
from booking.auto_book import (  # noqa: E402
    search_flights, search_trains,
)
from services import hotels_provider  # noqa: E402
from services import piper_service  # noqa: E402
from intake import parse_intake  # noqa: E402
from security import (  # noqa: E402
    booking_automation_enabled,
    cors_allowed_origins,
    require_booking_access,
)
from plan_runtime import (  # noqa: E402
    PlanningCancelled,
    cancel_plan as cancel_active_plan,
    finish_plan,
    register_plan,
)

# Booking automation stores sensitive traveler data, so it is opt-in. Core
# planning and hotel comparison work without PostgreSQL.
_booking_db_ready = False
if booking_automation_enabled():
    try:
        db.init_db()
        _booking_db_ready = True
        print("[main] PostgreSQL booking DB initialized")
    except Exception as e:
        print(f"[main] PostgreSQL booking DB unavailable: {e}")
else:
    print("[main] Booking automation disabled (safe default)")

try:
    init_shared_db()  # create shared agent data tables (SQLite fallback if no DATABASE_URL)
    print("[main] Shared agent DB initialized")
except Exception as e:
    print(f"[main] Shared DB init failed: {e}")

app = FastAPI(title="Multi-Agent AI Trip Planner", version="0.1.0")

# The local Vite origins are allowed by default. Production deployments must
# provide their explicit origins through CORS_ALLOWED_ORIGINS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Dates(BaseModel):
    start: str
    end: str

    @model_validator(mode="after")
    def validate_range(self):
        try:
            start_date = date.fromisoformat(self.start)
            end_date = date.fromisoformat(self.end)
        except ValueError as exc:
            raise ValueError("Dates must use YYYY-MM-DD format.") from exc
        if end_date < start_date:
            raise ValueError("End date must be on or after start date.")
        if (end_date - start_date).days > 31:
            raise ValueError("Trips longer than 32 calendar days are not supported.")
        return self


class Budget(BaseModel):
    total: float = Field(gt=0)
    currency: str = Field(default="USD", pattern=r"^[A-Za-z]{3}$")

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


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
    location: str = Field(min_length=1, max_length=200)
    origin: str = Field(default="New York", min_length=1, max_length=200)
    dates: Dates
    budget: Budget
    preferences: Preferences = Field(default_factory=Preferences)
    accessibility: AccessibilityPreferences = Field(default_factory=AccessibilityPreferences)
    time_constraints: str = ""
    must_go_sites: list[str] = Field(default_factory=list)
    num_people: int = Field(default=1, ge=1, le=100)
    is_group: bool = False
    request_id: str = Field(default_factory=lambda: str(uuid4()), min_length=8, max_length=100)


class IntakeRequest(BaseModel):
    description: str = Field(min_length=10, max_length=2500)


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12_000)
    language: str = Field(default="en", max_length=16)
    speed: float = Field(default=1.0, ge=0.6, le=1.5)


@app.get("/health")
def health():
    deepseek_configured = bool(_os.getenv("DEEPSEEK_API_KEY", "").strip())
    booking_enabled = booking_automation_enabled()
    return {
        "status": "ok" if deepseek_configured else "degraded",
        "service": "trip-planner",
        "agents": AGENT_ORDER,
        "dependencies": {
            "deepseek": "configured" if deepseek_configured else "missing_key",
            "amap_web_service": (
                "configured"
                if (_os.getenv("GAODE_KEY", "") or _os.getenv("AMAP_KEY", "")).strip()
                else "optional_missing"
            ),
            "piper": "configured" if _os.getenv("PIPER_TTS_URL", "").strip() else "optional_missing",
            "booking_automation": (
                "ready" if booking_enabled and _booking_db_ready
                else "database_unavailable" if booking_enabled
                else "disabled"
            ),
        },
    }


_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@app.get("/", include_in_schema=False)
def root():
    index = _FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    return health()


@app.post("/intake/parse")
def intake_parse(request: IntakeRequest):
    """Extract a reviewable form draft; this endpoint never starts planning."""
    try:
        return parse_intake(request.description)
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

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/booking/confirm")
def booking_confirm(
    req: BookingConfirmRequest,
    _: None = Depends(require_booking_access),
) -> BookingResult:
    """Use one-time traveler details to attempt Ctrip's payment checkpoint.

    This operator-only experiment does not persist identity fields and does not
    claim a provider-confirmed purchase.
    """
    return pipeline.confirm_booking(req)


@app.post("/booking/mark_paid")
def booking_mark_paid(
    req: MarkPaidRequest,
    _: None = Depends(require_booking_access),
):
    """Record a user-reported payment without claiming provider confirmation."""
    route = pipeline.record_payment_report(req.route_id, req.order_no)
    if route is None:
        raise HTTPException(status_code=404, detail="Route not found")
    return route


@app.get("/booking/routes")
def booking_routes(_: None = Depends(require_booking_access)):
    """List operator-only payment-checkpoint audit records."""
    return db.list_routes()


# --------------------------------------------------------------------------- #
# Legacy booking paths retained as protected not-implemented responses.
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
    # One-time traveler identity for the provider request (never persisted).
    id_number: str = ""
    name: str | None = None
    phone: str | None = None


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
def auto_hotel(
    req: AutoBookHotelRequest,
    _: None = Depends(require_booking_access),
):
    """Auto-book a Ctrip hotel through the real payment checkpoint.

    Drives a stealth browser with stored Ctrip cookies to the payment step and
    returns a ``pending_payment`` report. This is honest automation: it leaves
    the final payment confirmation to the human traveler and never claims an
    order was placed when it was not.
    """
    confirm = BookingConfirmRequest(
        id_number=req.id_number,
        name=req.name,
        phone=req.phone,
        hotel=HotelSelection(
            id=req.hotel_id,
            name=req.hotel_name,
            url=req.hotel_url,
            room_type=req.room_type,
            price_total=req.price_total,
            currency=req.currency,
        ),
        check_in=req.check_in,
        check_out=req.check_out,
        rooms=req.rooms,
        adults=req.adults,
        children=req.children,
        payment_method=req.payment_method,
    )
    return pipeline.confirm_booking(confirm)


@app.post("/booking/auto/flight")
def auto_flight(
    req: AutoBookFlightRequest,
    _: None = Depends(require_booking_access),
):
    """A provider-confirmed flight purchase is not implemented."""
    raise HTTPException(
        status_code=501,
        detail="Flight results are for comparison only. Complete the purchase with the provider.",
    )


@app.post("/booking/auto/train")
def auto_train(
    req: AutoBookTrainRequest,
    _: None = Depends(require_booking_access),
):
    """A provider-confirmed 12306 ticket purchase is not implemented."""
    raise HTTPException(
        status_code=501,
        detail="Train results are for comparison only. Complete identity verification and purchase in 12306.",
    )


@app.post("/booking/auto/restaurant")
def auto_restaurant(
    req: AutoBookRestaurantRequest,
    _: None = Depends(require_booking_access),
):
    """A provider-confirmed restaurant reservation is not implemented."""
    raise HTTPException(
        status_code=501,
        detail="Restaurant suggestions are for comparison only. Reserve with the restaurant or provider.",
    )


@app.post("/booking/credentials")
def save_credentials(
    req: StoreCredentialsRequest,
    _: None = Depends(require_booking_access),
):
    """Credential persistence is intentionally disabled to protect traveler PII."""
    raise HTTPException(
        status_code=410,
        detail=(
            "G3TA no longer stores passport/ID and phone credentials. "
            "Supply them only to an authenticated, one-time provider request."
        ),
    )


# --------------------------------------------------------------------------- #
# Result persistence (cookie-backed) — saved plans survive reloads
# --------------------------------------------------------------------------- #

RESULTS_DIR = Path(__file__).resolve().parent / "data" / "results"


class SaveResultRequest(BaseModel):
    result: dict
    input: dict | None = None
    trip_id: str | None = None


@app.post("/api/results/save")
async def save_result(payload: SaveResultRequest, response: Response):
    """Persist a generated plan so it can be reopened from the landing page.

    Returns a ``trip_id`` and sets a ``g3ta_trip_id`` cookie so the next visit
    shows the previous plan unless the user regenerates a new one.
    """
    trip_id = payload.trip_id or uuid4().hex
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{trip_id}.json"
    data = {
        "trip_id": trip_id,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "input": payload.input,
        "result": payload.result,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    response.set_cookie(
        key="g3ta_trip_id",
        value=trip_id,
        max_age=60 * 60 * 24 * 30,
        httponly=False,
        samesite="lax",
    )
    return {"trip_id": trip_id, "saved": True}


@app.get("/api/results/load")
async def load_result(trip_id: str = Query(...)):
    """Load a previously saved plan by its trip_id."""
    path = RESULTS_DIR / f"{trip_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No saved result for this trip_id.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/results/latest")
async def latest_result():
    """Return the most recently saved plan (for the landing page)."""
    if not RESULTS_DIR.exists():
        raise HTTPException(status_code=404, detail="No saved results yet.")
    files = sorted(RESULTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise HTTPException(status_code=404, detail="No saved results yet.")
    with open(files[0], encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# Ctrip cookies + real hotel images (Playwright scraping)
# --------------------------------------------------------------------------- #

class SaveCookiesRequest(BaseModel):
    cookie_string: str = ""


@app.post("/booking/cookies")
def save_cookies(
    payload: SaveCookiesRequest,
    _: None = Depends(require_booking_access),
):
    """Persist Ctrip session cookies so auto-booking can reuse a login.

    Paste the cookie header string copied from Ctrip DevTools
    (Application → Cookies → copy as ``name=value;`` pairs).
    """
    if not payload.cookie_string.strip():
        raise HTTPException(status_code=400, detail="cookie_string is required")
    try:
        summary = ctrip.save_ctrip_cookies(payload.cookie_string)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok", **summary}


class HotelImagesRequest(BaseModel):
    url: str = ""
    hotel_id: str = ""
    max_images: int = 6


@app.post("/booking/hotel-images")
def hotel_images(payload: HotelImagesRequest):
    """Scrape real hotel gallery image URLs from Ctrip (read-only)."""
    url = payload.url
    if not url and payload.hotel_id:
        url = f"https://hotels.ctrip.com/hotels/{payload.hotel_id}.html"
    if not url:
        raise HTTPException(status_code=400, detail="url or hotel_id required")
    images = ctrip.scrape_hotel_images(url, headless=True, max_images=payload.max_images)
    return {"url": url, "images": images, "count": len(images)}


# --------------------------------------------------------------------------- #
# Search-first booking endpoints — show top results before customer commits
# --------------------------------------------------------------------------- #

@app.post("/booking/search/flights")
def search_flights_endpoint(req: FlightSearchRequest):
    """Search flights and return comparison results for provider-side purchase."""
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
    """Search 12306 trains and return comparison results for provider-side purchase."""
    return search_trains(
        origin_station=req.origin_station,
        dest_station=req.dest_station,
        depart_date=req.depart_date,
    )


@app.post("/booking/book-flight-by-index")
def book_flight_index(
    req: BookFlightByIndexRequest,
    _: None = Depends(require_booking_access),
):
    """Legacy shortcut retained without claiming that a flight was purchased."""
    raise HTTPException(
        status_code=501,
        detail="Choose a search result, then complete the purchase with the provider.",
    )


class FinalizeRequest(BaseModel):
    trip: TripInput
    adjusted_budget: dict | None = None
    existing_result: dict | None = None


class TogglePackedRequest(BaseModel):
    trip_id: str = Field(min_length=8, max_length=100)
    is_packed: bool = True


# --------------------------------------------------------------------------- #
# Checklist API — read / update shared_checklist from the frontend
# --------------------------------------------------------------------------- #

@app.get("/api/checklist/{trip_id}")
def get_checklist(trip_id: str):
    """Return all checklist items for a trip with their is_packed status."""
    try:
        items = get_checklist_by_trip(trip_id)
        return {"trip_id": trip_id, "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load checklist: {e}")


@app.put("/api/checklist/{item_id}")
def toggle_checklist_item(item_id: int, req: TogglePackedRequest):
    """Set a checklist item's is_packed status (1 = packed, 0 = unpacked)."""
    try:
        updated = set_checklist_packed(item_id, req.trip_id, req.is_packed)
        if not updated:
            raise HTTPException(status_code=404, detail="Checklist item not found for this trip")
        return {"id": item_id, "trip_id": req.trip_id, "is_packed": req.is_packed}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update checklist item: {e}")


@app.post("/plan/finalize")
def plan_finalize(req: FinalizeRequest):
    """Save reviewed budget targets without repeating provider/LLM research."""
    try:
        if req.existing_result is not None:
            result = json.loads(json.dumps(req.existing_result, ensure_ascii=False))
            if req.adjusted_budget:
                safe_targets = {}
                for key, value in req.adjusted_budget.items():
                    if isinstance(value, bool):
                        continue
                    try:
                        numeric = max(float(value), 0)
                    except (TypeError, ValueError):
                        continue
                    safe_targets[str(key)] = round(numeric, 2)
                result["budget_targets"] = safe_targets
                result.setdefault("reasoning_log", []).append({
                    "agent": "Traveler review",
                    "note": (
                        "Saved the traveler's preferred category targets without rerunning "
                        "provider searches. Existing quoted and estimated costs were not rewritten."
                    ),
                })
            return result

        # Compatibility path for API clients that do not send the reviewed
        # result yet. The web frontend always uses the no-rerun path above.
        trip_input = req.trip.model_dump()
        if req.adjusted_budget:
            trip_input["_budget_override"] = req.adjusted_budget
        return orchestrator.plan(trip_input)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/api/hotel-amenities")
def hotel_amenities(location: str, hotel_name: str = ""):
    """Check hotel amenities (toothbrush, toothpaste, lotion etc.) via Ctrip scraping.

    Returns a list of amenities found for the specified hotel/location.
    Useful for knowing what toiletries to pack.
    """
    try:
        from services.hotel_amenities_service import check_amenities
        return check_amenities(location, hotel_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Amenities check failed: {e}")


@app.post("/plan/stream")
def plan_stream(trip: TripInput):
    """Stream the canonical transport-first six-agent planning pipeline."""
    return _plan_stream_response(trip)


@app.post("/plan/cancel/{request_id}")
def cancel_plan(request_id: str):
    """Request cooperative cancellation of one streamed plan."""
    if not cancel_active_plan(request_id):
        raise HTTPException(status_code=404, detail="Active planning request not found")
    return {"request_id": request_id, "status": "cancelling"}


def _plan_stream_response(
    trip: TripInput,
    *,
    pipeline_version: str | None = None,
) -> StreamingResponse:
    trip_input = orchestrator.prepare_trip_input(trip.model_dump())
    request_id = trip_input.get("request_id") or trip.request_id
    trip_input["request_id"] = request_id
    cancel_event = register_plan(request_id)
    trip_input["_cancel_event"] = cancel_event
    try:
        max_plan_seconds = max(float(_os.getenv("PLAN_MAX_SECONDS", "300")), 30)
    except ValueError:
        max_plan_seconds = 300

    def generate():
        outputs = {}
        shared = dict(trip_input)
        deadline = time.monotonic() + max_plan_seconds

        def ensure_active():
            if cancel_event.is_set():
                raise PlanningCancelled("Trip planning was cancelled.")
            if time.monotonic() >= deadline:
                cancel_event.set()
                raise RuntimeError(
                    f"Planning exceeded the {int(max_plan_seconds)} second limit. "
                    "Completed provider results remain cached; please retry."
                )

        def run_with_progress(name: str, agent_input: dict, initial_detail: str):
            """Run a blocking agent without leaving the SSE stream silent."""
            progress = {"detail": initial_detail}

            def update_progress(detail: str):
                progress["detail"] = detail

            worker_input = {**agent_input, "_progress_callback": update_progress}
            started = time.monotonic()
            last_detail = None
            last_elapsed = -1
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(orchestrator.run_single_agent, name, worker_input)
            try:
                while not future.done():
                    try:
                        ensure_active()
                    except Exception:
                        future.cancel()
                        raise
                    elapsed = int(time.monotonic() - started)
                    detail = progress["detail"]
                    if detail != last_detail or elapsed - last_elapsed >= 2:
                        yield _sse({
                            "type": "agent_progress",
                            "agent": name,
                            "detail": detail,
                            "elapsed_seconds": elapsed,
                        })
                        last_detail = detail
                        last_elapsed = elapsed
                    try:
                        future.result(timeout=1)
                    except FutureTimeoutError:
                        pass
                return future.result()
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

        try:
            # Transportation must complete before Budget so the allocation is
            # grounded in an actual route cost.
            yield _sse({"type": "agent_start", "agent": "transportation"})
            outputs["transportation"] = yield from run_with_progress(
                "transportation",
                shared,
                "正在启动交通数据查询",
            )
            shared["_transport_cost"] = float(outputs["transportation"].get("cost", 0) or 0)
            shared["_transport_scope"] = outputs["transportation"].get("scope", "national")
            yield _sse({
                "type": "agent_done",
                "agent": "transportation",
                "output": outputs["transportation"],
            })

            yield _sse({"type": "agent_start", "agent": "budget"})
            outputs["budget"] = yield from run_with_progress(
                "budget",
                shared,
                "正在读取交通成本并准备预算",
            )
            shared = orchestrator.with_budget_guidance(shared, outputs["budget"])
            shared["_budget_allocations"] = outputs["budget"].get("allocations", {})
            yield _sse({
                "type": "agent_done",
                "agent": "budget",
                "output": outputs["budget"],
            })

            yield _sse({"type": "agent_start", "agent": "activity"})
            yield _sse({"type": "agent_start", "agent": "housing"})
            progress = {
                "activity": {"detail": "正在启动景点查询"},
                "housing": {"detail": "正在启动住宿查询"},
            }
            started = {
                "activity": time.monotonic(),
                "housing": time.monotonic(),
            }

            def parallel_input(name: str):
                worker_input = dict(shared)
                worker_input["_progress_callback"] = (
                    lambda detail, agent=name: progress[agent].update(detail=detail)
                )
                return worker_input

            executor = ThreadPoolExecutor(max_workers=2)
            try:
                future_names = {
                    executor.submit(
                        orchestrator.run_single_agent,
                        name,
                        parallel_input(name),
                    ): name
                    for name in ("activity", "housing")
                }
                pending = set(future_names)
                last_sent = {"activity": ("", -1), "housing": ("", -1)}
                while pending:
                    try:
                        ensure_active()
                    except Exception:
                        for future in pending:
                            future.cancel()
                        raise
                    done, pending = wait(
                        pending,
                        timeout=1,
                        return_when=FIRST_COMPLETED,
                    )
                    for future in done:
                        name = future_names[future]
                        outputs[name] = future.result()
                        yield _sse({
                            "type": "agent_done",
                            "agent": name,
                            "output": outputs[name],
                        })
                    for future in pending:
                        name = future_names[future]
                        elapsed = int(time.monotonic() - started[name])
                        detail = progress[name]["detail"]
                        previous_detail, previous_elapsed = last_sent[name]
                        if detail != previous_detail or elapsed - previous_elapsed >= 2:
                            yield _sse({
                                "type": "agent_progress",
                                "agent": name,
                                "detail": detail,
                                "elapsed_seconds": elapsed,
                            })
                            last_sent[name] = (detail, elapsed)
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

            shared["_activity_meal_slots"] = outputs["activity"].get(
                "meal_slot_handoff", {}
            )
            shared["_activity_outputs"] = outputs["activity"].get("recommended", [])
            housing_recommendation = outputs["housing"].get("recommended") or {}
            shared["_hotel_name"] = housing_recommendation.get("name", "")
            shared["_housing_data"] = outputs["housing"]

            yield _sse({"type": "agent_start", "agent": "food"})
            outputs["food"] = yield from run_with_progress(
                "food",
                shared,
                "正在启动餐厅查询",
            )
            yield _sse({
                "type": "agent_done",
                "agent": "food",
                "output": outputs["food"],
            })

            yield _sse({"type": "agent_start", "agent": "planning"})
            outputs["planning"] = yield from run_with_progress(
                "planning",
                shared,
                "正在整理天气、节奏与行李",
            )
            yield _sse({
                "type": "agent_done",
                "agent": "planning",
                "output": outputs["planning"],
            })

            yield _sse({"type": "agent_start", "agent": "orchestrator"})
            yield _sse({
                "type": "agent_progress",
                "agent": "orchestrator",
                "detail": "正在合并全部建议并检查冲突",
                "elapsed_seconds": 0,
            })
            synthesis_started = time.monotonic()
            executor = ThreadPoolExecutor(max_workers=1)
            synthesis = executor.submit(
                    orchestrator.reconcile_and_synthesize,
                    shared,
                    outputs,
                )
            try:
                last_elapsed = 0
                while not synthesis.done():
                    try:
                        ensure_active()
                    except Exception:
                        synthesis.cancel()
                        raise
                    try:
                        synthesis.result(timeout=1)
                    except FutureTimeoutError:
                        elapsed = int(time.monotonic() - synthesis_started)
                        if elapsed - last_elapsed >= 2:
                            yield _sse({
                                "type": "agent_progress",
                                "agent": "orchestrator",
                                "detail": "正在合并全部建议并检查冲突",
                                "elapsed_seconds": elapsed,
                            })
                            last_elapsed = elapsed
                result = synthesis.result()
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
            result["trip_id"] = trip_input["trip_id"]
            if pipeline_version:
                result["pipeline_version"] = pipeline_version
            yield _sse({"type": "agent_done", "agent": "orchestrator"})
            yield _sse({"type": "complete", "result": result})
        except PlanningCancelled:
            yield _sse({"type": "cancelled", "request_id": request_id})
        except RuntimeError as e:
            yield _sse({"type": "error", "message": str(e)})
        except Exception as e:  # noqa: BLE001 — surface anything else to the UI
            yield _sse({"type": "error", "message": f"Unexpected error: {e}"})
        finally:
            # A browser refresh or closed tab stops iterating this generator.
            # Signal any still-running provider worker before dropping the
            # registry entry so abandoned work does not continue silently.
            cancel_event.set()
            finish_plan(request_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Keep the existing v2 routes as compatibility aliases. They now delegate to
# the canonical transport-first orchestrator instead of a second implementation.
@app.post("/plan/v2")
def plan_v2(trip: TripInput):
    try:
        result = orchestrator.plan(trip.model_dump())
        result["pipeline_version"] = "v2_transport_first"
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/plan/stream/v2")
def plan_stream_v2(trip: TripInput):
    return _plan_stream_response(trip, pipeline_version="v2_transport_first")


# A production image can copy ``frontend/dist`` beside the backend. API routes
# above keep priority; all other paths fall back to the Vite SPA.
if _FRONTEND_DIST.is_dir():
    assets = _FRONTEND_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")

    @app.get("/{frontend_path:path}", include_in_schema=False)
    def frontend_fallback(frontend_path: str):
        first_segment = frontend_path.split("/", 1)[0]
        if first_segment in {
            "agents",
            "api",
            "booking",
            "docs",
            "health",
            "intake",
            "openapi.json",
            "plan",
            "redoc",
            "speech",
        }:
            raise HTTPException(status_code=404, detail="API route not found")
        candidate = (_FRONTEND_DIST / frontend_path).resolve()
        try:
            candidate.relative_to(_FRONTEND_DIST.resolve())
        except ValueError:
            raise HTTPException(status_code=404, detail="Not found")
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")
