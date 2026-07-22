"""Pydantic schemas for the planning subagent.

Split into two groups:
  * Inputs  - what the planning agent receives from the user and from the
              other subagents (activity agent, budget agent).
  * Outputs - the unified shape every one of the 5 category pages on the
              frontend consumes, so the frontend can render them "pretty
              much the same" as the prompt requires.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Inputs from other subagents
# ---------------------------------------------------------------------------

class ActivityItem(BaseModel):
    """One piece of equipment the activity agent says is needed."""

    name: str
    estimated_cost: float = Field(0.0, ge=0)
    required: bool = True
    usability_score: float = Field(0.5, ge=0, le=1)
    entertainment_score: float = Field(0.5, ge=0, le=1)


class ActivityAgentOutput(BaseModel):
    items: list[ActivityItem] = Field(default_factory=list)


class BudgetAgentOutput(BaseModel):
    leftover: float = Field(0.0, ge=0)
    shopping_budget: float = Field(0.0, ge=0)


class ShoppingPreference(BaseModel):
    """Relative weight the user places on usability vs. entertainment (0-1 each)."""

    usability: float = Field(0.5, ge=0, le=1)
    entertainment: float = Field(0.5, ge=0, le=1)

    @field_validator("usability", "entertainment")
    @classmethod
    def _clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class TripScope(str, Enum):
    NATIONAL = "national"
    INTERNATIONAL = "international"


class ResidencyStatus(str, Enum):
    CITIZEN = "citizen"
    PERMANENT_RESIDENT = "permanent_resident"
    VISA_HOLDER = "visa_holder"
    OTHER = "other"


class UserProfile(BaseModel):
    destination_city: str
    destination_country: str
    origin_country: str
    trip_start_date: date
    trip_end_date: date
    residency_status: ResidencyStatus = ResidencyStatus.CITIZEN
    hotel_amenities: list[str] = Field(default_factory=list)
    device_list: list[str] = Field(default_factory=list)

    @property
    def trip_scope(self) -> TripScope:
        same_country = self.destination_country.strip().lower() == self.origin_country.strip().lower()
        return TripScope.NATIONAL if same_country else TripScope.INTERNATIONAL

    @property
    def trip_duration_days(self) -> int:
        return max(1, (self.trip_end_date - self.trip_start_date).days)


class PlanningRequest(BaseModel):
    trip_id: str
    user_profile: UserProfile
    activity_output: ActivityAgentOutput
    budget_output: BudgetAgentOutput
    preference: ShoppingPreference = Field(default_factory=ShoppingPreference)


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

class ChecklistItem(BaseModel):
    id: str
    name: str
    note: Optional[str] = None
    checked: bool = False
    estimated_cost: Optional[float] = None
    status: Optional[str] = None  # e.g. "required" | "recommended" | "skipped_over_budget"
    category: Optional[str] = None  # set when flattened into PlanningResponse.packing_list


class CategoryResult(BaseModel):
    category: str
    summary: Optional[str] = None
    items: list[ChecklistItem] = Field(default_factory=list)


class PackingSummary(BaseModel):
    total_items: int
    checked_items: int
    remaining_items: int


class WeatherSummary(BaseModel):
    climate: str
    avg_weather: str
    avg_temp_c: float
    avg_humid_pct: float
    uv_index: Optional[float] = None
    source: str = "openweathermap"


class BudgetSummary(BaseModel):
    shopping_budget: float
    leftover: float
    total_available: float
    total_allocated: float
    remaining: float


class PlanningResponse(BaseModel):
    trip_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    weather: WeatherSummary
    budget_summary: BudgetSummary
    categories: list[CategoryResult]
    packing_list: list[ChecklistItem] = Field(default_factory=list)
    packing_summary: Optional[PackingSummary] = None
    flight_info: list[str]
