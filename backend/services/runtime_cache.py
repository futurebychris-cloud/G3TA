"""Small in-process TTL cache for slow, read-only provider lookups.

The planner repeatedly asks for the same city/date data while agents hand work
to one another. Caching those results avoids reopening browsers and repeating
network calls without changing the public agent contracts.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
import time
from collections.abc import Callable
from typing import Any

_CACHE: dict[tuple[str, str], tuple[float, Any]] = {}
_LOCK = threading.RLock()


def _disabled() -> bool:
    return bool(
        os.getenv("PYTEST_CURRENT_TEST")
        or os.getenv("G3TA_DISABLE_RUNTIME_CACHE", "").lower() in {"1", "true", "yes"}
    )


def cached_call(
    namespace: str,
    key: object,
    loader: Callable[[], Any],
    *,
    ttl_seconds: float = 600,
    persist: bool = False,
    source: str = "playwright",
    snapshot: bool = False,
) -> Any:
    """Return a copied cached value or execute ``loader`` once.

    Values are deep-copied on read/write because several agents normalize and
    enrich provider dictionaries in place.
    """
    if _disabled():
        return loader()

    try:
        query_json = json.dumps(
            key,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    except (TypeError, ValueError):
        query_json = repr(key)
    key_digest = hashlib.sha256(query_json.encode("utf-8")).hexdigest()
    cache_key = (namespace, key_digest)
    now = time.monotonic()
    with _LOCK:
        hit = _CACHE.get(cache_key)
        if hit and hit[0] > now:
            return copy.deepcopy(hit[1])

    provider_db_enabled = False
    if persist:
        try:
            from booking import shared_db

            provider_db_enabled = shared_db._USE_POSTGRES
            if provider_db_enabled:
                persisted = shared_db.get_provider_cache(namespace, key_digest)
                if persisted is not None:
                    with _LOCK:
                        _CACHE[cache_key] = (
                            now + max(float(ttl_seconds), 1),
                            copy.deepcopy(persisted),
                        )
                    return copy.deepcopy(persisted)
        except Exception as exc:
            # Persistence is an optimization. A missing/unavailable database
            # must never make the planning request fail.
            print(f"[runtime_cache] persistent read unavailable for {namespace}: {exc}")

    if snapshot:
        try:
            from services.provider_snapshots import get_provider_snapshot

            snapshotted = get_provider_snapshot(namespace, key_digest, key)
            if snapshotted is not None:
                with _LOCK:
                    _CACHE[cache_key] = (
                        now + max(float(ttl_seconds), 1),
                        copy.deepcopy(snapshotted),
                    )
                return copy.deepcopy(snapshotted)
        except Exception as exc:
            print(f"[runtime_cache] snapshot read unavailable for {namespace}: {exc}")

    value = loader()
    with _LOCK:
        _CACHE[cache_key] = (now + max(ttl_seconds, 1), copy.deepcopy(value))

    if persist and provider_db_enabled:
        try:
            from booking.shared_db import save_provider_cache

            save_provider_cache(
                namespace,
                key_digest,
                query_json,
                value,
                source=source,
                ttl_seconds=ttl_seconds,
            )
        except Exception as exc:
            print(f"[runtime_cache] persistent write unavailable for {namespace}: {exc}")
    return value


def clear_runtime_cache() -> None:
    with _LOCK:
        _CACHE.clear()
