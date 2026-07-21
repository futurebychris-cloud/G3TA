# Agent Handoff — Input/Output Contracts

This document is the source of truth for what each agent consumes and produces.
Read it before extending an agent or wiring a new data source. A teammate's own
AI coding agent should be able to work from this file alone.

Every agent exposes `run(trip_input: dict) -> dict` in `backend/agents/<name>_agent.py`.
Every agent reads its data through a destination-aware function in `backend/services/`.
Until real provider APIs are connected, those services generate DeepSeek estimates
and mark them `verification_required`. The Orchestrator is the only component that
sees all six outputs together and enforces destination isolation.

---

## Shared input (given to every agent)

```json
{
  "location": "Shanghai",
  "origin": "New York",
  "dates": { "start": "2026-04-10", "end": "2026-04-14" },
  "budget": { "total": 2500, "currency": "USD" },
  "preferences": {
    "bites": ["Thai", "American"],
    "transportation_type": ["flight"],
    "activity_style": ["cultural", "adventure"]
  },
  "time_constraints": "fixed dates"
}
```

`news`/`weather` are NOT user-entered — the Planning Agent pulls weather itself.

---

## 1. Budget Agent — `budget_agent.run(trip_input, overflow=None)`

- **Service:** `budget_service.get_cost_index(destination)`
- **Output:**
```json
{
  "daily_caps": { "food": 55, "activity": 45, "housing": 150, "local_transport": 15 },
  "warnings": ["Budget is tight: ..."],
  "reasoning": "…",
  "num_days": 5,
  "total_budget": 2500,
  "currency": "USD"
}
```
- `overflow` (float) is passed by the Orchestrator when the combined plan exceeds
  the budget; the agent then returns tightened caps and a trim warning.

## 2. Transportation Agent — `transportation_agent.run(trip_input)`

- **Service:** `flights_service.get_flight_options(origin, destination, dates)`
- **Output:**
```json
{
  "options": [ { "id", "carrier", "price", "duration", "departure_time", "arrival_airport", "stops" } ],
  "recommended": { "...one option..." },
  "cost": 690,
  "reasoning": "…"
}
```

## 3. Housing Agent — `housing_agent.run(trip_input)`

- **Service:** `hotels_service.get_hotel_options(destination, dates, max_price_per_night=None)`
- **Output:**
```json
{
  "options": [ { "id", "name", "price_per_night", "rating", "area", "lat", "lng", "tags" } ],
  "recommended": { "...one option..." },
  "nights": 4,
  "cost": 440,
  "reasoning": "…"
}
```
- The Orchestrator may **override** `recommended`/`cost` if the whole-trip budget
  overflows (records the substitution in `reasoning_log`).

## 4. Food Agent — `food_agent.run(trip_input)`

- **Service:** `food_service.get_food_options(destination, cuisine_tags=None)`
- **Output:**
```json
{
  "daily_meals": [
    { "date": "2026-04-10", "meals": [ { "slot", "name", "cuisine", "price", "area" } ] }
  ],
  "cost": 440,
  "reasoning": "…"
}
```

## 5. Activity Agent — `activity_agent.run(trip_input)`

- **Service:** `activities_service.get_activity_options(destination, activity_styles=None)`
- **Output:**
```json
{
  "recommended": [ { "id", "name", "style", "price", "duration", "area", "lat", "lng", "tags" } ],
  "cost": 312,
  "reasoning": "…"
}
```

## 6. Planning Agent — `planning_agent.run(trip_input)`

- **Service:** `weather_service.get_weather(destination, dates)`
- **Output:**
```json
{
  "packing_list": ["Warm jacket", "Compact umbrella", "…"],
  "weather_summary": "AI seasonal estimate for Shanghai: mild spring conditions …",
  "pacing_notes": "With 5 days, keep one flexible afternoon …",
  "daily_weather": [ { "date", "condition", "high_c", "low_c", "rain_chance" } ]
}
```

---

## Orchestrator — `orchestrator.plan(trip_input)`

Runs all six agents, reconciles the combined cost against the budget (re-queries
the Budget Agent and downgrades lodging on overflow), then makes one DeepSeek call
to synthesize the schedule. Final itinerary object:

```json
{
  "destination": "Shanghai",
  "dates": { "start": "...", "end": "..." },
  "summary": "…",
  "schedule": [ { "day": 1, "date": "2026-04-10", "title": "…", "items": [ { "time", "type", "title", "detail" } ] } ],
  "cost": {
    "currency": "USD", "total": 1737, "budget": 2500, "within_budget": true,
    "breakdown": { "transportation", "housing", "food", "activity", "local_transport" }
  },
  "map_points": [ { "label", "type", "area", "lat", "lng" } ],
  "packing_list": ["…"],
  "weather_summary": "…",
  "reasoning_log": [ { "agent": "Housing", "note": "…" }, { "agent": "Orchestrator", "note": "…downgrade trade-off…" } ],
  "agent_outputs": { "budget": {…}, "transportation": {…}, "housing": {…}, "food": {…}, "activity": {…}, "planning": {…} }
}
```

`item.type` is one of: `arrival | departure | lodging | meal | activity`.

---

## Extending toward "AI Town" (PRD §14)

This is a one-shot orchestrator/worker pipeline, **not** a persistent simulation.
Before adding memory, reflection, autonomous planning, or a multi-day loop, read
**PRD §14 (Gap Analysis vs. AI Town)** — it lists exactly what's missing and the
recommended order to add it. The smallest first step is per-trip agent memory.
