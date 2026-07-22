"""Backend dataset persistence for the planning agent.

A plain JSON-file-per-trip store. Swap this module's two functions for a real
database client later; nothing else in the package depends on the storage
mechanism.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import config
from .models import PlanningResponse


def _path_for(trip_id: str) -> Path:
    safe_id = "".join(c for c in trip_id if c.isalnum() or c in ("-", "_")) or "trip"
    return config.PLANNING_DATA_DIR / f"{safe_id}.json"


def save_plan(plan: PlanningResponse) -> None:
    path = _path_for(plan.trip_id)
    path.write_text(plan.model_dump_json(indent=2))


def load_plan(trip_id: str) -> PlanningResponse | None:
    path = _path_for(trip_id)
    if not path.exists():
        return None
    return PlanningResponse.model_validate(json.loads(path.read_text()))
