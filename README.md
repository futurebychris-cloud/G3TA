# G3TA Multi-Agent Trip Planner

G3TA is an NYU Shanghai team project that turns one reviewed trip brief into a
day-by-day itinerary. Six specialist agents share a single trip ID, exchange
structured handoffs, and expose their progress in an Agent Town interface.

DeepSeek supplies reasoning where needed. AMap powers the interactive route
view. Provider records are preferred when available, while estimates and
repository snapshots are labeled separately.

## Current capabilities

- Voice-or-text trip drafting followed by a normal editable form.
- Transport-first orchestration with visible per-agent progress.
- Destination and date guards that reject stale data from another trip.
- AMap places, walking/driving routes, and a gradual route-reveal animation.
- Day-by-day itinerary, budget review, packing checklist, weather, and agent log.
- Hotel comparison that sends the traveler to the provider to verify and book.
- Piper English/Mandarin read-aloud with no operating-system voice fallback.
- Standard, Easy Reading, Senior Mode, Voice First, high contrast, reduced
  motion, larger text, and line-focus controls.
- Cooperative cancellation, a configurable overall planning deadline, provider
  caching, backend/frontend tests, CI, and a production container build.

## Truth and safety boundaries

- Planning is read-only. Generating a route never starts a booking or submits
  traveler information.
- Activity, meal, and transportation database rows start as `pending`, not
  `confirmed`.
- Flight, train, hotel, and restaurant availability must be verified with the
  provider before purchase.
- Offline mock search data is allowed only with `ALLOW_MOCK_RESULTS=1` and is
  labeled `mock`. Mock mode never creates an order number or payment state.
- Repository provider snapshots are disabled by default. If explicitly enabled,
  they contain public, slowly changing metadata only—never current prices,
  schedules, weather, availability, cookies, secrets, or personal information.
- Passport/ID and phone fields are no longer collected by the public frontend or
  persisted by the normal planning pipeline.
- Legacy provider-browser experiments are disabled by default, protected by an
  operator token, and return `501 Not Implemented` for unsupported purchase flows.
- This remains a local/team demo, not a production multi-user service. Put any
  public deployment behind real user authentication, rate limits, HTTPS, and
  provider-compliant integrations.

## Canonical pipeline

```text
Trip brief
   │
   ▼
Transportation ── actual/estimated route cost ──► Budget
                                                   │
                              ┌────────────────────┴───────────────────┐
                              ▼                                        ▼
                         Activity                                  Housing
                              └────────────────────┬───────────────────┘
                                                   ▼
                                                 Food
                                                   ▼
                                               Planning
                                                   ▼
                                            Lead orchestrator
                                                   ▼
                                    itinerary + map + provenance
```

The actual order is:

1. Transportation
2. Budget
3. Activity and Housing in parallel
4. Food
5. Planning
6. Lead orchestrator synthesis

## Data sources

| Area | Preferred source | Honest fallback |
|---|---|---|
| Transportation | 12306 public query, Ctrip public pages | clearly labeled destination-aware estimate |
| Local routes and POIs | AMap Web Service / JS API; OSRM where used | no fabricated route |
| Housing | configured hotel API; Ctrip listing when an authenticated local session is available | planning omits lodging cost; explicit comparison may show an OpenStreetMap place record without a live price |
| Food | AMap POIs, optional public search | labeled estimate |
| Activities | known-place catalog; optional public browser search | labeled deterministic recommendation |
| Weather | Open-Meteo forecast | labeled prior-year climate proxy outside forecast coverage |
| Speech | local Piper service | text remains available; no hidden system-voice fallback |

Every final result includes `data_provenance` and a verification notice. “Live”
means directly queried provider/public records, not guaranteed inventory or a
confirmed reservation.

## Project layout

```text
.
├── backend/
│   ├── main.py                    FastAPI routes and SSE planning stream
│   ├── orchestrator.py            handoffs, guards, reconciliation, synthesis
│   ├── plan_runtime.py            cancellation lifecycle
│   ├── security.py                local CORS and booking boundary
│   ├── agents/                    six specialist agents
│   ├── services/                  provider adapters, AMap, weather, Piper proxy
│   ├── booking/                   comparison and operator-only experiments
│   ├── data/                      optional sanitized provider metadata snapshots
│   └── tests/
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── components/            form, Agent Town, map, itinerary, accessibility
│       ├── hooks/
│       └── lib/amap.js
├── piper/                         local TTS container
├── docs/AGENT_HANDOFF.md
├── Dockerfile
└── docker-compose.yml
```

