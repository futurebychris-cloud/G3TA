"""Offline smoke test: stubs the LLM to force deterministic fallbacks, then runs
the full orchestration to verify wiring, cost math, and budget reconciliation.
Not part of the shipped app — used to sanity-check the base plate.
"""
import json

import agents.base as base
import orchestrator


def _boom(*a, **k):
    raise ValueError("stubbed LLM (offline test)")


# Force every LLM call to a non-RuntimeError so the deterministic fallbacks run.
# (RuntimeError is reserved for a missing key and is intentionally not swallowed.)
base.chat_json = _boom
orchestrator.chat_json = _boom

# A budget deliberately tight enough to trigger the housing-downgrade trade-off.
trip = {
    "location": "Tokyo",
    "origin": "New York",
    "dates": {"start": "2026-04-10", "end": "2026-04-14"},
    "budget": {"total": 2200, "currency": "USD"},
    "preferences": {
        "bites": ["ramen", "sushi"],
        "transportation_type": ["flight"],
        "activity_style": ["cultural", "adventure"],
    },
    "time_constraints": "fixed dates",
}

result = orchestrator.plan(trip)

print("SUMMARY:", result["summary"][:80])
print("DAYS:", len(result["schedule"]))
print("COST:", json.dumps(result["cost"], indent=2))
print("MAP POINTS:", len(result["map_points"]))
print("PACKING ITEMS:", len(result["packing_list"]))
print("REASONING LOG:")
for entry in result["reasoning_log"]:
    print(f"  [{entry['agent']}] {entry['note']}")

assert len(result["schedule"]) == 5, "expected 5 days"
assert result["cost"]["breakdown"]["transportation"] > 0
assert result["cost"]["total"] > 0
assert "housing" in result["cost"]["breakdown"]
print("\nSMOKE_TEST_OK")
