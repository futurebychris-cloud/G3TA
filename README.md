# Multi-Agent AI Trip Planner

> NYU Shanghai AI Pre-College final project — a **base plate** for the team build.
> Six specialist AI agents + an orchestrator turn a single trip request into a
> complete, auditable itinerary. The MVP runs on **mock data**; teammates swap in
> real APIs one file at a time without touching agent logic.

**LLM:** DeepSeek (`deepseek-chat`, OpenAI-compatible endpoint).

---

## What it does

You enter a destination, dates, budget, and preferences. Six agents each own one
domain and run in parallel-ish sequence, then an **Orchestrator** merges their
outputs into one day-by-day itinerary:

| Agent | Owns | Data source (MVP) |
|---|---|---|
| Budget | per-category daily caps, overspend warnings | `mock_budget_db.json` |
| Transportation | flight recommendation within budget | `mock_flights.json` |
| Housing | lodging recommendation | `mock_hotels.json` |
| Food | day-by-day meals matching cuisine prefs | `mock_food.json` |
| Activity | activities matching style prefs | `mock_activities.json` |
| Planning | packing list, weather, pacing | `mock_weather.json` |

The demo-able insight (PRD §13): when the combined plan **breaks the budget**, the
Orchestrator downgrades lodging and records *why* in a **reasoning log** you can
point at — e.g. *"Housing Agent's first pick 'Ginza Grand Luxe' broke the budget by
$691; substituted 'Asakusa View Ryokan' to fit."* That's the proof this is genuinely
multi-agent, not one prompt with extra UI.

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
│   ├── mocks/                static JSON demo data (Tokyo)
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

Open http://localhost:5173, hit **Plan my trip** (the form is pre-filled with the
Tokyo demo), and watch the six agents run.

### Offline sanity check (no key needed)

`backend/_smoke_test.py` stubs the LLM to force the deterministic fallbacks and runs
the full orchestration — useful to verify wiring and the budget-downgrade logic
without spending tokens:

```bash
cd backend && python3 _smoke_test.py
```

---

## Adding Real APIs

**This is the whole point of the base plate.** Every external data source is
wrapped in one function under `backend/services/`. Agents call **only** these
functions — never the mock files — so replacing a mock with a real API means
editing exactly one file and keeping the return shape. Nothing in `agents/` changes.

Set the matching key in `.env` (`FLIGHTS_API_KEY`, `HOTELS_API_KEY`, `WEATHER_API_KEY`,
`MAPS_API_KEY`, …), then replace the function body:

| Service function (file) | Signature | Must return |
|---|---|---|
| `flights_service.get_flight_options` | `(origin, destination, dates) -> list[dict]` | `[{"id","carrier","price","duration","departure_time","arrival_airport","stops"}]` |
| `hotels_service.get_hotel_options` | `(destination, dates, max_price_per_night=None) -> list[dict]` | `[{"id","name","price_per_night","rating","area","lat","lng","tags"}]` |
| `food_service.get_food_options` | `(destination, cuisine_tags=None) -> list[dict]` | `[{"id","name","cuisine","price","meal_type","area","rating","tags"}]` |
| `activities_service.get_activity_options` | `(destination, activity_styles=None) -> list[dict]` | `[{"id","name","style","price","duration","area","lat","lng","tags"}]` |
| `weather_service.get_weather` | `(destination, dates) -> dict` | `{"summary": str, "daily": [{"date","condition","high_c","low_c","rain_chance"}]}` |
| `budget_service.get_cost_index` | `(destination) -> dict` | `{"currency","cost_level","daily_index":{"food","activity","housing","local_transport"},"flight_reference"}` |

Example (flights):

```python
# backend/services/flights_service.py
def get_flight_options(origin, destination, dates) -> list[dict]:
    # BEFORE (MVP): return load_mock("mock_flights.json")["options"]
    # AFTER: call Amadeus/Skyscanner with os.getenv("FLIGHTS_API_KEY"),
    #        then map the provider's response into the shape above.
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
