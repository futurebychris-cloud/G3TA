"""Repository-backed provider snapshots for fast, offline-first lookups."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any


DEFAULT_SNAPSHOT_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "provider_snapshots.json"
)

# These namespaces contain directory-like or slowly changing public metadata.
# Live schedules, availability, weather and transport prices are deliberately
# absent from this allow-list.
STATIC_NAMESPACES = {
    "activity-discovery",
    "budget-web-costs",
    "food-google-maps",
    "hotel-planning-search",
}

_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "cookie_string",
    "email",
    "id_number",
    "password",
    "phone",
    "session",
    "session_id",
    "token",
}

_VOLATILE_KEYS_BY_NAMESPACE = {
    "activity-discovery": {
        "availability",
        "price",
        "ticket_price",
        "total_price",
    },
    "hotel-planning-search": {
        "availability",
        "discount",
        "price",
        "price_per_night",
        "rooms",
        "total_cost",
    },
}

_LOCK = threading.RLock()
_LOADED_PATH: Path | None = None
_LOADED_MTIME_NS: int | None = None
_INDEX: dict[tuple[str, str], Any] = {}
_SCOPE_INDEX: dict[tuple[str, str], Any] = {}


def snapshot_path() -> Path:
    configured = os.getenv("G3TA_PROVIDER_SNAPSHOT_PATH", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_SNAPSHOT_PATH


def snapshots_enabled() -> bool:
    """Snapshots are an explicit offline aid, never a silent live-data fallback."""
    return os.getenv("G3TA_ALLOW_PROVIDER_SNAPSHOTS", "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def sanitize_snapshot_payload(namespace: str, value: Any) -> Any:
    """Remove secrets/PII and fields that become misleading when snapshotted."""
    volatile = _VOLATILE_KEYS_BY_NAMESPACE.get(namespace, set())
    if isinstance(value, dict):
        return {
            key: sanitize_snapshot_payload(namespace, child)
            for key, child in value.items()
            if key.casefold() not in _SENSITIVE_KEYS
            and key.casefold() not in volatile
        }
    if isinstance(value, list):
        return [sanitize_snapshot_payload(namespace, child) for child in value]
    if isinstance(value, tuple):
        return [sanitize_snapshot_payload(namespace, child) for child in value]
    return value


def snapshot_scope_key(namespace: str, query: Any) -> str | None:
    """Build a stable key that omits volatile inputs such as hotel dates."""
    if namespace == "hotel-planning-search":
        if not isinstance(query, (list, tuple)) or not query:
            return None
        scope = {"location": str(query[0]).strip().casefold()}
    elif namespace == "budget-web-costs":
        scope = {"location": str(query).strip().casefold()}
    elif namespace in {"activity-discovery", "food-google-maps"}:
        if not isinstance(query, (list, tuple)) or not query:
            return None
        scope = {
            "location": str(query[0]).strip().casefold(),
            "filters": query[1] if len(query) > 1 else [],
        }
    else:
        return None
    encoded = json.dumps(
        scope, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _load_index() -> dict[tuple[str, str], Any]:
    global _LOADED_PATH, _LOADED_MTIME_NS, _INDEX, _SCOPE_INDEX

    path = snapshot_path()
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        return {}

    with _LOCK:
        if path == _LOADED_PATH and mtime_ns == _LOADED_MTIME_NS:
            return _INDEX
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            if document.get("schema_version") != 1:
                raise ValueError("unsupported provider snapshot schema")
            entries = document.get("entries", [])
            index = {
                (entry["namespace"], entry["cache_key"]): entry["payload"]
                for entry in entries
                if entry.get("namespace") in STATIC_NAMESPACES
                and entry.get("cache_key")
                and "payload" in entry
            }
            scope_index = {
                (entry["namespace"], entry["scope_key"]): entry["payload"]
                for entry in entries
                if entry.get("namespace") in STATIC_NAMESPACES
                and entry.get("scope_key")
                and "payload" in entry
            }
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            print(f"[provider_snapshot] unable to load {path}: {exc}")
            index = {}
            scope_index = {}
        _LOADED_PATH = path
        _LOADED_MTIME_NS = mtime_ns
        _INDEX = index
        _SCOPE_INDEX = scope_index
        return _INDEX


def get_provider_snapshot(
    namespace: str, cache_key: str, query: Any = None
) -> Any | None:
    if not snapshots_enabled() or namespace not in STATIC_NAMESPACES:
        return None
    value = _load_index().get((namespace, cache_key))
    if value is None and query is not None:
        scope_key = snapshot_scope_key(namespace, query)
        if scope_key:
            value = _SCOPE_INDEX.get((namespace, scope_key))
    if value is None:
        return None
    marked = copy.deepcopy(value)
    if isinstance(marked, list):
        marked = [
            {
                **item,
                "snapshot_original_source": item.get("source", ""),
                "source": "repository_snapshot",
                "verification_required": True,
            }
            if isinstance(item, dict)
            else item
            for item in marked
        ]
    elif isinstance(marked, dict):
        marked["__g3ta_snapshot__"] = True
    return marked


def reset_snapshot_cache() -> None:
    global _LOADED_PATH, _LOADED_MTIME_NS, _INDEX, _SCOPE_INDEX
    with _LOCK:
        _LOADED_PATH = None
        _LOADED_MTIME_NS = None
        _INDEX = {}
        _SCOPE_INDEX = {}
