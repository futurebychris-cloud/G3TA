# Multi-Agent AI Trip Planner

> NYU Shanghai AI Pre-College final project — a **base plate** for the team build.
> Six specialist AI agents + an orchestrator turn a single trip request into a
> complete, auditable itinerary. Until live provider APIs are connected, DeepSeek
> generates destination-specific planning estimates that are explicitly marked for verification.

**LLM:** DeepSeek (`deepseek-chat`, OpenAI-compatible endpoint).

---

## What it does

You enter a destination, dates, budget, and preferences. Six agents each own one
domain. The Budget Agent runs first so its category caps guide the other five
agents, which then run concurrently; an **Orchestrator** merges their
outputs into one day-by-day itinerary:

| Agent | Owns | Current data source |
|---|---|---|
| Budget | per-category daily caps, overspend warnings | DeepSeek destination estimate |
| Transportation | route recommendation within budget | DeepSeek route estimate |
| Housing | lodging recommendation | DeepSeek destination estimate |
| Food | day-by-day meals matching cuisine prefs | DeepSeek destination estimate |
| Activity | distinct activities matching style prefs | DeepSeek destination estimate |
| Planning | packing list, seasonal weather, pacing | DeepSeek seasonal estimate |

The demo-able insight (PRD §13): when the combined plan **breaks the budget**, the
Orchestrator downgrades lodging and records *why* in a **reasoning log** you can
point at. A geography guard rejects outputs for the wrong destination, and schedule
validation prevents repeated or invented activities from reaching the UI.

> **Accuracy note:** DeepSeek does not provide live inventory. Prices, schedules,
> availability, opening hours, coordinates, and named venues must be verified before
> booking. Each generated record and final itinerary carries this warning. Connect real
> provider APIs under `backend/services/` when keys become available.

> **Scope note:** This is a one-shot orchestrator/worker pipeline, **not** an
> AI-Town-style persistent simulation. See PRD §14 for the gap analysis and the
> recommended extension path before adding memory/reflection/multi-day loops.

---

## Project layout

```
├── README.md                ← you are here
├── .env.example             ← copy to .env, add your DeepSeek key
├── frontend/                ← React (Vite) wizard: form → progress → result
│   └── src/components/       InputForm, ProgressTracker, ItineraryView, MapView, BudgetView, PackingList, ReasoningLog
├── backend/
│   ├── main.py               FastAPI app: /plan, /plan/stream, /agents/{name}
│   ├── orchestrator.py       runs 6 agents, reconciles budget, synthesizes itinerary
│   ├── agents/               the six specialist agents (each: input → service → DeepSeek → output)
│   ├── services/             ← THE SWAP POINT for real APIs (see below)
│   └── llm/deepseek_client.py single DeepSeek entry point
└── docs/AGENT_HANDOFF.md     exact input/output contract for every agent
```

---

## Setup

### 1. Keys

```bash
cp .env.example .env
# edit .env and set DEEPSEEK_API_KEY=...   (required — every agent calls DeepSeek)
```

### 2. Backend (Python 3.10+)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate    # optional but recommended
pip install -r requirements.txt
uvicorn main:app --reload                              # http://localhost:8000
```

Quick check: open http://localhost:8000/ → `{"status":"ok", ...}`.

### 3. Frontend (Node 18+)

```bash
cd frontend
npm install
npm run dev                                            # http://localhost:5173
```

Open http://localhost:5173, enter any destination, and watch the six agents run.

### Offline sanity check (no key needed)

`backend/_smoke_test.py` stubs the LLM to force the deterministic fallbacks and runs
the full orchestration for Shanghai and asserts that no retired Tokyo data leaks
into the result. It does not spend tokens:

```bash
cd backend && python3 _smoke_test.py
```

---

## Adding Real APIs

Every external data source is wrapped under `backend/services/`. Today those
services use destination-specific DeepSeek estimates. Replacing one with a live
API means editing that service while keeping its return shape; agent logic stays intact.

Set the matching key in `.env` (`FLIGHTS_API_KEY`, `HOTELS_API_KEY`, `WEATHER_API_KEY`,
`MAPS_API_KEY`, …), then replace the function body:

| Service function (file) | Signature | Must return |
|---|---|---|
| `flights_service.get_flight_options` | `(origin, destination, dates, budget=None, transport_types=None)` | `[{"id","carrier","mode","price","duration","departure_time","arrival_airport","stops"}]` |
| `hotels_service.get_hotel_options` | `(destination, dates, max_price_per_night=None, budget=None, preferences=None)` | `[{"id","name","price_per_night","rating","area","lat","lng","tags"}]` |
| `food_service.get_food_options` | `(destination, cuisine_tags=None, num_days=5, ...)` | `[{"id","name","cuisine","cuisine_family","price","meal_type","area","rating","tags"}]` |
| `activities_service.get_activity_options` | `(destination, activity_styles=None, requested_count=6, ...)` | `[{"id","name","style","price","duration","area","lat","lng","tags"}]` |
| `weather_service.get_weather` | `(destination, dates) -> dict` | `{"summary": str, "daily": [{"date","condition","high_c","low_c","rain_chance"}]}` |
| `budget_service.get_cost_index` | `(destination, origin="", dates=None, currency="USD")` | `{"currency","cost_level","daily_index":{"food","activity","housing","local_transport"},"flight_reference"}` |

Example (flights):

```python
# backend/services/flights_service.py
def get_flight_options(origin, destination, dates, budget=None, transport_types=None):
    # Replace the DeepSeek estimate with Amadeus/Skyscanner data, then map the
    # provider response into the existing normalized option shape.
    ...
```

Who owns which integration is an open team question (PRD §15) — coordinate before
claiming one.

---

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | health check + agent list |
| POST | `/agents/{name}` | run one agent (`budget`, `transportation`, `housing`, `food`, `activity`, `planning`) — handy for debugging |
| POST | `/plan` | run the full orchestration, return the final itinerary |
| POST | `/plan/stream` | same, streamed as Server-Sent Events so the UI shows live progress |

Request body for all of them is the trip input — see `docs/AGENT_HANDOFF.md`.

---

## For teammates / their AI agents

Start with **`docs/AGENT_HANDOFF.md`** — it's the exact input/output contract for
every agent and the Orchestrator. To add a real data source, you only need that
file plus the table above. To extend toward AI-Town-style behavior, read **PRD §14**
first.
