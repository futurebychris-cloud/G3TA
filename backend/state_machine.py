"""Validated state-machine reader for the G3TA planning flow.

The JSON follows the same compact node format as the supplied reference:
type 1 is an interactive instruction, type 2 is a message/result state, and
type 3 invokes a function. The chart documents planning through the final trip;
booking is intentionally outside its scope.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


VALID_NODE_TYPES = {1, 2, 3}


class StateMachine:
    """Load, validate, and traverse a node-based state chart."""

    def __init__(self, statechart_path: str | Path):
        self.statechart_path = Path(statechart_path)
        with self.statechart_path.open("r", encoding="utf-8") as chart_file:
            raw_nodes = json.load(chart_file)
        self.nodes = self._validate_nodes(raw_nodes)
        self.current_node_id: int | None = None
        self.context: dict[str, Any] = {}
        self.transition_log: list[dict[str, Any]] = []

    @staticmethod
    def _validate_nodes(raw_nodes: Any) -> dict[int, dict[str, Any]]:
        if not isinstance(raw_nodes, list) or not raw_nodes:
            raise ValueError("State chart must be a non-empty JSON array.")

        nodes: dict[int, dict[str, Any]] = {}
        for node in raw_nodes:
            if not isinstance(node, dict) or not isinstance(node.get("id"), int):
                raise ValueError("Every state-chart node must have an integer id.")
            node_id = node["id"]
            if node_id in nodes:
                raise ValueError(f"Duplicate state-chart node id: {node_id}")
            if node.get("type") not in VALID_NODE_TYPES:
                raise ValueError(f"Node {node_id} has an unsupported type.")
            if not isinstance(node.get("text"), str) or not node["text"].strip():
                raise ValueError(f"Node {node_id} must have descriptive text.")
            if node["type"] == 3:
                function = node.get("function")
                if not isinstance(function, dict) or not str(function.get("name", "")).strip():
                    raise ValueError(f"Function node {node_id} must name a function.")
                if not isinstance(function.get("parameters", []), list):
                    raise ValueError(f"Function node {node_id} parameters must be a list.")
            transitions = node.get("transition_list", [])
            if not isinstance(transitions, list):
                raise ValueError(f"Node {node_id} transition_list must be a list.")
            conditions = [transition.get("condition_text") for transition in transitions]
            if len(conditions) != len(set(conditions)):
                raise ValueError(f"Node {node_id} contains duplicate transition conditions.")
            nodes[node_id] = node

        if 0 not in nodes:
            raise ValueError("State chart must contain entry node 0.")
        for node_id, node in nodes.items():
            for transition in node.get("transition_list", []):
                if not isinstance(transition, dict):
                    raise ValueError(f"Node {node_id} contains an invalid transition.")
                if not isinstance(transition.get("condition_text"), str):
                    raise ValueError(f"Node {node_id} transition conditions must be strings.")
                target = transition.get("next_node_id")
                if target not in nodes:
                    raise ValueError(f"Node {node_id} points to missing node {target}.")
        return nodes

    def start(self, initial_node_id: int = 0) -> dict[str, Any]:
        if initial_node_id not in self.nodes:
            raise ValueError(f"Unknown initial node: {initial_node_id}")
        self.current_node_id = initial_node_id
        self._log_transition(None, initial_node_id, "start")
        return self.nodes[initial_node_id]

    def get_current_node(self) -> dict[str, Any]:
        if self.current_node_id is None:
            raise RuntimeError("State machine not started")
        return self.nodes[self.current_node_id]

    def transition(
        self,
        condition_text: str,
        context_update: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.current_node_id is None:
            raise RuntimeError("State machine not started")

        current_node = self.nodes[self.current_node_id]
        transition = next(
            (
                candidate
                for candidate in current_node.get("transition_list", [])
                if candidate["condition_text"] == condition_text
            ),
            None,
        )
        if transition is None:
            available = self.get_available_transitions()
            raise ValueError(
                f"No transition found for condition '{condition_text}' from node "
                f"{self.current_node_id}. Available: {available}"
            )

        if context_update:
            self.context.update(context_update)
        next_node_id = transition["next_node_id"]
        self._log_transition(self.current_node_id, next_node_id, condition_text)
        self.current_node_id = next_node_id
        return self.nodes[next_node_id]

    def get_available_transitions(self) -> list[str]:
        if self.current_node_id is None:
            return []
        return [
            transition["condition_text"]
            for transition in self.nodes[self.current_node_id].get("transition_list", [])
        ]

    def is_terminal(self) -> bool:
        return self.current_node_id is not None and not self.get_available_transitions()

    def _log_transition(self, from_id: int | None, to_id: int, condition: str) -> None:
        self.transition_log.append({
            "from_node_id": from_id,
            "to_node_id": to_id,
            "condition": condition,
            "context_snapshot": dict(self.context),
        })

    def get_transition_log(self) -> list[dict[str, Any]]:
        return [dict(entry) for entry in self.transition_log]

    def reset(self) -> None:
        self.current_node_id = None
        self.context.clear()
        self.transition_log.clear()


class OrchestrationStateMachine(StateMachine):
    """Convenience wrapper for the actual backend planning path."""

    def __init__(self):
        super().__init__(Path(__file__).parent.parent / "trip_planner_statechart.json")

    def start_planning(self, trip_input: dict[str, Any]) -> dict[str, Any]:
        self.reset()
        self.start(2)
        self.context["trip_input"] = trip_input
        return self.get_current_node()

    def input_valid(self, trip_input: dict[str, Any]) -> dict[str, Any]:
        return self.transition("Trip input is valid", {"trip_input": trip_input})

    def session_ready(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        return self.transition("Planning session is ready", {"trip_input": prepared_input})

    def budget_agent_complete(self, budget_output: dict[str, Any]) -> dict[str, Any]:
        return self.transition("Budget Agent completed", {"budget_output": budget_output})

    def specialist_agents_complete(self, agent_outputs: dict[str, Any]) -> dict[str, Any]:
        return self.transition("All specialist agents completed", {"agent_outputs": agent_outputs})

    def geography_valid(self) -> dict[str, Any]:
        return self.transition("Agent geography is valid")

    def itinerary_complete(self, itinerary: dict[str, Any]) -> dict[str, Any]:
        return self.transition("Final itinerary was synthesized", {"itinerary": itinerary})
