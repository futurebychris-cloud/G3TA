"""PostgreSQL connection-pool manager for G3TA.

Provides a thread-safe connection pool (ThreadedConnectionPool) and context
managers for connections and cursors. All queries return dict-like rows via
RealDictCursor so existing sqlite3.Row-based code needs minimal changes.

Configuration:
    DATABASE_URL  env var  — required PostgreSQL DSN
    DB_MIN_CONN   env var  — min pool size (default: 2)
    DB_MAX_CONN   env var  — max pool size (default: 10)

Usage:
    from booking.postgres_db import get_cursor

    with get_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (1,))
        row = cur.fetchone()  # RealDictRow → dict-like
"""
from __future__ import annotations

import os
from contextlib import contextmanager

from psycopg2 import pool
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

_MIN_CONN = int(os.environ.get("DB_MIN_CONN", 2))
_MAX_CONN = int(os.environ.get("DB_MAX_CONN", 10))

_connection_pool: pool.ThreadedConnectionPool | None = None


def _get_pool() -> pool.ThreadedConnectionPool:
    """Lazy-init the thread-safe connection pool."""
    global _connection_pool
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is required for operator booking records. "
            "No default database password is provided."
        )
    if _connection_pool is None:
        _connection_pool = pool.ThreadedConnectionPool(
            minconn=_MIN_CONN,
            maxconn=_MAX_CONN,
            dsn=DATABASE_URL,
        )
    return _connection_pool


@contextmanager
def get_conn():
    """Yield a raw psycopg2 connection from the pool (autocommit off).

    Commits on clean exit, rollbacks on exception, always returns the
    connection to the pool.
    """
    p = _get_pool()
    conn = p.getconn()
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        p.putconn(conn)


@contextmanager
def get_cursor():
    """Yield a psycopg2 cursor with RealDictCursor (dict-like rows).

    Wraps get_conn() so every cursor lives inside a transaction that is
    committed or rolled back automatically.
    """
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cur
        finally:
            cur.close()


def close_pool():
    """Close all pool connections (call on app shutdown)."""
    global _connection_pool
    if _connection_pool is not None:
        _connection_pool.closeall()
        _connection_pool = None
