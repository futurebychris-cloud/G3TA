"""FastAPI app for the multi-agent trip planner.

Endpoints:
    GET  /                 health check
    POST /agents/{name}    run one specialist agent (modularity / debugging)
    POST /plan             run the full orchestration, return the final itinerary
    POST /plan/stream      same, but stream per-agent progress as Server-Sent Events

Run from the backend/ directory:
    uvicorn main:app --reload
"""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Load the nearest .env by walking up from the backend/ working dir, so a single
# .env at the repo root (copied from .env.example) is picked up. DEEPSEEK_API_KEY etc.
load_dotenv(find_dotenv(usecwd=True))

from agents import AGENT_ORDER  # noqa: E402
import orchestrator  # noqa: E402

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


class TripInput(BaseModel):
    location: str
    origin: str = "New York"
    dates: Dates
    budget: Budget
    preferences: Preferences = Field(default_factory=Preferences)
    time_constraints: str = ""


@app.get("/")
def health():
    return {"status": "ok", "service": "trip-planner", "agents": AGENT_ORDER}


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


@app.post("/plan/stream")
def plan_stream(trip: TripInput):
    """Run agents one at a time and stream progress so the UI can show a live checklist."""
    trip_input = trip.model_dump()

    def generate():
        outputs = {}
        try:
            for name in AGENT_ORDER:
                yield _sse({"type": "agent_start", "agent": name})
            with ThreadPoolExecutor(max_workers=len(AGENT_ORDER)) as executor:
                futures = {
                    executor.submit(orchestrator.run_single_agent, name, trip_input): name
                    for name in AGENT_ORDER
                }
                for future in as_completed(futures):
                    name = futures[future]
                    outputs[name] = future.result()
                    yield _sse({"type": "agent_done", "agent": name, "output": outputs[name]})

            yield _sse({"type": "agent_start", "agent": "orchestrator"})
            result = orchestrator.reconcile_and_synthesize(trip_input, outputs)
            yield _sse({"type": "agent_done", "agent": "orchestrator"})
            yield _sse({"type": "complete", "result": result})
        except RuntimeError as e:
            yield _sse({"type": "error", "message": str(e)})
        except Exception as e:  # noqa: BLE001 — surface anything else to the UI
            yield _sse({"type": "error", "message": f"Unexpected error: {e}"})

    return StreamingResponse(generate(), media_type="text/event-stream")
