"""Shared database for all G3TA agents — stores planning data across agent runs.

Supports both SQLite (default) and PostgreSQL (when DATABASE_URL is set).

Tables:
    shared_expenses     — Budget Agent: tracks all expenses across categories
    shared_activities   — Activity Agent: proposed activities with review state
    shared_meals        — Food Agent: proposed restaurant/meal selections
    shared_transport    — Transportation Agent: proposed routes and booking state
    shared_checklist    — Planning Agent: packing/checklist items
    shared_preferences  — User preferences & travel history
    shared_trips        — Trip metadata
    shared_provider_cache — Persisted Playwright/provider query results
"""
from __future__ import annotations

import os
import json
import time
from datetime import datetime
from contextlib import contextmanager

# ---- Database backend selection -------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL", "")
_USE_POSTGRES = bool(DATABASE_URL and DATABASE_URL.startswith("postgres"))

if _USE_POSTGRES:
    from booking.postgres_db import get_cursor as _pg_cursor
else:
    import sqlite3
    DB_PATH = os.environ.get("SHARED_DB_PATH", os.path.join(os.path.dirname(__file__), "shared.db"))


# ========================================================================== #
# SQLite backend
# ========================================================================== #
if not _USE_POSTGRES:
    @contextmanager
    def _conn():
        c = sqlite3.connect(DB_PATH)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    _PLACEHOLDER = "?"


# ========================================================================== #
# PostgreSQL backend
# ========================================================================== #
else:
    @contextmanager
    def _conn():
        with _pg_cursor() as cur:
            yield cur

    _PLACEHOLDER = "%s"


# ========================================================================== #
# Table initialization
# ========================================================================== #
def init_shared_db():
    """Create all shared tables if they don't exist."""
    if _USE_POSTGRES:
        _init_postgres_tables()
    else:
        _init_sqlite_tables()
    purge_expired_provider_cache()


