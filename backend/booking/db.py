"""PostgreSQL store for the Ctrip hotel booking pipeline.

Two tables:
  * users            — traveler identity (name, ID number, phone). The ID/phone the
                       pipeline needs to auto-fill the Ctrip booking form.
  * confirmed_routes — a "confirmed route": a hotel booking the pipeline has driven
                       to the payment step (status pending_payment) and that the user
                       has paid + marked confirmed. This is the durable audit record.

Uses psycopg2 connection pool (thread-safe); no module-level lock needed.
"""
from booking.postgres_db import get_cursor


def init_db() -> None:
    """Create users + confirmed_routes tables (idempotent)."""
    with get_cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id         SERIAL PRIMARY KEY,
                name       TEXT NOT NULL,
                id_number  TEXT NOT NULL UNIQUE,
                phone      TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS confirmed_routes (
                id             SERIAL PRIMARY KEY,
                user_id        INTEGER REFERENCES users(id),
                hotel_name     TEXT,
                hotel_id       TEXT,
                hotel_url      TEXT,
                check_in       TEXT,
                check_out      TEXT,
                rooms          INTEGER,
                adults         INTEGER,
                children       INTEGER,
                room_type      TEXT,
                price_total    NUMERIC,
                currency       TEXT,
                payment_method TEXT,
                status         TEXT,
                order_no       TEXT,
                raw            TEXT,
                created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )


def upsert_user(name: str, id_number: str, phone: str) -> dict:
    """Insert or update a traveler by ID number; returns the user row as a dict."""
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (name, id_number, phone, created_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT(id_number) DO UPDATE SET
                name = EXCLUDED.name,
                phone = EXCLUDED.phone
            RETURNING id, name, id_number, phone, created_at
            """,
            (name, id_number, phone),
        )
        row = cur.fetchone()
    return _serialize_row(row, _COLS_USER)


def get_user(id_number: str) -> dict | None:
    init_db()
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name, id_number, phone, created_at FROM users WHERE id_number = %s",
            (id_number,),
        )
        row = cur.fetchone()
    return _serialize_row(row, _COLS_USER) if row else None


def save_route(
    *,
    user_id: int | None,
    hotel_name: str | None,
    hotel_id: str | None,
    hotel_url: str | None,
    check_in: str,
    check_out: str,
    rooms: int,
    adults: int,
    children: int,
    room_type: str | None,
    price_total: float,
    currency: str,
    payment_method: str,
    status: str,
    order_no: str | None = None,
    raw: str | None = None,
) -> dict:
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO confirmed_routes (
                user_id, hotel_name, hotel_id, hotel_url, check_in, check_out,
                rooms, adults, children, room_type, price_total, currency,
                payment_method, status, order_no, raw, created_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            RETURNING *
            """,
            (
                user_id, hotel_name, hotel_id, hotel_url, check_in, check_out,
                rooms, adults, children, room_type, price_total, currency,
                payment_method, status, order_no, raw,
            ),
        )
        row = cur.fetchone()
    return _serialize_row(row, _COLS_ROUTE)


def list_users() -> list[dict]:
    """Return all stored travelers from the users table."""
    init_db()
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name, id_number, phone, created_at FROM users ORDER BY id DESC"
        )
        rows = cur.fetchall()
    return [_serialize_row(r, _COLS_USER) for r in rows]


def update_route_status(route_id: int, status: str, order_no: str | None = None) -> dict | None:
    with get_cursor() as cur:
        if order_no is not None:
            cur.execute(
                "UPDATE confirmed_routes SET status = %s, order_no = %s WHERE id = %s RETURNING *",
                (status, order_no, route_id),
            )
        else:
            cur.execute(
                "UPDATE confirmed_routes SET status = %s WHERE id = %s RETURNING *",
                (status, route_id),
            )
        row = cur.fetchone()
    return _serialize_row(row, _COLS_ROUTE) if row else None


def list_routes(user_id: int | None = None) -> list[dict]:
    init_db()
    with get_cursor() as cur:
        if user_id is not None:
            cur.execute(
                "SELECT * FROM confirmed_routes WHERE user_id = %s ORDER BY id DESC",
                (user_id,),
            )
        else:
            cur.execute("SELECT * FROM confirmed_routes ORDER BY id DESC")
        rows = cur.fetchall()
    return [_serialize_row(r, _COLS_ROUTE) for r in rows]


# --- column lists for serialization ---------------------------------------- #

_COLS_USER = ["id", "name", "id_number", "phone", "created_at"]
_COLS_ROUTE = [
    "id", "user_id", "hotel_name", "hotel_id", "hotel_url", "check_in", "check_out",
    "rooms", "adults", "children", "room_type", "price_total", "currency",
    "payment_method", "status", "order_no", "raw", "created_at",
]


def _serialize_row(row, cols: list[str]) -> dict:
    """Convert a RealDictRow to a plain dict, with type normalization for JSON."""
    from decimal import Decimal
    result = {}
    for col in cols:
        val = row.get(col)
        if val is None:
            result[col] = None
        elif hasattr(val, "isoformat"):
            result[col] = val.isoformat()  # datetime → ISO string
        elif isinstance(val, Decimal):
            result[col] = float(val)        # NUMERIC → float
        else:
            result[col] = val
    return result
