# Multi-Agent AI Trip Planner

> NYU Shanghai AI Pre-College final project — a **base plate** for the team build.
> Six specialist AI agents + an orchestrator turn a single trip request into a
> complete, auditable itinerary. The v2 pipeline prefers live provider data and browser
> research, then uses clearly labeled estimates when a source is unavailable.

**LLM:** DeepSeek (`deepseek-chat`, OpenAI-compatible endpoint).

---

## What it does

You enter a destination, dates, budget, and preferences. Six agents each own one
domain. The Budget Agent runs first so its category caps guide the other five
agents, which then run concurrently; an **Orchestrator** merges their
outputs into one day-by-day itinerary:

| Agent | Owns | Current data source |
|---|---|---|
| Budget | per-category caps and overspend warnings | Cost index + browser research + DeepSeek reasoning |
| Transportation | intercity route and local mobility | Ctrip, 12306, Gaode/OSRM; labeled estimate fallback |
| Housing | real-priced lodging recommendation | Hotel APIs, Ctrip, then OpenStreetMap discovery |
| Food | day-by-day meals matching cuisine and caps | Google Maps research + normalized destination options |
| Activity | distinct activities and must-see choices | Ctrip/web research + verified-name attraction catalog |
| Planning | packing list, daily weather, pacing | Open-Meteo forecast + labeled seasonal fallback |

The demo-able insight (PRD §13): when the combined plan **breaks the budget**, the
Orchestrator downgrades lodging and records *why* in a **reasoning log** you can
point at. A geography guard rejects outputs for the wrong destination, and schedule
validation prevents repeated or invented activities from reaching the UI.

## Accessibility options

Use the **Accessibility** button in the top-right header to choose independent reading and
interaction tools. A first-run setup offers **Standard**, **Easy Reading**, **Senior Mode**, and
**Voice First** as optional starting points. Standard remains the default, and every setting can
still be changed independently after selecting a preset. Available options are:

- Easy Reading, Bigger Text, More Text Spacing, and High Contrast;
- Reduce Motion and a system-based reading font (`Arial, Verdana, Tahoma, sans-serif`);
- one-line or three-line Line Focus;
- Read Aloud controls with adjustable reading speed;
- browser voice input beside the destination field.

### Senior Mode

Senior Mode builds on the same accessibility settings; it does not create a separate theme or
duplicate the speech and reading systems. Selecting it enables Bigger Text, More Text Spacing,
High Contrast, Reduce Motion, Easy Reading, Read Aloud at `0.9×`, Reading Font, and three-line
Line Focus. Users can then override any one of those choices from the Accessibility panel.

In trip results, Senior Mode also provides larger touch targets and travel facts, a smaller set of
primary trip sections, and short **Top Recommendation**, **Best Value**, and **Closest** place
choices with a button to reveal the full list. It adds brief explanations for common travel terms,
a confirmation before leaving the current trip, one-tap Emergency Information, and a floating
**What do I do next?** helper. The emergency card labels missing provider data for verification;
it does not invent phone numbers, street addresses, or embassy details.

Read Aloud controls cover itinerary days, important flight and hotel events, directions, packing,
and emergency information. They only speak after the user presses a control. Senior Mode's Easy
Reading instructions and frontend formatting must never change dates, times, prices, locations,
routes, reservation details, or other factual travel data.

Settings are validated and stored together in browser `localStorage` under
`g3ta-accessibility-settings-v1`. If storage is blocked, they continue working for the current
session. **Reset to defaults** removes all selected presentation modes.

Voice input uses the browser Web Speech Recognition API and is mainly available in Chromium and
some Safari versions; it is generally unavailable in Firefox. Read Aloud uses the browser Speech
Synthesis API, whose voices and pause/resume behavior vary by browser and operating system. Both
features fail safely and keep normal typing and reading available. No paid speech service is used.

The optional reading font uses installed system fonts. OpenDyslexic is not downloaded or required.
Easy Reading always has deterministic frontend structure as a fallback. When its optional DeepSeek
prompt instruction is used, it explicitly requires every date, time, price, location, warning,
duration, flight number, and factual detail to remain unchanged and prohibits adding facts.

This feature set improves accessibility but is not a claim of complete WCAG conformance. Keyboard,
screen-reader, browser zoom, voice permission, and operating-system voice behavior should still be
reviewed manually in supported browsers.

