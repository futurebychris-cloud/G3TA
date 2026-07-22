# Planning Agent (OpenWeather variant) — standalone, not yet wired in

A second, more fleshed-out implementation of the Planning Agent's packing-list
responsibility, built independently against a spec that predates this repo's
actual `budget_agent`/`activity_agent` output shapes. It is **not** imported by
`orchestrator.py` or `main.py` — it's dropped here for a teammate to reconcile
with `planning_agent.py` / `planning_agent_v2.py` (see the note in
`docs/AGENT_HANDOFF.md`).

## What it does differently from `planning_agent_v2.py`

- Weather: OpenWeather (`OPENWEATHER_API_KEY` in root `.env`) instead of Open-Meteo.
- Interface: a FastAPI app with Pydantic request/response models
  (`planning_agent/api.py`, `planning_agent/models.py`), not a
  `run(trip_input: dict) -> dict` function. It runs as its own process/port.
- Output: 5 checklist categories (items, clothing, supportive, legal, devices)
  PLUS a flattened `packing_list` (every item tagged with its source category)
  and a `packing_summary` (`total_items`/`checked_items`/`remaining_items`) —
  see `PlanningResponse` in `planning_agent/models.py`.
- Persistence: one JSON file per trip in `data/` (gitignored), not the shared
  `booking/shared_db.py` SQLite database the rest of the backend uses.
- Checkbox state: `PATCH /plan/{trip_id}/check-item` toggles an item and keeps
  the per-category list and the flattened `packing_list` in sync.

## Known gaps to resolve before wiring this in

- `budget_agent.run()` returns `daily_caps` (food/activity/housing/local_transport),
  not `leftover`/`shopping_budget`. This module's `ITEMS` category (budget-constrained
  activity equipment) expects the latter — there's no real source for it yet.
- `activity_agent.run()` returns `recommended` (bookable activities), not an
  equipment/gear list. This module's `ActivityAgentOutput.items` input has no
  real producer today.
- To fold this into the `run(trip_input) -> dict` convention, the entry point
  would be `PlanningAgent.generate_plan()` in `planning_agent/agent.py` — it
  takes a `PlanningRequest` (see `models.py`) rather than the shared `trip_input`
  dict, so a thin adapter function is the missing piece, not a rewrite.

## Running it standalone

```bash
cd backend/agents/planning_openweather
pip install -r ../../requirements.txt   # fastapi, pydantic, python-dotenv already there; adds `requests`
uvicorn planning_agent.api:app --reload --port 8003
```

Reads `OPENWEATHER_API_KEY` from the repo root `.env` (see `.env.example`).

```bash
curl -X POST http://127.0.0.1:8003/plan -H "Content-Type: application/json" -d '{
  "trip_id": "demo-001",
  "user_profile": {
    "destination_city": "Tokyo", "destination_country": "Japan", "origin_country": "United States",
    "trip_start_date": "2026-08-01", "trip_end_date": "2026-08-05",
    "residency_status": "citizen", "hotel_amenities": ["towel"], "device_list": ["phone"]
  },
  "activity_output": {"items": [{"name": "snorkel mask", "estimated_cost": 25, "required": true}]},
  "budget_output": {"leftover": 50, "shopping_budget": 100},
  "preference": {"usability": 0.7, "entertainment": 0.3}
}'
```
