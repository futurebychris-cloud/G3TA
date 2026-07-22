"""SQLite store for the Ctrip hotel booking pipeline.

Two tables:
  * users            — traveler identity (name, ID number, phone). The ID/phone the
                       pipeline needs to auto-fill the Ctrip booking form.
  * confirmed_routes — a "confirmed route": a hotel booking the pipeline has driven
                       to the payment step (status pending_payment) and that the user
                       has paid + marked confirmed. This is the durable audit record.

The DB lives next to this file (booking/booking.db) and is created on first import.
All writes go through a module-level lock so FastAPI's threadpool can't corrupt it.
"""
import os
import sqlite3
import threading
from datetime import datetime, timezone

_DB_PATH = os.environ.get("BOOKING_DB_PATH") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "booking.db"
)
_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    with _LOCK, sqlite3.connect(_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                id_number  TEXT NOT NULL UNIQUE,
                phone      TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS confirmed_routes (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER,
                hotel_name   TEXT,
                hotel_id     TEXT,
                hotel_url    TEXT,
                check_in     TEXT,
                check_out    TEXT,
                rooms        INTEGER,
                adults       INTEGER,
                children     INTEGER,
                room_type    TEXT,
                price_total  REAL,
                currency     TEXT,
                payment_method TEXT,
                status       TEXT,
                order_no     TEXT,
                raw          TEXT,
                created_at   TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.commit()


def upsert_user(name: str, id_number: str, phone: str) -> dict:
    """Insert or update a traveler by ID number; returns the user row as a dict."""
    init_db()
    with _LOCK, sqlite3.connect(_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO users (name, id_number, phone, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id_number) DO UPDATE SET
                name = excluded.name,
                phone = excluded.phone
            """,
            (name, id_number, phone, _now()),
        )
        row = conn.execute(
            "SELECT id, name, id_number, phone, created_at FROM users WHERE id_number = ?",
            (id_number,),
        ).fetchone()
    return _user_dict(row)


def get_user(id_number: str) -> dict | None:
    init_db()
    with sqlite3.connect(_DB_PATH) as conn:
        row = conn.execute(
            "SELECT id, name, id_number, phone, created_at FROM users WHERE id_number = ?",
            (id_number,),
        ).fetchone()
    return _user_dict(row) if row else None


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
    with _LOCK, sqlite3.connect(_DB_PATH) as conn:
        cur = conn.execute(
            """
            INSERT INTO confirmed_routes (
                user_id, hotel_name, hotel_id, hotel_url, check_in, check_out,
                rooms, adults, children, room_type, price_total, currency,
                payment_method, status, order_no, raw, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, hotel_name, hotel_id, hotel_url, check_in, check_out,
                rooms, adults, children, room_type, price_total, currency,
                payment_method, status, order_no, raw, _now(),
            ),
        )
        rid = cur.lastrowid
        row = conn.execute(
            "SELECT * FROM confirmed_routes WHERE id = ?", (rid,)
        ).fetchone()
    return _route_dict(row)


def list_users() -> list[dict]:
    """Return all stored travelers from the users table."""
    init_db()
    with sqlite3.connect(_DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, name, id_number, phone, created_at FROM users ORDER BY id DESC"
        ).fetchall()
    return [_user_dict(r) for r in rows]


def update_route_status(route_id: int, status: str, order_no: str | None = None) -> dict | None:
    with _LOCK, sqlite3.connect(_DB_PATH) as conn:
        if order_no is not None:
            conn.execute(
                "UPDATE confirmed_routes SET status = ?, order_no = ? WHERE id = ?",
                (status, order_no, route_id),
            )
        else:
            conn.execute(
                "UPDATE confirmed_routes SET status = ? WHERE id = ?",
                (status, route_id),
            )
        row = conn.execute("SELECT * FROM confirmed_routes WHERE id = ?", (route_id,)).fetchone()
    return _route_dict(row) if row else None


def list_routes(user_id: int | None = None) -> list[dict]:
    init_db()
    with sqlite3.connect(_DB_PATH) as conn:
        if user_id is not None:
            rows = conn.execute(
                "SELECT * FROM confirmed_routes WHERE user_id = ? ORDER BY id DESC",
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM confirmed_routes ORDER BY id DESC"
            ).fetchall()
    return [_route_dict(r) for r in rows]


# --- row -> dict helpers ----------------------------------------------------- #
_COLS_USER = ["id", "name", "id_number", "phone", "created_at"]
_COLS_ROUTE = [
    "id", "user_id", "hotel_name", "hotel_id", "hotel_url", "check_in", "check_out",
    "rooms", "adults", "children", "room_type", "price_total", "currency",
    "payment_method", "status", "order_no", "raw", "created_at",
]


def _user_dict(row) -> dict:
    return dict(zip(_COLS_USER, row))


def _route_dict(row) -> dict:
    return dict(zip(_COLS_ROUTE, row))
