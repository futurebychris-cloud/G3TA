"""The six specialist agents — v2 with provider-first data pipelines.

Each module exposes `run(trip_input: dict) -> dict` and reasons over exactly one
domain. The Orchestrator is the only caller that sees all six outputs together.

v2 agents prefer public/provider records and preserve clearly labeled estimates
when a live source is unavailable.
"""
import os

# Use v2 agents if the corresponding file exists (graceful fallback to v1)
def _load_agent(name: str):
    v2_path = os.path.join(os.path.dirname(__file__), f"{name}_agent_v2.py")
    if os.path.exists(v2_path):
        try:
            mod = __import__(f"agents.{name}_agent_v2", fromlist=[name])
            print(f"[agents] loaded {name}_agent_v2 (provider-first pipeline)")
            return mod
        except Exception as e:
            print(f"[agents] v2 agent '{name}' import failed ({e}), falling back to v1")
    mod = __import__(f"agents.{name}_agent", fromlist=[name])
    return mod

# Load agents (v2 preferred, v1 fallback)
activity_agent = _load_agent("activity")
budget_agent = _load_agent("budget")
food_agent = _load_agent("food")
housing_agent = __import__("agents.housing_agent", fromlist=["housing"])
planning_agent = _load_agent("planning")
transportation_agent = _load_agent("transportation")

AGENT_ORDER = [
    "transportation",  # completes first so Budget uses a route-grounded cost
    "budget",
    "activity",
    "housing",
    "food",
    "planning",
]