## Local setup

### 1. Environment files

```bash
cp .env.example .env
```

At minimum, set:

```dotenv
DEEPSEEK_API_KEY=...
GAODE_KEY=...                 # AMap Web Service key used by the backend
```

For the browser map, create an ignored repository-root `.env.local`:

```dotenv
VITE_AMAP_KEY=...             # AMap Web JS API 2.0 key
VITE_AMAP_SECURITY_CODE=...   # matching JS security code
```

The Web Service key and Web JS key are different AMap service types. Restrict
the browser key to the exact localhost/production domains in the AMap console.
Never commit `.env` or `.env.local`. Any key that has appeared in Git history
must be rotated.

### 2. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Health check: `http://127.0.0.1:8000/health`

### 3. Frontend

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173`.

### 4. Piper read-aloud

```bash
docker build -t g3ta-piper:latest ./piper
docker run -d --name g3ta-piper -p 127.0.0.1:8083:8080 g3ta-piper:latest
```

Piper health check: `http://127.0.0.1:8083/health`

### One-command container setup

After creating `.env`:

```bash
docker compose up --build
```

The compose ports bind to localhost only. The production image builds the
frontend and serves it through FastAPI at `http://127.0.0.1:8000`.

## Tests

```bash
cd backend
.venv/bin/python -m pytest -q
python _smoke_test.py

cd ../frontend
npm test -- --run
npm run build
```

GitHub Actions runs the backend suite plus frontend tests and build.

## Main API routes

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | configuration status without secret values |
| `POST` | `/intake/parse` | convert a description into a reviewable form draft |
| `POST` | `/speech/synthesize` | proxy text to Piper and return WAV audio |
| `POST` | `/plan/stream` | canonical SSE planning flow |
| `POST` | `/plan/cancel/{request_id}` | cancel one active streamed plan |
| `POST` | `/plan/finalize` | save reviewed budget targets without rerunning agents |
| `POST` | `/agents/{name}` | run one agent for local debugging |
| `POST` | `/booking/search` | compare hotel sources; no purchase |
| `POST` | `/booking/search/flights` | compare flight results; no purchase |
| `POST` | `/booking/search/trains` | compare train results; no purchase |
| `GET/PUT` | `/api/checklist/...` | read/update one trip’s packing state |

Operator-only legacy routes under `/booking/confirm`, `/booking/mark_paid`,
`/booking/routes`, and `/booking/auto/*` require
`BOOKING_AUTOMATION_ENABLED=1` (now **enabled by default** in this release) and
`X-G3TA-Booking-Token`. When enabled, the `/booking/auto/*` endpoints run real
Playwright browser flows: hotel drives to a `pending_payment` checkout
checkpoint, while flight/train/restaurant select/prefill and return
`manual_required` with a provider link to finish identity verification/payment.
None of them fabricate an order or payment state.

## Optional provider cache and snapshots

Slow read-only lookups use a short in-process cache. A hosted PostgreSQL
`DATABASE_URL` can persist provider cache entries; local SQLite is used only for
ordinary shared planning data.

To export sanitized, Git-friendly public metadata:

```bash
cd backend
PYTHONPATH=. .venv/bin/python scripts/export_provider_snapshots.py
```

To allow those non-live snapshots during an explicit offline demo:

```dotenv
G3TA_ALLOW_PROVIDER_SNAPSHOTS=1
```

The separate `scripts/scrape_travel_providers.py` collector records structured
success/empty/blocked outcomes and stops at login, CAPTCHA, or risk-control
pages. It is not part of the interactive planning request and refuses to store
results without a remote PostgreSQL database.

## Team handoff

Read [docs/AGENT_HANDOFF.md](docs/AGENT_HANDOFF.md) before changing an agent
contract. Keep provider-specific logic inside `backend/services/`, keep
destination/date fields in every cache key, and add a test whenever a handoff or
truthfulness label changes.