> **Accuracy note:** Live sources can fail, change, or block automated access. DeepSeek
> does not provide live inventory. Verify every price, schedule, availability claim,
> opening hour, coordinate, and reservation with the provider before purchase. Flight,
> train, and restaurant selections are never labeled confirmed without provider proof.

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
│   ├── agents/               six v2 specialists with the stable v1 safety contracts
│   ├── booking/              hotel search, provider automation, and SQLite audit stores
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
python -m playwright install chromium                 # browser automation
uvicorn main:app --reload                              # http://localhost:8000
```

Quick check: open http://localhost:8000/ → `{"status":"ok", ...}`.

### 3. Frontend (Node 18+)

```bash
cd frontend
npm install
npm run dev                                            # http://localhost:5173
```

Open http://localhost:5173, enter any destination, and watch the Budget Agent establish
caps before the other five specialists run concurrently.

### Offline sanity check (no key needed)

`backend/_smoke_test.py` stubs the LLM to force the deterministic fallbacks and runs
the full orchestration for Shanghai and asserts that no retired Tokyo data leaks
into the result. It does not spend tokens:

```bash
cd backend && python3 _smoke_test.py
```

### Accessibility tests

The frontend uses Vitest, jsdom, and React Testing Library for settings and preset persistence,
first-run setup, dialog focus, keyboard behavior, accessible names, immediate-next-step formatting,
and speech fallbacks:

```bash
cd frontend
npm test
npm run build
```

Backend easy-reading factual-preservation and weather tests run with:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -v
```

---

## Adding Real APIs

External sources are normalized behind stable service and agent contracts. Weather geocodes
arbitrary destinations and requests up to 16 forecast days from Open-Meteo without an API key.
Dates outside that window, or requests made while Open-Meteo is unavailable, retain a clearly
labeled seasonal estimate. Replacing another service means editing that service while keeping
its return shape; agent logic stays intact.

Open-Meteo data is normalized into the app's daily schema and attributed in the result UI under
the [CC BY 4.0 licence](https://open-meteo.com/en/license). The free endpoint is for this
non-commercial educational demo; use an appropriate paid endpoint and key for commercial use.

Set the matching key in `.env` (`FLIGHTS_API_KEY`, `HOTELS_API_KEY`, `MAPS_API_KEY`, …),
then replace the function body. Open-Meteo does not require a key for this non-commercial demo:

| Service function (file) | Signature | Must return |
|---|---|---|
| `flights_service.get_flight_options` | `(origin, destination, dates, budget=None, transport_types=None)` | `[{"id","carrier","mode","price","duration","departure_time","arrival_airport","stops"}]` |
| `hotels_service.get_hotel_options` | `(destination, dates, max_price_per_night=None, budget=None, preferences=None)` | `[{"id","name","price_per_night","rating","area","lat","lng","tags"}]` |
| `food_service.get_food_options` | `(destination, cuisine_tags=None, num_days=5, ...)` | `[{"id","name","cuisine","cuisine_family","price","meal_type","area","rating","tags"}]` |
| `activities_service.get_activity_options` | `(destination, activity_styles=None, requested_count=6, ...)` | `[{"id","name","style","price","duration","area","lat","lng","tags"}]` |
| `weather_service.get_weather` | `(destination, dates) -> dict` | `{"summary","source","location","daily":[{"date","condition","high_c","low_c","rain_chance","precipitation_mm","snowfall_cm","wind_speed_max_kmh","uv_index_max","source"}]}` |
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
| POST | `/booking/search` | stream hotel discovery and filtering results |
| POST | `/booking/confirm` | attempt to reach Ctrip's verified payment checkpoint |
| POST | `/booking/mark_paid` | record the user's explicit payment confirmation |
| GET | `/booking/routes` | list the stored hotel-booking audit trail |
| POST | `/booking/search/flights` | show flight choices before any booking action |
| POST | `/booking/search/trains` | show train choices before any booking action |

Request body for all of them is the trip input — see `docs/AGENT_HANDOFF.md`.

---

## For teammates / their AI agents

Start with **`docs/AGENT_HANDOFF.md`** — it's the exact input/output contract for
every agent and the Orchestrator. To add a real data source, you only need that
file plus the table above. To extend toward AI-Town-style behavior, read **PRD §14**
first.
