"""FastAPI surface for the planning subagent.

Run standalone (from backend/agents/planning_openweather/):
  uvicorn planning_agent.api:app --reload --port 8003

Endpoints:
  POST  /plan                          generate + persist a trip's plan
  GET   /plan/{trip_id}                fetch the stored plan (frontend page load)
  PATCH /plan/{trip_id}/check-item      toggle a checklist item's `checked` state
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .agent import PlanningAgent
from .models import PackingSummary, PlanningRequest, PlanningResponse
from .storage import load_plan, save_plan

app = FastAPI(title="Travel Planning Subagent")
_agent = PlanningAgent()


@app.post("/plan", response_model=PlanningResponse)
def create_plan(request: PlanningRequest) -> PlanningResponse:
    return _agent.generate_plan(request)


@app.get("/plan/{trip_id}", response_model=PlanningResponse)
def get_plan(trip_id: str) -> PlanningResponse:
    plan = load_plan(trip_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"No plan found for trip_id '{trip_id}'")
    return plan


class CheckItemRequest(BaseModel):
    category: str
    item_id: str
    checked: bool


@app.patch("/plan/{trip_id}/check-item", response_model=PlanningResponse)
def check_item(trip_id: str, body: CheckItemRequest) -> PlanningResponse:
    plan = load_plan(trip_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"No plan found for trip_id '{trip_id}'")

    for category in plan.categories:
        if category.category != body.category:
            continue
        for item in category.items:
            if item.id == body.item_id:
                item.checked = body.checked
                for packing_item in plan.packing_list:
                    if packing_item.id == body.item_id:
                        packing_item.checked = body.checked
                        break
                checked = sum(1 for i in plan.packing_list if i.checked)
                plan.packing_summary = PackingSummary(
                    total_items=len(plan.packing_list),
                    checked_items=checked,
                    remaining_items=len(plan.packing_list) - checked,
                )
                save_plan(plan)
                return plan
        raise HTTPException(status_code=404, detail=f"No item '{body.item_id}' in category '{body.category}'")

    raise HTTPException(status_code=404, detail=f"No category '{body.category}' in this plan")
