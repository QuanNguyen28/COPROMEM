from __future__ import annotations

import unittest

from copromem.copromem_memory_module import MemoryInjectionResult
from copromem.learning import ActionObservation
from copromem.schema import DecompositionSchema
from copromem.types import DependencyEdge, SubtaskNode

from copromem_adapter import AlfworldCopromemController, TaskEntities


def descriptor(*operations: str) -> tuple[ActionObservation, ...]:
    events = []
    previous = ""
    for index, operation in enumerate(operations):
        output = f"slot_{index}"
        events.append(
            ActionObservation(
                operation,
                input_slots=(previous,) if previous else (),
                output_slots=(output,),
                check=f"verify {operation}",
            )
        )
        previous = output
    return tuple(events)


def retrieval(events: tuple[ActionObservation, ...], *, veto: bool = False):
    nodes = tuple(
        SubtaskNode(
            f"step_{index + 1}",
            "agent",
            event.operation,
            event.input_slots,
            event.output_slots,
        )
        for index, event in enumerate(events)
    )
    edges = tuple(
        DependencyEdge(nodes[index].node_id, nodes[index + 1].node_id)
        for index in range(len(nodes) - 1)
    )
    schema = DecompositionSchema(
        "schema_test",
        "alfworld:test",
        (),
        nodes,
        edges,
        structural_stats={
            "step_evidence": [
                {"precondition": event.precondition, "check": event.check}
                for event in events
            ]
        },
        status="provisional",
    )
    return MemoryInjectionResult(
        arm="copromem_v2",
        injected_text="retrieved procedure",
        schema=schema,
        selected_schema_id=schema.schema_id,
        should_veto=veto,
        separated=veto,
    )


class TaskEntityTests(unittest.TestCase):
    def test_parses_alfworld_task_templates(self) -> None:
        clean = TaskEntities.parse("clean some pan and put it in countertop.")
        self.assertEqual((clean.target, clean.destination, clean.transformation),
                         ("pan", "countertop", "clean"))
        pair = TaskEntities.parse("put two apple in cabinet.")
        self.assertEqual((pair.target, pair.destination, pair.quantity),
                         ("apple", "cabinet", 2))


class ControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.simple = descriptor(
            "inspect environment",
            "locate target object",
            "acquire target object",
            "locate destination receptacle",
            "place required object",
        )

    def test_dag_gates_wrong_object_and_wrong_destination(self) -> None:
        controller = AlfworldCopromemController(
            retrieval(self.simple),
            "put some watch on safe.",
            "task/watch",
            self.simple,
        )
        controller.initialize("You are in a bedroom.", ["look", "go to drawer 5"])
        decision = controller.decide(
            "The drawer contains a watch 1 and a box 1.",
            ["take box 1 from drawer 5", "take watch 1 from drawer 5", "look"],
        )
        self.assertEqual(decision.admissible, ["take watch 1 from drawer 5"])
        self.assertEqual(decision.active_intent, "acquire target object")

        controller.observe(
            decision.admissible[0],
            "You pick up the watch 1 from the drawer 5.",
            ["go to safe 1", "go to shelf 1"],
            done=False,
            won=False,
        )
        placement = controller.decide(
            "The safe 1 is open.",
            ["move watch 1 to safe 1", "move watch 1 to shelf 1", "look"],
        )
        self.assertEqual(placement.admissible, ["move watch 1 to safe 1"])
        self.assertEqual(placement.active_intent, "place required object")

    def test_transformation_checkpoint_is_enforced(self) -> None:
        clean_events = descriptor(
            "inspect environment",
            "locate target object",
            "acquire target object",
            "clean held object",
            "locate destination receptacle",
            "place required object",
        )
        controller = AlfworldCopromemController(
            retrieval(clean_events),
            "clean some pan and put it in countertop.",
            "task/pan",
            clean_events,
        )
        controller.initialize("Kitchen.", ["take pan 1 from stoveburner 1"])
        controller.observe(
            "take pan 1 from stoveburner 1",
            "You pick up the pan 1 from the stoveburner 1.",
            ["clean pan 1 with sinkbasin 1", "clean bowl 1 with sinkbasin 1", "go to countertop 1"],
            done=False,
            won=False,
        )
        decision = controller.decide(
            "You are holding the pan 1.",
            ["clean pan 1 with sinkbasin 1", "clean bowl 1 with sinkbasin 1", "move pan 1 to countertop 1"],
        )
        self.assertEqual(decision.admissible, ["clean pan 1 with sinkbasin 1"])
        self.assertEqual(decision.active_intent, "clean held object")

    def test_veto_disables_schema_enforcement(self) -> None:
        controller = AlfworldCopromemController(
            retrieval(self.simple, veto=True),
            "put some watch on safe.",
            "task/veto",
            self.simple,
        )
        actions = ["take box 1 from drawer 1", "take watch 1 from drawer 1", "look"]
        controller.initialize("Bedroom.", actions)
        decision = controller.decide("Bedroom.", actions)
        self.assertFalse(decision.gated)
        self.assertEqual(decision.admissible, actions)
        self.assertIn("vetoed", decision.guidance)

    def test_failed_episode_yields_honest_learning_evidence(self) -> None:
        controller = AlfworldCopromemController(
            retrieval(self.simple),
            "put some watch on safe.",
            "task/failure",
            self.simple,
        )
        controller.initialize("Bedroom.", ["look", "go to drawer 1"])
        evidence = controller.learning_events()
        self.assertTrue(evidence[0].observed)
        self.assertTrue(all(not event.observed for event in evidence[1:]))


if __name__ == "__main__":
    unittest.main()
