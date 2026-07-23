import json
import unittest
from pathlib import Path

from state_machine import OrchestrationStateMachine, StateMachine


CHART_PATH = Path(__file__).parents[2] / "trip_planner_statechart.json"


class StateChartTests(unittest.TestCase):
    def test_chart_matches_reference_node_shape_and_has_no_dangling_edges(self):
        nodes = json.loads(CHART_PATH.read_text(encoding="utf-8"))
        ids = {node["id"] for node in nodes}

        self.assertEqual(len(ids), len(nodes))
        self.assertTrue(all(node["type"] in {1, 2, 3} for node in nodes))
        self.assertTrue(all(
            transition["next_node_id"] in ids
            for node in nodes
            for transition in node.get("transition_list", [])
        ))
        self.assertEqual(next(node for node in nodes if node["id"] == 8).get("transition_list", []), [])

    def test_main_planning_path_ends_at_planned_trip(self):
        machine = StateMachine(CHART_PATH)

        machine.start()
        machine.transition("User chooses the standard trip brief")
        machine.transition("User submits the trip brief")
        machine.transition("Trip input is valid")
        machine.transition("Planning session is ready")
        machine.transition("Budget Agent completed")
        machine.transition("All specialist agents completed")
        machine.transition("Agent geography is valid")
        final_node = machine.transition("Final itinerary was synthesized")

        self.assertEqual(final_node["id"], 8)
        self.assertIn("planned trip is ready", final_node["text"])
        self.assertTrue(machine.is_terminal())

    def test_voice_path_returns_to_reviewable_main_form(self):
        machine = StateMachine(CHART_PATH)

        machine.start()
        machine.transition("User chooses voice-guided setup")
        machine.transition("User starts guided setup")
        machine.transition("User provides an answer")
        machine.transition("All guided questions were answered")
        machine.transition("All required details are present")
        main_form = machine.transition("User fills the main form with the draft")

        self.assertEqual(main_form["id"], 1)

    def test_orchestration_wrapper_tracks_real_agent_outputs(self):
        machine = OrchestrationStateMachine()

        machine.start_planning({"location": "Milan, Italy"})
        machine.input_valid({"location": "Milan, Italy"})
        machine.session_ready({"location": "Milan, Italy", "trip_id": "trip-1"})
        machine.budget_agent_complete({"daily_caps": {"food": 50}})
        machine.specialist_agents_complete({"food": {"destination": "Milan, Italy"}})
        machine.geography_valid()
        final_node = machine.itinerary_complete({"destination": "Milan, Italy"})

        self.assertEqual(final_node["id"], 8)
        self.assertEqual(machine.context["itinerary"]["destination"], "Milan, Italy")


if __name__ == "__main__":
    unittest.main()
