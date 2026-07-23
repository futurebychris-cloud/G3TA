"""Shared database for all G3TA agents — stores planning data across agent runs.

Supports both SQLite (default) and PostgreSQL (when DATABASE_URL is set).

Tables:
    shared_expenses     — Budget Agent: tracks all expenses across categories
    shared_activities   — Activity Agent: confirmed activities with metadata
    shared_meals        — Food Agent: confirmed restaurant/meal selections
    shared_transport    — Transportation Agent: confirmed routes & tickets
    shared_checklist    — Planning Agent: packing/checklist items
    shared_preferences  — User preferences & travel history
    shared_trips        — Trip metadata
"""
from __future__ import annotations

import os
import json
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
                status TEXT DEFAULT 'confirmed' CHECK(status IN ('pending','confirmed','cancelled')),
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
                status TEXT DEFAULT 'confirmed' CHECK(status IN ('pending','confirmed','ordered','cancelled')),
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS shared_transport (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id TEXT NOT NULL,
                transport_type TEXT NOT NULL CHECK(transport_type IN ('flight','train','bus','taxi','subway','bike','walk','ferry')),
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
                status TEXT DEFAULT 'confirmed' CHECK(status IN ('pending','confirmed','cancelled')),
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
                status TEXT DEFAULT 'confirmed' CHECK(status IN ('pending','confirmed','ordered','cancelled')),
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS shared_transport (
                id SERIAL PRIMARY KEY,
                trip_id TEXT NOT NULL,
                transport_type TEXT NOT NULL CHECK(transport_type IN ('flight','train','bus','taxi','subway','bike','walk','ferry')),
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
    "status": "confirmed",
    "booking_status": "pending",
    "scope": "national",
    "meal_slot": "",
    "activity_type": "",
    "dish_category": "",
}


def _sanitize_for_pg(table: str, vals: dict) -> dict:
    """Convert empty strings to valid defaults for PG columns."""
    if not _USE_POSTGRES:
        return vals
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


def mark_checklist_packed(item_id: int) -> None:
    with _conn() as db:
        db.execute(f"UPDATE shared_checklist SET is_packed=1 WHERE id={_PLACEHOLDER}", (item_id,))


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
