# Ctrip (携程) Hotel Booking Pipeline

A Playwright-driven pipeline that turns the multi-agent planner's outputs into a
real hotel search → filter → book → pay → store flow on 携程.

> **Status:** MVP. The *search* step drives a real headless browser against Ctrip
> when Playwright + Chromium are installed. The *booking* step drives the browser
> to the **payment checkpoint** (Ctrip requires a logged-in account and a
> human-scanned WeChat/Alipay QR, so fully-automated payment is impossible).
>
> **Strict / no-mock mode (default):** the pipeline uses ONLY real Ctrip data. On any
> live failure (no browser, structure change, network block, or Ctrip returning
> nothing parseable) it **raises a clear error** — it does NOT inject fake hotels or a
> fake order number. The deterministic mock fallback is **opt-in** and only activates
> when you explicitly set `ALLOW_MOCK_RESULTS=1` (offline demos only). This guarantees
> a normal run never silently serves mock data.

---

## How the agents feed the pipeline (your spec)

| Pipeline input | Comes from | Where |
|---|---|---|
| `location` | Planning Agent | planner `result.destination` |
| `max_price_per_night` | Budget Agent | `agent_outputs.budget.daily_caps.housing` |
| `preferences` / `min_rating` | Planning Agent | `trip_input.preferences.activity_style` |
| `id_number` / `phone` / `name` | DB (traveler identity) | `booking/db.py` (`users` table) |
| `payment_method` | User picks in frontend | `wechat` / `alipay` |

The frontend's **"在携程预订酒店"** button on a completed plan pre-fills the search
form from exactly these fields (see `App.jsx` → `plannerPrefill()`).

---

## The 5 pipeline steps

1. **Search by location** — `ctrip.search_hotels` resolves the city name to a
   Ctrip city id, opens the hotel list page in headless Chromium, and parses
   hotel cards → normalized `HotelResult` list.
2. **Filter by budget + preferences** — `pipeline.search_and_filter` drops hotels
   above `max_price_per_night` or below `min_rating`, then ranks by preference-tag
   overlap → rating → price, returning the top 12.
3. **Return to frontend** — results render as cards; the user picks one.
4. **Confirm → Playwright booking** — `ctrip.book_hotel` opens the hotel, fills
   the traveler's name / ID / phone from the DB record, selects the room, chooses
   the payment method, and clicks through to the **payment page**. It stops there
   and returns `status: "pending_payment"` with a generated order number.
5. **Store confirmed route** — `pipeline.confirm_booking` persists the booking as a
   `confirmed_routes` row (status `pending_payment`). After the user pays in their
   own WeChat/Alipay and clicks **"标记已支付"**, `mark_paid` flips it to
   `confirmed`. This is the durable "confirmed route" record.

---

## API

Base URL: `http://localhost:8000` (configurable via `VITE_API_BASE`).

### `POST /hotels/ctrip/search`
Body (`HotelSearchRequest`):
```json
{
  "location": "上海",
  "check_in": "2026-08-10",
  "check_out": "2026-08-14",
  "adults": 2, "children": 0, "rooms": 1,
  "max_price_per_night": 900,
  "min_rating": 4.0,
  "preferences": ["central", "quiet"]
}
```
Returns `HotelResult[]` (real Ctrip data has `source: "ctrip"`; `source` is only
ever `"mock"`/`"simulated"` when you explicitly run with `ALLOW_MOCK_RESULTS=1`):
```json
[{ "id": "ctrip_12345", "name": "上海和平饭店", "price_per_night": 900.0,
   "rating": 4.6, "area": "南京东路", "tags": ["central","business"],
   "url": "https://hotels.ctrip.com/hotels/12345.html",
   "currency": "CNY", "source": "ctrip" }]
```

### `POST /hotels/ctrip/confirm`
Body (`BookingConfirmRequest`):
```json
{
  "id_number": "310...", "name": "张三", "phone": "13800000000",
  "hotel": { "id": "ctrip_12345", "name": "上海和平饭店",
             "url": "https://hotels.ctrip.com/hotels/12345.html",
             "room_type": null, "price_total": 3440.0, "currency": "CNY" },
  "check_in": "2026-08-10", "check_out": "2026-08-14",
  "rooms": 1, "adults": 2, "children": 0, "payment_method": "wechat"
}
```
Returns `BookingResult` (a `failed` status with `route: null` means the live Ctrip
attempt could not proceed and **nothing was written**; a `pending_payment` status
means the browser reached the payment checkpoint and a real `confirmed_routes` row
was stored):
```json
{ "status": "pending_payment", "order_no": "CTRIP-1753200000",
  "message": "已到达支付页面…请在携程中扫码完成支付…",
  "route": { "id": 1, "status": "pending_payment", ... } }
```

### `POST /hotels/ctrip/routes/{route_id}/paid?order_no=...`
Marks a pending route `confirmed` after the user pays.

### `GET /hotels/ctrip/routes`
Lists all stored `confirmed_routes` rows.

---

## Running it

```bash
# Backend (from backend/)
pip install -r requirements.txt
playwright install chromium        # one-time browser download
uvicorn main:app --reload         # http://localhost:8000

# Frontend (from frontend/)
npm install && npm run dev        # http://localhost:5173
```

Then: plan a trip → click **"在携程预订酒店"** → adjust filters → **搜索携程酒店**
→ pick a hotel → **选择** → fill name/ID/phone + pick 微信/支付宝 → **确认并下单**
→ pay in your Ctrip app → **标记已支付**.

### Strict mode vs. mock (important)

- **Default (`ALLOW_MOCK_RESULTS` unset):** only real Ctrip data. If live scraping is
  unavailable or blocked, the search endpoint returns an error — **no fake hotels**.
  If live booking can't reach the payment checkpoint, `confirm` returns
  `status: "failed"` with `route: null` — **no fake route is stored**.
- **Offline demo only:** set `ALLOW_MOCK_RESULTS=1` before starting the backend to
  enable the deterministic mock fallback. Results are tagged `source: "mock"` and the
  frontend shows a **"非真实数据"** warning badge so you can never confuse them with
  real bookings.

### Verifying the no-mock guarantee

```bash
cd backend
python booking/verify_real.py     # asserts strict mode, real city resolve, no mock injected, DB round-trip
```

> **Honest limitation — scraping selectors:** Ctrip is heavily protected and its page
> structure changes often. The selectors in `ctrip.py` (`window.__INITIAL_STATE__`,
> `.hotel-item`, etc.) are best-effort; if Ctrip serves a block/empty page the live
> search will return nothing parseable and raise in strict mode (no fake data). To get
> real results you may need to update those selectors against current Ctrip markup, or
> run against a logged-in browser context. Fully-automated *payment* is impossible
> regardless (human QR scan required), which is why the flow stops at the payment
> checkpoint and you confirm payment in your own Ctrip app.

---

## Files

- `backend/booking/db.py` — SQLite store (`users`, `confirmed_routes`).
- `backend/booking/ctrip.py` — Playwright search + booking bot (+ mock fallback).
- `backend/booking/pipeline.py` — search/filter/confirm orchestration.
- `backend/booking/schemas.py` — Pydantic request/response models.
- `backend/main.py` — the four `/hotels/ctrip/*` endpoints.
- `frontend/src/components/HotelSearch.jsx` — search UI + confirm modal + routes list.
- `frontend/src/App.jsx` — top-level "规划行程 / 携程订酒店" toggle + planner prefill.
