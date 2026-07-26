# Ctrip hotel comparison and operator experiment

## Public product behavior

The shipped frontend provides a **Compare stays** flow:

1. Query a configured hotel API.
2. Fall back to a Ctrip listing only when an authenticated local Ctrip session
   is configured; otherwise skip the slow login redirect.
3. Fall back to an OpenStreetMap lodging record with no live price.
4. Filter and rank the results.
5. Open the provider URL so the traveler can verify and book there.

This flow never asks for passport/ID, phone, or payment data and never marks a
hotel paid or confirmed.

`ALLOW_MOCK_RESULTS=1` enables deterministic **search** cards for an explicit
offline demo. Those cards use `source: "mock"`. Mock mode never generates an
order number, payment checkpoint, route record, or confirmed booking.

## Public API

`POST /booking/search` streams:

```json
{"type":"booking_stage","stage":"search","status":"running"}
{"type":"booking_stage","stage":"search","status":"done","source":"ctrip"}
{"type":"booking_stage","stage":"filtering","status":"done","count":8}
{"type":"booking_results","hotels":[...]}
```

The request is a `HotelSearchRequest`:

```json
{
  "location": "上海",
  "check_in": "2026-08-10",
  "check_out": "2026-08-14",
  "adults": 2,
  "children": 0,
  "rooms": 1,
  "max_price_per_night": 900,
  "min_rating": 4.0,
  "preferences": ["central", "quiet"]
}
```

## Operator-only payment-checkpoint experiment

`POST /booking/confirm` is not exposed by the normal frontend. It is disabled
unless both conditions are met:

```dotenv
BOOKING_AUTOMATION_ENABLED=1
BOOKING_API_TOKEN=<generate-random-value>
```

The caller must send:

```http
X-G3TA-Booking-Token: <generate-random-value>
```

The token is never accepted from a query parameter and must not be compiled
into the public frontend. For an isolated localhost-only demo, a tokenless
override additionally requires `ALLOW_LOCAL_BOOKING_WITHOUT_TOKEN=1`.

If enabled, the experiment uses one-time identity fields for that provider
request and does not persist them in G3TA. A record is written only when the
browser reaches a verifiable provider payment checkpoint. The status remains
`pending_payment` or `payment_reported`; only a real provider callback or
verified provider lookup could set `confirmed`, and neither is implemented.

The flight, train, and restaurant auto-booking endpoints now run real Playwright
browser flows (search/select/prefill) and return `manual_required` with a
provider link so the human can finish identity verification and payment. The
shortcut endpoint remains unimplemented. None fabricate an order or payment
state.

## Files

- `backend/services/hotels_provider.py` — source resolution
- `backend/booking/ctrip.py` — public listing parser and protected experiment
- `backend/booking/pipeline.py` — filter and checkpoint audit logic
- `backend/booking/schemas.py` — request/response models
- `backend/security.py` — enable flag and operator token
- `frontend/src/components/BookingPanel.jsx` — comparison-only UI

Provider pages and anti-automation rules change frequently. Treat browser
collectors as best-effort research tools, stop at login/CAPTCHA/risk-control
pages, and prefer an official provider API for any production deployment.
