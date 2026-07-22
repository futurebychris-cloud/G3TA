"""Offline regression test for destination isolation and full orchestration.

Both service-level and agent-level DeepSeek calls are stubbed so the test proves
that safe fallbacks remain tied to the requested destination and never leak the
retired Tokyo demo catalog.
"""
import json
import os as _os

# Load .env from project root so hotel APIs etc are available
from dotenv import load_dotenv
_env_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".env")
if _os.path.exists(_env_path):
    load_dotenv(_env_path)

import agents.base as agent_base
import orchestrator
import services._ai as service_ai


def _offline(*args, **kwargs):
    raise ValueError("stubbed LLM (offline regression test)")


agent_base.chat_json = _offline
service_ai.chat_json = _offline
orchestrator.chat_json = _offline

trip = {
    "location": "Shanghai",
    "origin": "New York",
    "dates": {"start": "2026-08-05", "end": "2026-08-17"},
    "budget": {"total": 5000, "currency": "USD"},
    "preferences": {
        "bites": ["Thai"],
        "transportation_type": ["flight"],
        "activity_style": ["cultural", "adventure", "relaxed"],
    },
    "time_constraints": "fixed dates",
}

result = orchestrator.plan(trip)
serialized = json.dumps(result, ensure_ascii=False).casefold()

print("SUMMARY:", result["summary"][:100])
print("DAYS:", len(result["schedule"]))
print("COST:", json.dumps(result["cost"], indent=2))
print("DESTINATION:", result["destination"])

assert result["destination"] == "Shanghai"
assert len(result["schedule"]) == 13
assert [day["date"] for day in result["schedule"]] == [
    f"2026-08-{day:02d}" for day in range(5, 18)
]
assert "tokyo" not in serialized
assert "asakusa" not in serialized
assert "shibuya" not in serialized
assert '"nrt"' not in serialized

for agent_name, output in result["agent_outputs"].items():
    assert output.get("destination") == "Shanghai", (agent_name, output.get("destination"))

meal_cuisines = {
    meal["cuisine"]
    for day in result["agent_outputs"]["food"]["daily_meals"]
    for meal in day["meals"]
}
assert meal_cuisines == {"Thai"}, meal_cuisines

activity_names = [
    activity["name"] for activity in result["agent_outputs"]["activity"]["recommended"]
]
assert len(activity_names) == 13
assert len(activity_names) == len(set(activity_names))

scheduled_activity_names = [
    item["title"]
    for day in result["schedule"]
    for item in day["items"]
    if item["type"] == "activity"
]
assert len(scheduled_activity_names) == 13
assert len(scheduled_activity_names) == len(set(scheduled_activity_names))

print("SHANGHAI_DESTINATION_ISOLATION_OK")