def _init_sqlite_tables():
    with _conn() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS shared_expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id TEXT NOT NULL,
                category TEXT NOT NULL CHECK(category IN ('dining','hotel','transport','activity','shopping','other')),
                subject_id TEXT NOT NULL,
                subject_name TEXT DEFAULT '',
                date TEXT NOT NULL,
                value REAL NOT NULL,
                currency TEXT DEFAULT 'CNY',
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS shared_activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id TEXT NOT NULL,
                activity_name TEXT NOT NULL,
                activity_location TEXT DEFAULT '',
                activity_description TEXT DEFAULT '',
                activity_type TEXT DEFAULT '' CHECK(activity_type IN ('sport','nature','culture','entertainment','shopping','other')),
                start_time TEXT DEFAULT '',
                end_time TEXT DEFAULT '',
                ticket_price REAL DEFAULT 0,
                num_people INTEGER DEFAULT 1,
                is_group INTEGER DEFAULT 0,
                opening_hours TEXT DEFAULT '',
                best_visit_time TEXT DEFAULT '',
                population_level TEXT DEFAULT '',
                lat REAL,
                lng REAL,
                meal_slot TEXT DEFAULT '' CHECK(meal_slot IN ('breakfast','lunch','dinner','')),
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending','confirmed','cancelled')),
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS shared_meals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id TEXT NOT NULL,
                date TEXT NOT NULL,
                meal_slot TEXT NOT NULL CHECK(meal_slot IN ('breakfast','lunch','dinner')),
                restaurant_name TEXT NOT NULL,
                restaurant_location TEXT DEFAULT '',
                cuisine_type TEXT DEFAULT '',
                taste_profile TEXT DEFAULT '',
                dish_name TEXT DEFAULT '',
                dish_category TEXT DEFAULT '' CHECK(dish_category IN ('main','starter','dessert','drink','')),
                dish_price REAL DEFAULT 0,
                dish_popularity REAL DEFAULT 0,
                currency TEXT DEFAULT 'CNY',
                is_ordered INTEGER DEFAULT 0,
                order_number TEXT DEFAULT '',
                lat REAL,
                lng REAL,
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending','confirmed','ordered','cancelled')),
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS shared_transport (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id TEXT NOT NULL,
                transport_type TEXT NOT NULL CHECK(transport_type IN ('flight','train','car','bus','taxi','subway','bike','walk','ferry')),
                scope TEXT DEFAULT 'national' CHECK(scope IN ('national','international','local')),
                from_location TEXT NOT NULL,
                to_location TEXT NOT NULL,
                departure_time TEXT DEFAULT '',
                arrival_time TEXT DEFAULT '',
                carrier TEXT DEFAULT '',
                flight_number TEXT DEFAULT '',
                train_number TEXT DEFAULT '',
                price REAL DEFAULT 0,
                currency TEXT DEFAULT 'CNY',
                booking_status TEXT DEFAULT 'pending' CHECK(booking_status IN ('pending','booked','confirmed','cancelled')),
                booking_ref TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS shared_checklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id TEXT NOT NULL,
                category TEXT NOT NULL CHECK(category IN ('clothing','item','supportive','legal','device','other')),
                item_name TEXT NOT NULL,
                quantity INTEGER DEFAULT 1,
                is_packed INTEGER DEFAULT 0,
                weather_note TEXT DEFAULT '',
                suggestion_reason TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS shared_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id TEXT NOT NULL,
                preference_key TEXT NOT NULL,
                preference_value TEXT DEFAULT '',
                weight REAL DEFAULT 1.0,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS shared_trips (
                trip_id TEXT PRIMARY KEY,
                location TEXT NOT NULL,
                origin TEXT DEFAULT '',
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                total_budget REAL DEFAULT 0,
                currency TEXT DEFAULT 'CNY',
                scope TEXT DEFAULT 'national' CHECK(scope IN ('national','international')),
                status TEXT DEFAULT 'planning' CHECK(status IN ('planning','confirmed','completed')),
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS shared_provider_cache (
                namespace TEXT NOT NULL,
                cache_key TEXT NOT NULL,
                query_json TEXT NOT NULL,
                source TEXT DEFAULT 'playwright',
                payload_json TEXT NOT NULL,
                record_count INTEGER DEFAULT 0,
                fetched_at_epoch REAL NOT NULL,
                expires_at_epoch REAL NOT NULL,
                updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (namespace, cache_key)
            )
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_provider_cache_expiry
            ON shared_provider_cache (expires_at_epoch)
        """)
        _ensure_sqlite_transport_supports_car(db)


def _ensure_sqlite_transport_supports_car(db) -> None:
    """Migrate the legacy SQLite transport CHECK while preserving every row."""
    row = db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='shared_transport'"
    ).fetchone()
    table_sql = str(row["sql"] if row else "")
    if "'car'" in table_sql:
        return
    legacy_name = "shared_transport_legacy_car_migration"
    if db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (legacy_name,),
    ).fetchone():
        raise RuntimeError(
            f"Cannot migrate shared_transport while {legacy_name} already exists."
        )
    db.execute(f"ALTER TABLE shared_transport RENAME TO {legacy_name}")
    db.execute("""
        CREATE TABLE shared_transport (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id TEXT NOT NULL,
            transport_type TEXT NOT NULL CHECK(transport_type IN ('flight','train','car','bus','taxi','subway','bike','walk','ferry')),
            scope TEXT DEFAULT 'national' CHECK(scope IN ('national','international','local')),
            from_location TEXT NOT NULL,
            to_location TEXT NOT NULL,
            departure_time TEXT DEFAULT '',
            arrival_time TEXT DEFAULT '',
            carrier TEXT DEFAULT '',
            flight_number TEXT DEFAULT '',
            train_number TEXT DEFAULT '',
            price REAL DEFAULT 0,
            currency TEXT DEFAULT 'CNY',
            booking_status TEXT DEFAULT 'pending' CHECK(booking_status IN ('pending','booked','confirmed','cancelled')),
            booking_ref TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    columns = (
        "id, trip_id, transport_type, scope, from_location, to_location, "
        "departure_time, arrival_time, carrier, flight_number, train_number, "
        "price, currency, booking_status, booking_ref, notes, created_at"
    )
    db.execute(
        f"INSERT INTO shared_transport ({columns}) "
        f"SELECT {columns} FROM {legacy_name}"
    )
    db.execute(f"DROP TABLE {legacy_name}")


def _init_postgres_tables():
    with _conn() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS shared_trips (
                trip_id TEXT PRIMARY KEY,
                location TEXT NOT NULL,
                origin TEXT DEFAULT '',
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                total_budget NUMERIC DEFAULT 0,
                currency TEXT DEFAULT 'CNY',
                scope TEXT DEFAULT 'national' CHECK(scope IN ('national','international')),
                status TEXT DEFAULT 'planning' CHECK(status IN ('planning','confirmed','completed')),
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS shared_expenses (
                id SERIAL PRIMARY KEY,
                trip_id TEXT NOT NULL,
                category TEXT NOT NULL CHECK(category IN ('dining','hotel','transport','activity','shopping','other')),
                subject_id TEXT NOT NULL,
                subject_name TEXT DEFAULT '',
                date TEXT NOT NULL,
                value NUMERIC NOT NULL,
                currency TEXT DEFAULT 'CNY',
                notes TEXT DEFAULT '',
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS shared_activities (
                id SERIAL PRIMARY KEY,
                trip_id TEXT NOT NULL,
                activity_name TEXT NOT NULL,
                activity_location TEXT DEFAULT '',
                activity_description TEXT DEFAULT '',
                activity_type TEXT DEFAULT '' CHECK(activity_type IN ('sport','nature','culture','entertainment','shopping','other')),
                start_time TEXT DEFAULT '',
                end_time TEXT DEFAULT '',
                ticket_price NUMERIC DEFAULT 0,
                num_people INTEGER DEFAULT 1,
                is_group INTEGER DEFAULT 0,
                opening_hours TEXT DEFAULT '',
                best_visit_time TEXT DEFAULT '',
                population_level TEXT DEFAULT '',
                lat DOUBLE PRECISION,
                lng DOUBLE PRECISION,
                meal_slot TEXT DEFAULT '' CHECK(meal_slot IN ('breakfast','lunch','dinner','')),
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending','confirmed','cancelled')),
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS shared_meals (
                id SERIAL PRIMARY KEY,
                trip_id TEXT NOT NULL,
                date TEXT NOT NULL,
                meal_slot TEXT NOT NULL CHECK(meal_slot IN ('breakfast','lunch','dinner')),
                restaurant_name TEXT NOT NULL,
                restaurant_location TEXT DEFAULT '',
                cuisine_type TEXT DEFAULT '',
                taste_profile TEXT DEFAULT '',
                dish_name TEXT DEFAULT '',
                dish_category TEXT DEFAULT '' CHECK(dish_category IN ('main','starter','dessert','drink','')),
                dish_price NUMERIC DEFAULT 0,
                dish_popularity NUMERIC DEFAULT 0,
                currency TEXT DEFAULT 'CNY',
                is_ordered INTEGER DEFAULT 0,
                order_number TEXT DEFAULT '',
                lat DOUBLE PRECISION,
                lng DOUBLE PRECISION,
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending','confirmed','ordered','cancelled')),
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS shared_transport (
                id SERIAL PRIMARY KEY,
                trip_id TEXT NOT NULL,
                transport_type TEXT NOT NULL CHECK(transport_type IN ('flight','train','car','bus','taxi','subway','bike','walk','ferry')),
                scope TEXT DEFAULT 'national' CHECK(scope IN ('national','international','local')),
                from_location TEXT NOT NULL,
                to_location TEXT NOT NULL,
                departure_time TEXT DEFAULT '',
                arrival_time TEXT DEFAULT '',
                carrier TEXT DEFAULT '',
                flight_number TEXT DEFAULT '',
                train_number TEXT DEFAULT '',
                price NUMERIC DEFAULT 0,
                currency TEXT DEFAULT 'CNY',
                booking_status TEXT DEFAULT 'pending' CHECK(booking_status IN ('pending','booked','confirmed','cancelled')),
                booking_ref TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            ALTER TABLE shared_transport
            DROP CONSTRAINT IF EXISTS shared_transport_transport_type_check
        """)
        cur.execute("""
            ALTER TABLE shared_transport
            ADD CONSTRAINT shared_transport_transport_type_check
            CHECK(transport_type IN ('flight','train','car','bus','taxi','subway','bike','walk','ferry'))
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS shared_checklist (
                id SERIAL PRIMARY KEY,
                trip_id TEXT NOT NULL,
                category TEXT NOT NULL CHECK(category IN ('clothing','item','supportive','legal','device','other')),
                item_name TEXT NOT NULL,
                quantity INTEGER DEFAULT 1,
                is_packed INTEGER DEFAULT 0,
                weather_note TEXT DEFAULT '',
                suggestion_reason TEXT DEFAULT '',
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS shared_preferences (
                id SERIAL PRIMARY KEY,
                trip_id TEXT NOT NULL,
                preference_key TEXT NOT NULL,
                preference_value TEXT DEFAULT '',
                weight NUMERIC DEFAULT 1.0,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS shared_provider_cache (
                namespace TEXT NOT NULL,
                cache_key TEXT NOT NULL,
                query_json TEXT NOT NULL,
                source TEXT DEFAULT 'playwright',
                payload_json TEXT NOT NULL,
                record_count INTEGER DEFAULT 0,
                fetched_at_epoch DOUBLE PRECISION NOT NULL,
                expires_at_epoch DOUBLE PRECISION NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (namespace, cache_key)
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_provider_cache_expiry
            ON shared_provider_cache (expires_at_epoch)
        """)


# ========================================================================== #
# Persistent provider / Playwright cache helpers
# ========================================================================== #
def _record_count(payload) -> int:
    if isinstance(payload, dict):
        for key in ("results", "items", "records"):
            records = payload.get(key)
            if isinstance(records, (list, tuple, set)):
                return len(records)
        return len(payload)
    if isinstance(payload, (list, tuple, set)):
        return len(payload)
    return 1 if payload is not None else 0


def save_provider_cache(
    namespace: str,
    cache_key: str,
    query_json: str,
    payload,
    *,
    source: str = "playwright",
    ttl_seconds: float = 600,
) -> None:
    """Upsert one JSON-serializable provider response."""
    fetched_at = time.time()
    expires_at = fetched_at + max(float(ttl_seconds), 1)
    payload_json = json.dumps(payload, ensure_ascii=False, default=str)
    values = (
        namespace,
        cache_key,
        query_json,
        source,
        payload_json,
        _record_count(payload),
        fetched_at,
        expires_at,
    )
    with _conn() as db:
        if _USE_POSTGRES:
            db.execute(
                f"""
                INSERT INTO shared_provider_cache (
                    namespace, cache_key, query_json, source, payload_json,
                    record_count, fetched_at_epoch, expires_at_epoch
                ) VALUES (
                    {_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},
                    {_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER}
                )
                ON CONFLICT (namespace, cache_key) DO UPDATE SET
                    query_json=EXCLUDED.query_json,
                    source=EXCLUDED.source,
                    payload_json=EXCLUDED.payload_json,
                    record_count=EXCLUDED.record_count,
                    fetched_at_epoch=EXCLUDED.fetched_at_epoch,
                    expires_at_epoch=EXCLUDED.expires_at_epoch,
                    updated_at=NOW()
                """,
                values,
            )
        else:
            db.execute(
                f"""
                INSERT INTO shared_provider_cache (
                    namespace, cache_key, query_json, source, payload_json,
                    record_count, fetched_at_epoch, expires_at_epoch
                ) VALUES (
                    {_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},
                    {_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER}
                )
                ON CONFLICT(namespace, cache_key) DO UPDATE SET
                    query_json=excluded.query_json,
                    source=excluded.source,
                    payload_json=excluded.payload_json,
                    record_count=excluded.record_count,
                    fetched_at_epoch=excluded.fetched_at_epoch,
                    expires_at_epoch=excluded.expires_at_epoch,
                    updated_at=datetime('now')
                """,
                values,
            )


def get_provider_cache(namespace: str, cache_key: str):
    """Return an unexpired persisted provider response, otherwise ``None``."""
    with _conn() as db:
        sql = (
            f"SELECT payload_json FROM shared_provider_cache "
            f"WHERE namespace={_PLACEHOLDER} AND cache_key={_PLACEHOLDER} "
            f"AND expires_at_epoch>{_PLACEHOLDER}"
        )
        params = (namespace, cache_key, time.time())
        if _USE_POSTGRES:
            db.execute(sql, params)
            row = db.fetchone()
        else:
            row = db.execute(sql, params).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["payload_json"])
    except (TypeError, json.JSONDecodeError):
        return None


def list_provider_cache(namespace: str | None = None, limit: int = 100) -> list[dict]:
    """Return cache metadata without returning potentially large payload bodies."""
    safe_limit = max(1, min(int(limit), 1000))
    with _conn() as db:
        if namespace:
            sql = (
                f"SELECT namespace, cache_key, query_json, source, record_count, "
                f"fetched_at_epoch, expires_at_epoch, updated_at "
                f"FROM shared_provider_cache WHERE namespace={_PLACEHOLDER} "
                f"ORDER BY fetched_at_epoch DESC LIMIT {safe_limit}"
            )
            params = (namespace,)
        else:
            sql = (
                "SELECT namespace, cache_key, query_json, source, record_count, "
                "fetched_at_epoch, expires_at_epoch, updated_at "
                f"FROM shared_provider_cache ORDER BY fetched_at_epoch DESC LIMIT {safe_limit}"
            )
            params = ()
        rows = _execute_and_fetch(db, sql, params)
    return [dict(row) for row in rows]


def purge_expired_provider_cache() -> int:
    """Delete expired provider rows and return the affected row count."""
    with _conn() as db:
        if _USE_POSTGRES:
            db.execute(
                f"DELETE FROM shared_provider_cache WHERE expires_at_epoch<={_PLACEHOLDER}",
                (time.time(),),
            )
            return db.rowcount
        cur = db.execute(
            f"DELETE FROM shared_provider_cache WHERE expires_at_epoch<={_PLACEHOLDER}",
            (time.time(),),
        )
        return cur.rowcount


# ========================================================================== #
# Budget Agent helpers
# ========================================================================== #
def add_expense(trip_id: str, category: str, subject_id: str, subject_name: str,
                date: str, value: float, currency: str = "CNY", notes: str = "") -> int:
    with _conn() as db:
        if _USE_POSTGRES:
            cur = db
            cur.execute(
                f"INSERT INTO shared_expenses (trip_id, category, subject_id, subject_name, date, value, currency, notes) "
                f"VALUES ({_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER}) RETURNING id",
                (trip_id, category, subject_id, subject_name, date, value, currency, notes),
            )
            return cur.fetchone()["id"]
        else:
            cur = db.execute(
                f"INSERT INTO shared_expenses (trip_id, category, subject_id, subject_name, date, value, currency, notes) "
                f"VALUES ({_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER})",
                (trip_id, category, subject_id, subject_name, date, value, currency, notes),
            )
            return cur.lastrowid


def _execute_and_fetch(db, sql: str, params: tuple):
    """Execute query and fetchall — works with both SQLite & PostgreSQL."""
    if _USE_POSTGRES:
        db.execute(sql, params)
        return db.fetchall()
    else:
        return db.execute(sql, params).fetchall()


_NUMERIC_FIELDS = {
    "shared_activities": {"ticket_price", "num_people", "is_group", "lat", "lng"},
    "shared_meals": {"dish_price", "dish_popularity", "is_ordered", "lat", "lng"},
    "shared_transport": {"price"},
}

_DEFAULT_VALUES = {
    "status": "pending",
    "booking_status": "pending",
    "scope": "national",
    "meal_slot": "",
    "activity_type": "",
    "dish_category": "",
}


def _sanitize_for_pg(table: str, vals: dict) -> dict:
    """Convert omitted helper arguments to values accepted by either backend."""
    numeric_cols = _NUMERIC_FIELDS.get(table, set())
    result = {}
    for k, v in vals.items():
        if v == "":
            if k in numeric_cols:
                result[k] = 0
            elif k in _DEFAULT_VALUES:
                result[k] = _DEFAULT_VALUES[k]
            else:
                result[k] = v
        else:
            result[k] = v
    return result


def get_expenses_by_trip(trip_id: str) -> list[dict]:
    with _conn() as db:
        rows = _execute_and_fetch(
            db,
            f"SELECT * FROM shared_expenses WHERE trip_id={_PLACEHOLDER} ORDER BY date, category",
            (trip_id,),
        )
    return [dict(r) for r in rows]


def get_expense_summary(trip_id: str) -> dict:
    with _conn() as db:
        rows = _execute_and_fetch(
            db,
            f"SELECT category, SUM(value) as total FROM shared_expenses WHERE trip_id={_PLACEHOLDER} GROUP BY category",
            (trip_id,),
        )
    return {r["category"]: r["total"] for r in rows}


# ========================================================================== #
# Activity Agent helpers
# ========================================================================== #
def save_activity(trip_id: str, **kwargs) -> int:
    fields = ["trip_id","activity_name","activity_location","activity_description",
              "activity_type","start_time","end_time","ticket_price","num_people",
              "is_group","opening_hours","best_visit_time","population_level",
              "lat","lng","meal_slot","status"]
    vals = _sanitize_for_pg("shared_activities", {f: kwargs.get(f, "") for f in fields})
    vals["trip_id"] = trip_id
    cols = ", ".join(vals.keys())
    placeholders = ", ".join(_PLACEHOLDER for _ in vals)
    with _conn() as db:
        if _USE_POSTGRES:
            db.execute(f"INSERT INTO shared_activities ({cols}) VALUES ({placeholders}) RETURNING id", tuple(vals.values()))
            return db.fetchone()["id"]
        else:
            cur = db.execute(f"INSERT INTO shared_activities ({cols}) VALUES ({placeholders})", tuple(vals.values()))
            return cur.lastrowid


def get_activities_by_trip(trip_id: str) -> list[dict]:
    with _conn() as db:
        rows = _execute_and_fetch(db, f"SELECT * FROM shared_activities WHERE trip_id={_PLACEHOLDER} ORDER BY start_time", (trip_id,))
    return [dict(r) for r in rows]


# ========================================================================== #
# Food Agent helpers
# ========================================================================== #
def save_meal(trip_id: str, **kwargs) -> int:
    fields = ["trip_id","date","meal_slot","restaurant_name","restaurant_location",
              "cuisine_type","taste_profile","dish_name","dish_category","dish_price",
              "dish_popularity","currency","is_ordered","order_number","lat","lng","status"]
    vals = _sanitize_for_pg("shared_meals", {f: kwargs.get(f, "") for f in fields})
    vals["trip_id"] = trip_id
    cols = ", ".join(vals.keys())
    placeholders = ", ".join(_PLACEHOLDER for _ in vals)
    with _conn() as db:
        if _USE_POSTGRES:
            db.execute(f"INSERT INTO shared_meals ({cols}) VALUES ({placeholders}) RETURNING id", tuple(vals.values()))
            return db.fetchone()["id"]
        else:
            cur = db.execute(f"INSERT INTO shared_meals ({cols}) VALUES ({placeholders})", tuple(vals.values()))
            return cur.lastrowid


def get_meals_by_trip(trip_id: str) -> list[dict]:
    with _conn() as db:
        rows = _execute_and_fetch(db, f"SELECT * FROM shared_meals WHERE trip_id={_PLACEHOLDER} ORDER BY date, meal_slot", (trip_id,))
    return [dict(r) for r in rows]


# ========================================================================== #
# Transportation Agent helpers
# ========================================================================== #
def save_transport(trip_id: str, **kwargs) -> int:
    fields = ["trip_id","transport_type","scope","from_location","to_location",
              "departure_time","arrival_time","carrier","flight_number","train_number",
              "price","currency","booking_status","booking_ref","notes"]
    vals = _sanitize_for_pg("shared_transport", {f: kwargs.get(f, "") for f in fields})
    vals["trip_id"] = trip_id
    cols = ", ".join(vals.keys())
    placeholders = ", ".join(_PLACEHOLDER for _ in vals)
    with _conn() as db:
        if _USE_POSTGRES:
            db.execute(f"INSERT INTO shared_transport ({cols}) VALUES ({placeholders}) RETURNING id", tuple(vals.values()))
            return db.fetchone()["id"]
        else:
            cur = db.execute(f"INSERT INTO shared_transport ({cols}) VALUES ({placeholders})", tuple(vals.values()))
            return cur.lastrowid


def get_transport_by_trip(trip_id: str) -> list[dict]:
    with _conn() as db:
        rows = _execute_and_fetch(db, f"SELECT * FROM shared_transport WHERE trip_id={_PLACEHOLDER} ORDER BY departure_time", (trip_id,))
    return [dict(r) for r in rows]


# ========================================================================== #
# Planning Agent helpers
# ========================================================================== #
def save_checklist_item(trip_id: str, **kwargs) -> int:
    fields = ["trip_id","category","item_name","quantity","is_packed","weather_note","suggestion_reason"]
    vals = {f: kwargs.get(f, "") for f in fields}
    vals["trip_id"] = trip_id
    # Coerce numeric columns so an empty string / None never reaches an INTEGER column.
    try:
        vals["quantity"] = int(vals.get("quantity") or 1)
    except (ValueError, TypeError):
        vals["quantity"] = 1
    try:
        vals["is_packed"] = int(vals.get("is_packed") or 0)
    except (ValueError, TypeError):
        vals["is_packed"] = 0
    cols = ", ".join(vals.keys())
    placeholders = ", ".join(_PLACEHOLDER for _ in vals)
    with _conn() as db:
        if _USE_POSTGRES:
            db.execute(f"INSERT INTO shared_checklist ({cols}) VALUES ({placeholders}) RETURNING id", tuple(vals.values()))
            return db.fetchone()["id"]
        else:
            cur = db.execute(f"INSERT INTO shared_checklist ({cols}) VALUES ({placeholders})", tuple(vals.values()))
            return cur.lastrowid


def get_checklist_by_trip(trip_id: str) -> list[dict]:
    with _conn() as db:
        rows = _execute_and_fetch(db, f"SELECT * FROM shared_checklist WHERE trip_id={_PLACEHOLDER} ORDER BY category, id", (trip_id,))
    return [dict(r) for r in rows]


def set_checklist_packed(item_id: int, trip_id: str, is_packed: bool) -> bool:
    """Update one checklist row only when it belongs to the supplied trip."""
    with _conn() as db:
        cur = db.execute(
            f"UPDATE shared_checklist SET is_packed={_PLACEHOLDER} "
            f"WHERE id={_PLACEHOLDER} AND trip_id={_PLACEHOLDER}",
            (1 if is_packed else 0, item_id, trip_id),
        )
        return cur.rowcount > 0


def mark_checklist_packed(item_id: int) -> None:
    """Deprecated compatibility helper for trusted internal callers."""
    with _conn() as db:
        db.execute(
            f"UPDATE shared_checklist SET is_packed=1 WHERE id={_PLACEHOLDER}",
            (item_id,),
        )


# ========================================================================== #
# Trip helpers
# ========================================================================== #
def save_trip(trip_id: str, location: str, origin: str, start_date: str, end_date: str,
              total_budget: float, currency: str = "CNY", scope: str = "national") -> None:
    with _conn() as db:
        if _USE_POSTGRES:
            db.execute(
                f"INSERT INTO shared_trips (trip_id, location, origin, start_date, end_date, total_budget, currency, scope) "
                f"VALUES ({_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER}) "
                f"ON CONFLICT (trip_id) DO UPDATE SET location=EXCLUDED.location, origin=EXCLUDED.origin, "
                f"start_date=EXCLUDED.start_date, end_date=EXCLUDED.end_date, total_budget=EXCLUDED.total_budget, "
                f"currency=EXCLUDED.currency, scope=EXCLUDED.scope",
                (trip_id, location, origin, start_date, end_date, total_budget, currency, scope),
            )
        else:
            db.execute(
                f"INSERT OR REPLACE INTO shared_trips (trip_id, location, origin, start_date, end_date, total_budget, currency, scope) "
                f"VALUES ({_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER})",
                (trip_id, location, origin, start_date, end_date, total_budget, currency, scope),
            )


def save_preference(trip_id: str, key: str, value: str, weight: float = 1.0):
    with _conn() as db:
        db.execute(
            f"INSERT INTO shared_preferences (trip_id, preference_key, preference_value, weight) VALUES ({_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER},{_PLACEHOLDER})",
            (trip_id, key, value, weight),
        )


def get_preferences(trip_id: str) -> dict:
    with _conn() as db:
        rows = _execute_and_fetch(db, f"SELECT * FROM shared_preferences WHERE trip_id={_PLACEHOLDER}", (trip_id,))
    result = {}
    for r in rows:
        d = dict(r)
        k = d["preference_key"]
        if k not in result:
            result[k] = []
        result[k].append({"value": d["preference_value"], "weight": d["weight"]})
    return result
