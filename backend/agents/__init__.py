"""The six specialist agents — v2 with real data pipelines.

Each module exposes `run(trip_input: dict) -> dict` and reasons over exactly one
domain. The Orchestrator is the only caller that sees all six outputs together.

v2 agents use Playwright/web scraping for real data (ticket prices, restaurant
searches, flights, weather API) instead of LLM-only estimates.
"""
import os

# Use v2 agents if the corresponding file exists (graceful fallback to v1)
def _load_agent(name: str):
    v2_path = os.path.join(os.path.dirname(__file__), f"{name}_agent_v2.py")
    if os.path.exists(v2_path):
        try:
            mod = __import__(f"agents.{name}_agent_v2", fromlist=[name])
            print(f"[agents] loaded {name}_agent_v2 (real-data pipeline)")
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
    "budget",          # completes first; its caps guide every recommendation agent
    "transportation",
    "housing",
    "activity",
    "food",
    "planning",
]
