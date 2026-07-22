"""LEGAL category: ID/passport/visa reminders based on national vs international travel.

Deliberately conservative on visas: this agent flags "verify requirements" rather
than asserting a definitive visa rule, since entry requirements change often and
depend on exact nationality + destination pairs that a static table can't track
reliably.
"""

from __future__ import annotations

from ..models import CategoryResult, ChecklistItem, ResidencyStatus, TripScope, UserProfile
from ..reference_data import INTERNATIONAL_DOCS_BASE, NATIONAL_DOCS


def build_legal_category(user_profile: UserProfile) -> CategoryResult:
    checklist: list[ChecklistItem] = []
    next_id = 0

    def add(name: str, note: str) -> None:
        nonlocal next_id
        checklist.append(ChecklistItem(id=f"legal-{next_id}", name=name, note=note, checked=False))
        next_id += 1

    if user_profile.trip_scope == TripScope.NATIONAL:
        for doc in NATIONAL_DOCS:
            add(doc, "Domestic trip — no international travel documents required.")
    else:
        for doc in INTERNATIONAL_DOCS_BASE:
            add(doc, f"Required for international travel to {user_profile.destination_country}.")

        if user_profile.residency_status == ResidencyStatus.PERMANENT_RESIDENT:
            add("green card / permanent resident card",
                "Carry alongside your passport to re-enter your resident country.")
        if user_profile.residency_status == ResidencyStatus.VISA_HOLDER:
            add("current visa documentation",
                "Confirm it remains valid for your travel dates and permits re-entry if applicable.")

        add(f"visa requirement check for {user_profile.destination_country}",
            "Verify with the destination's official immigration site or embassy — "
            "requirements depend on your nationality and can change without notice.")

    summary = f"{user_profile.trip_scope.value.title()} trip — {len(checklist)} document(s) to prepare."
    return CategoryResult(category="legal", summary=summary, items=checklist)
