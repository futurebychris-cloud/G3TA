"""ITEM category: activity-equipment shopping list, budget-constrained.

Required (activity-essential) items are greedily fit into the available
budget first (cheapest first, to maximize coverage of must-haves). Whatever
budget remains is spent on optional/entertainment items, ranked by how well
they match the user's usability-vs-entertainment preference.
"""

from __future__ import annotations

from ..models import ActivityAgentOutput, BudgetAgentOutput, CategoryResult, ChecklistItem, ShoppingPreference


def build_items_category(
    activity_output: ActivityAgentOutput,
    budget_output: BudgetAgentOutput,
    preference: ShoppingPreference,
) -> tuple[CategoryResult, float]:
    total_available = budget_output.shopping_budget + budget_output.leftover
    required = sorted((i for i in activity_output.items if i.required), key=lambda i: i.estimated_cost)
    optional = [i for i in activity_output.items if not i.required]

    checklist: list[ChecklistItem] = []
    spent = 0.0
    next_id = 0

    def add(item, status: str, note: str) -> None:
        nonlocal next_id
        checklist.append(ChecklistItem(
            id=f"item-{next_id}",
            name=item.name,
            note=note,
            checked=False,
            estimated_cost=item.estimated_cost,
            status=status,
        ))
        next_id += 1

    for item in required:
        if spent + item.estimated_cost <= total_available:
            spent += item.estimated_cost
            add(item, "required", "Needed for your planned activities.")
        else:
            add(item, "skipped_over_budget",
                "Required for an activity but doesn't fit the current shopping budget.")

    # Rank optional items by preference-weighted value per dollar (cheap, well-matched items first).
    def value_score(item) -> float:
        weighted = preference.usability * item.usability_score + preference.entertainment * item.entertainment_score
        return weighted / max(item.estimated_cost, 1.0)

    for item in sorted(optional, key=value_score, reverse=True):
        if spent + item.estimated_cost <= total_available:
            spent += item.estimated_cost
            add(item, "recommended", "Matches your usability/entertainment preferences and fits your budget.")
        else:
            add(item, "skipped_over_budget", "Would exceed the remaining shopping budget.")

    summary = f"${spent:.2f} of ${total_available:.2f} allocated across {len(checklist)} item(s)."
    return CategoryResult(category="items", summary=summary, items=checklist), spent
