#!/usr/bin/env python3
"""Export safe, non-real-time provider records into a Git-friendly JSON file."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from booking.shared_db import get_provider_cache, list_provider_cache
from services.provider_snapshots import (
    DEFAULT_SNAPSHOT_PATH,
    STATIC_NAMESPACES,
    sanitize_snapshot_payload,
    snapshot_scope_key,
)


def _has_useful_data(payload) -> bool:
    if isinstance(payload, (list, tuple, set, dict)):
        return len(payload) > 0
    return payload is not None


def export_snapshots(output: Path) -> dict:
    entries = []
    for metadata in list_provider_cache(limit=1000):
        namespace = metadata["namespace"]
        if namespace not in STATIC_NAMESPACES:
            continue
        payload = get_provider_cache(namespace, metadata["cache_key"])
        if not _has_useful_data(payload):
            continue
        query = json.loads(metadata["query_json"])
        entries.append(
            {
                "namespace": namespace,
                "cache_key": metadata["cache_key"],
                "query_json": metadata["query_json"],
                "scope_key": snapshot_scope_key(namespace, query),
                "source": metadata["source"],
                "captured_at_epoch": metadata["fetched_at_epoch"],
                "payload": sanitize_snapshot_payload(namespace, payload),
            }
        )

    document = {
        "schema_version": 1,
        "kind": "static_provider_snapshot",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "attribution": {
            "openstreetmap": "© OpenStreetMap contributors (ODbL)"
        },
        "excluded_data": [
            "credentials and personal information",
            "cookies and session tokens",
            "flight and train availability",
            "live transport and hotel prices",
            "weather",
        ],
        "entries": sorted(
            entries, key=lambda item: (item["namespace"], item["cache_key"])
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return document


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_SNAPSHOT_PATH)
    args = parser.parse_args()
    document = export_snapshots(args.output)
    print(f"exported {len(document['entries'])} entries to {args.output}")


if __name__ == "__main__":
    main()
