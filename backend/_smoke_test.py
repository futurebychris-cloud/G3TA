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
from agents import food_agent


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

# Regression matrix: food limits are dynamic for any trip length/cap, not a
# special-case $60 value. The displayed total must equal the sum of meal prices.
food_cap_cases = [
    (3, 12.50),
    (6, 10),
    (9, 35),
]
for case_days, daily_cap in food_cap_cases:
    case_trip = {
        **trip,
        "dates": {"start": "2026-04-10", "end": f"2026-04-{9 + case_days:02d}"},
        "_budget_caps": {"food": daily_cap},
    }
    food_result = food_agent.run(case_trip)
    meal_prices = [
        meal["price"]
        for day in food_result["daily_meals"]
        for meal in day["meals"]
    ]
    assert len(meal_prices) == case_days * 3
    assert round(sum(meal_prices), 2) == food_result["cost"]
    assert food_result["cost"] <= daily_cap * case_days, (
        case_days,
        daily_cap,
        food_result["cost"],
    )

print("SHANGHAI_DESTINATION_ISOLATION_OK")
print("DYNAMIC_FOOD_CAP_MATRIX_OK", food_cap_cases)
