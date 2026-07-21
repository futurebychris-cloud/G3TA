"""The six specialist agents.

Each module exposes `run(trip_input: dict) -> dict` and reasons over exactly one
domain using exactly one service. The Orchestrator is the only caller that sees
all six outputs together. See docs/AGENT_HANDOFF.md for each agent's exact
input/output contract.
"""

AGENT_ORDER = [
    "budget",
    "transportation",
    "housing",
    "food",
    "activity",
    "planning",
]
