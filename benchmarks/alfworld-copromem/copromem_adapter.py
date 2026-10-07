"""Structured CoProMem execution adapter for the ALFWorld text environment.

CoProMem deliberately keeps environment execution outside its learning core.  This
adapter turns a ``MemoryInjectionResult`` into an executable, observable policy:
it follows the retrieved DAG, verifies ALFWorld milestones, gates out-of-order
actions, honours retrieval vetoes, and records contract checks for the run log.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Sequence

from copromem.copromem_memory_module import MemoryInjectionResult
from copromem.learning import ActionObservation
from copromem.schema import DecompositionSchema
from copromem.types import HandoffEvent, SubtaskNode


_SEARCH_VERBS = ("go to ", "open ", "look", "examine ", "inventory")
ADAPTER_VERSION = "alfworld-structured-core-v1"


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _words(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def _mentions(value: str, entity: str) -> bool:
    """Match ALFWorld's compact object names without matching arbitrary substrings."""
    if not entity:
        return False
    compact_entity = _compact(entity)
    return any(_compact(word) == compact_entity for word in _words(value))


def _starts_with_any(value: str, prefixes: Iterable[str]) -> bool:
    lowered = value.lower().strip()
    return any(lowered == prefix.rstrip() or lowered.startswith(prefix) for prefix in prefixes)


@dataclass(frozen=True)
class TaskEntities:
    target: str = ""
    destination: str = ""
    transformation: str = ""
    quantity: int = 1
    light_source: str = "desklamp"

    @classmethod
    def parse(cls, task: str) -> "TaskEntities":
        text = " ".join(task.lower().replace("-", " ").split())
        transformation = next(
            (name for name in ("clean", "heat", "cool") if re.search(rf"\b{name}\b", text)),
            "",
        )
        quantity = 2 if re.search(r"\b(?:two|2)\b", text) else 1

        target = ""
        patterns = []
        if transformation:
            patterns.append(
                rf"\b{transformation}\s+(?:(?:some|a|an|the|two|2)\s+)?([a-z][a-z0-9_]*)"
            )
        patterns.extend(
            (
                r"\bput\s+(?:(?:some|a|an|the|two|2)\s+)?([a-z][a-z0-9_]*)",
                r"\blook\s+at\s+(?:(?:some|a|an|the)\s+)?([a-z][a-z0-9_]*)",
                r"\bexamine\s+(?:(?:some|a|an|the)\s+)?([a-z][a-z0-9_]*)",
            )
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                target = match.group(1)
                break

        destinations = re.findall(
            r"\b(?:in|on|into|onto|under)\s+(?:(?:some|a|an|the)\s+)?([a-z][a-z0-9_]*)",
            text,
        )
        destination = destinations[-1] if destinations else ""
        light_source = destination if "look at" in text and destination else "desklamp"
        return cls(target, destination, transformation, quantity, light_source)


@dataclass
class ControlDecision:
    admissible: list[str]
    guidance: str
    active_node_id: str | None
    active_intent: str | None
    gated: bool
    original_action_count: int
    allowed_action_count: int
    fallback: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AlfworldCopromemController:
    """Execute the structured portion of a CoProMem retrieval result.

    The controller is strict only for a compatible retrieved schema.  Unknown,
    exploratory, or vetoed retrievals remain ungated so anti-lock-in is preserved.
    In all modes it passively tracks observable milestones for learning evidence.
    """

    result: MemoryInjectionResult
    task: str
    task_id: str
    descriptor: tuple[ActionObservation, ...]
    entities: TaskEntities = field(init=False)
    schema: DecompositionSchema | None = field(init=False)
    enabled: bool = field(init=False)
    completed: set[str] = field(default_factory=set, init=False)
    verified_operations: set[str] = field(default_factory=set, init=False)
    action_history: list[str] = field(default_factory=list, init=False)
    contract_checks: list[dict[str, Any]] = field(default_factory=list, init=False)
    blocked_contract_edges: dict[tuple[str, str], str] = field(
        default_factory=dict, init=False
    )
    checked_contract_edges: set[tuple[str, str]] = field(
        default_factory=set, init=False
    )
    transitions: list[dict[str, Any]] = field(default_factory=list, init=False)
    held_target: bool = field(default=False, init=False)
    transformed_target: bool = field(default=False, init=False)
    successful_placements: int = field(default=0, init=False)
    _last_observation: str = field(default="", init=False)
    _last_admissible: list[str] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.entities = TaskEntities.parse(self.task)
        self.schema = self.result.schema
        if (
            self.schema is None
            and self.result.alternative_schema is not None
            and not self.result.should_veto
            and not self.result.should_explore
        ):
            self.schema = self.result.alternative_schema
        self.enabled = bool(self.schema is not None and not self.result.should_veto)

    @property
    def nodes(self) -> list[SubtaskNode]:
        return self.schema.topological_sort() if self.schema is not None else []

    def initialize(self, observation: str, admissible: Sequence[str]) -> None:
        self._last_observation = observation
        self._last_admissible = list(admissible)
        self._advance_observable_milestones(observation, admissible, won=False)

    def decide(self, observation: str, admissible: Sequence[str]) -> ControlDecision:
        original = list(admissible)
        self._last_observation = observation
        self._last_admissible = original
        self._advance_observable_milestones(observation, original, won=False)
        active = self.active_node()

        if not self.enabled or active is None:
            return ControlDecision(
                admissible=original,
                guidance=self._render_guidance(active, gated=False),
                active_node_id=active.node_id if active else None,
                active_intent=active.intent if active else None,
                gated=False,
                original_action_count=len(original),
                allowed_action_count=len(original),
            )

        allowed = self._allowed_for(active, original)
        fallback = False
        if not allowed:
            # Fail open only when the adapter cannot map the domain commands.  This
            # avoids deadlocking on a new ALFWorld command vocabulary and is logged.
            allowed = original
            fallback = True
        return ControlDecision(
            admissible=allowed,
            guidance=self._render_guidance(active, gated=True, fallback=fallback),
            active_node_id=active.node_id,
            active_intent=active.intent,
            gated=True,
            original_action_count=len(original),
            allowed_action_count=len(allowed),
            fallback=fallback,
        )

    def observe(
        self,
        action: str,
        observation: str,
        admissible: Sequence[str],
        *,
        done: bool,
        won: bool,
    ) -> dict[str, Any]:
        before = self.active_node()
        accepted = self._action_confirmed(action, observation)
        self.action_history.append(action)
        self._last_observation = observation
        self._last_admissible = list(admissible)

        lowered = action.lower().strip()
        if accepted and lowered.startswith("take ") and _mentions(action, self.entities.target):
            self.held_target = True
            self._verify_operation("locate target object")
            self._verify_operation("acquire target object")
        if accepted and self.entities.transformation and lowered.startswith(
            self.entities.transformation + " "
        ) and _mentions(action, self.entities.target):
            self.transformed_target = True
            self._verify_operation(f"{self.entities.transformation} held object")
        if accepted and self._is_correct_placement(action):
            self.successful_placements += 1
            self.held_target = False
            if won or self.successful_placements >= self.entities.quantity:
                self._verify_operation("place required object")
            else:
                # A two-object task repeats the acquisition subgraph before the
                # terminal placement can be verified.
                self._reset_operation("locate target object")
                self._reset_operation("acquire target object")
        if accepted and self._is_light_action(action) and won:
            self._verify_operation("examine object under light")

        self._advance_observable_milestones(observation, admissible, won=won)
        self._check_contract_boundaries(action, observation, accepted)
        after = self.active_node()
        transition = {
            "action_accepted": accepted,
            "active_before": before.node_id if before else None,
            "active_after": after.node_id if after else None,
            "completed_nodes": sorted(self.completed),
            "verified_operations": sorted(self.verified_operations),
            "won": won,
            "done": done,
        }
        self.transitions.append(transition)
        return transition

    def active_node(self) -> SubtaskNode | None:
        if self.schema is None:
            return None
        if self.blocked_contract_edges:
            source_id = next(iter(self.blocked_contract_edges))[0]
            return next((node for node in self.nodes if node.node_id == source_id), None)
        predecessors: dict[str, set[str]] = {node.node_id: set() for node in self.nodes}
        for edge in self.schema.edges:
            predecessors[edge.target_node].add(edge.source_node)
        for node in self.nodes:
            if node.node_id in self.completed:
                continue
            if predecessors[node.node_id].issubset(self.completed):
                return node
        return None

    def learning_events(self) -> tuple[ActionObservation, ...]:
        """Return the adapter descriptor with honest per-step observation flags."""
        return tuple(
            ActionObservation(
                event.operation,
                event.input_slots,
                event.output_slots,
                event.precondition,
                event.check,
                dict(event.parameters),
                self._operation_verified(event.operation),
            )
            for event in self.descriptor
        )

    def summary(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "veto_applied": bool(self.result.should_veto),
            "exploration_requested": bool(self.result.should_explore),
            "schema_id": self.schema.schema_id if self.schema else None,
            "entities": asdict(self.entities),
            "completed_nodes": sorted(self.completed),
            "verified_operations": sorted(self.verified_operations),
            "contract_checks": list(self.contract_checks),
            "blocked_contract_edges": [
                {"source": source, "target": target, "recovery_route": route}
                for (source, target), route in self.blocked_contract_edges.items()
            ],
            "successful_placements": self.successful_placements,
            "transition_count": len(self.transitions),
        }

    def _render_guidance(
        self, active: SubtaskNode | None, *, gated: bool, fallback: bool = False
    ) -> str:
        lines = []
        if self.result.injected_text.strip():
            lines.append(self.result.injected_text.strip())
        lines.append("# CoProMem structured controller")
        if self.result.should_veto:
            lines.append(
                "The retrieved workflow was vetoed as incompatible. Build a fresh plan from "
                "the current observable state; no stored DAG is being enforced."
            )
        elif self.result.should_explore and self.schema is None:
            lines.append(
                "No compatible admitted workflow is available. Explore from observable state "
                "and verify each milestone before depending on it."
            )
        if self.schema is not None:
            lines.append(f"Schema: {self.schema.schema_id} ({self.schema.status}).")
        lines.append(
            "Task slots: "
            f"target={self.entities.target or 'unknown'}, "
            f"destination={self.entities.destination or 'unknown'}, "
            f"transformation={self.entities.transformation or 'none'}, "
            f"quantity={self.entities.quantity}."
        )
        if active is not None:
            lines.append(f"Active checkpoint: {active.node_id} — {active.intent}.")
            if active.input_keys:
                lines.append("Required inputs: " + ", ".join(active.input_keys) + ".")
            if active.output_keys:
                lines.append("Produce and verify: " + ", ".join(active.output_keys) + ".")
            evidence = self._evidence_for(active)
            if evidence.get("precondition"):
                lines.append("Precondition: " + str(evidence["precondition"]) + ".")
            if evidence.get("check"):
                lines.append("Verification: " + str(evidence["check"]) + ".")
            recoveries = [
                route
                for (source, _target), route in self.blocked_contract_edges.items()
                if source == active.node_id
            ]
            if recoveries:
                lines.append("Contract recovery required: " + "; ".join(recoveries) + ".")
        if gated:
            lines.append(
                "The admissible-action list has been gated to actions consistent with this "
                "checkpoint. Choose exactly one listed action."
            )
        if fallback:
            lines.append(
                "Adapter mapping fallback is active for this turn; use the safest action that "
                "advances the active checkpoint."
            )
        return "\n".join(lines)

    def _allowed_for(self, node: SubtaskNode, actions: list[str]) -> list[str]:
        intent = node.intent.lower()
        target = self.entities.target
        destination = self.entities.destination
        transformation = self.entities.transformation

        target_takes = [
            action for action in actions
            if action.lower().startswith("take ") and _mentions(action, target)
        ]
        correct_places = [action for action in actions if self._is_correct_placement(action)]
        transform_actions = [
            action for action in actions
            if transformation
            and action.lower().startswith(transformation + " ")
            and _mentions(action, target)
        ]
        appliance = {
            "clean": "sinkbasin",
            "heat": "microwave",
            "cool": "fridge",
        }.get(transformation, "")
        appliance_actions = [
            action for action in actions
            if _mentions(action, appliance)
            and _starts_with_any(action, ("go to ", "open ", "examine "))
        ]
        destination_actions = [
            action for action in actions
            if _mentions(action, destination)
            and _starts_with_any(action, ("go to ", "open ", "examine "))
        ]
        light_actions = [action for action in actions if self._is_light_action(action)]

        if "inspect" in intent:
            return self._prefer_untried(
                [action for action in actions if _starts_with_any(action, ("look", "inventory"))]
            )
        if "locate target" in intent:
            return target_takes or self._search_actions(actions)
        if "acquire" in intent or "pick up" in intent:
            return target_takes or self._search_actions(actions)
        if any(word in intent for word in ("clean", "heat", "cool")):
            return (
                transform_actions
                or appliance_actions
                or target_takes
                or self._search_actions(actions)
            )
        if "locate destination" in intent:
            return correct_places or destination_actions or self._search_actions(actions)
        if "place" in intent:
            return correct_places or destination_actions or self._search_actions(actions)
        if "light" in intent or "examine object" in intent:
            light_navigation = [
                action for action in actions
                if _mentions(action, self.entities.light_source)
                and _starts_with_any(action, ("go to ", "examine "))
            ]
            return light_actions or light_navigation or target_takes or self._search_actions(actions)
        return actions

    def _search_actions(self, actions: list[str]) -> list[str]:
        candidates = [action for action in actions if _starts_with_any(action, _SEARCH_VERBS)]
        return self._prefer_untried(candidates)

    def _prefer_untried(self, actions: list[str]) -> list[str]:
        tried = {action.lower() for action in self.action_history}
        untried = [action for action in actions if action.lower() not in tried]
        return untried or actions

    def _advance_observable_milestones(
        self, observation: str, admissible: Sequence[str], *, won: bool
    ) -> None:
        self._verify_operation("inspect environment")
        if any(
            action.lower().startswith("take ") and _mentions(action, self.entities.target)
            for action in admissible
        ):
            self._verify_operation("locate target object")
        if self.held_target:
            self._verify_operation("acquire target object")
        if self.transformed_target and self.entities.transformation:
            self._verify_operation(f"{self.entities.transformation} held object")
        if self.held_target and (
            _mentions(observation, self.entities.destination)
            or any(_mentions(action, self.entities.destination) for action in admissible)
        ):
            self._verify_operation("locate destination receptacle")
        if any(_mentions(action, self.entities.light_source) for action in admissible):
            self._verify_operation("locate light source")
        if won:
            if any("light" in event.operation.lower() for event in self.descriptor):
                self._verify_operation("examine object under light")
            else:
                self._verify_operation("place required object")
        self._sync_completed_nodes()

    def _sync_completed_nodes(self) -> None:
        if self.schema is None:
            return
        # A node is complete only after its own observable operation and all DAG
        # predecessors are complete.  This is the actual dependency enforcement.
        predecessors: dict[str, set[str]] = {node.node_id: set() for node in self.nodes}
        for edge in self.schema.edges:
            predecessors[edge.target_node].add(edge.source_node)
        changed = True
        while changed:
            changed = False
            for node in self.nodes:
                if node.node_id in self.completed:
                    continue
                if not predecessors[node.node_id].issubset(self.completed):
                    continue
                if self._operation_verified(node.intent):
                    self.completed.add(node.node_id)
                    changed = True

    def _verify_operation(self, operation: str) -> None:
        self.verified_operations.add(self._operation_key(operation))
        self._sync_completed_nodes()

    def _reset_operation(self, operation: str) -> None:
        key = self._operation_key(operation)
        self.verified_operations.discard(key)
        if self.schema is not None:
            for node in self.nodes:
                if self._operation_key(node.intent) == key:
                    self.completed.discard(node.node_id)

    def _operation_verified(self, operation: str) -> bool:
        return self._operation_key(operation) in self.verified_operations

    @staticmethod
    def _operation_key(operation: str) -> str:
        lowered = " ".join(operation.lower().split())
        if "inspect" in lowered:
            return "inspect"
        if "locate" in lowered and "target" in lowered:
            return "locate_target"
        if "acquire" in lowered or "pick up" in lowered:
            return "acquire_target"
        if "clean" in lowered:
            return "clean_target"
        if "heat" in lowered:
            return "heat_target"
        if "cool" in lowered:
            return "cool_target"
        if "locate" in lowered and ("destination" in lowered or "receptacle" in lowered):
            return "locate_destination"
        if "place" in lowered or "move" in lowered:
            return "place_target"
        if "locate" in lowered and "light" in lowered:
            return "locate_light"
        if "light" in lowered or "examine object" in lowered:
            return "examine_under_light"
        return re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")

    def _is_correct_placement(self, action: str) -> bool:
        lowered = action.lower().strip()
        return (
            _starts_with_any(lowered, ("move ", "put "))
            and _mentions(lowered, self.entities.target)
            and _mentions(lowered, self.entities.destination)
        )

    def _is_light_action(self, action: str) -> bool:
        lowered = action.lower().strip()
        return (
            _mentions(lowered, self.entities.light_source)
            and _starts_with_any(lowered, ("use ", "toggle ", "examine "))
        )

    @staticmethod
    def _action_confirmed(action: str, observation: str) -> bool:
        verb = action.lower().split(" ", 1)[0]
        text = observation.lower()
        confirmations = {
            "take": ("you pick up", "you take"),
            "move": ("you move", "you put"),
            "put": ("you put", "you move"),
            "clean": ("you clean",),
            "heat": ("you heat",),
            "cool": ("you cool",),
            "open": ("you open",),
            "close": ("you close",),
            "go": ("you arrive",),
            "use": ("you",),
            "toggle": ("you",),
            "look": ("you",),
            "examine": ("you", "this is", "on the", "in it"),
            "inventory": ("you are carrying", "you are not carrying"),
        }
        return any(marker in text for marker in confirmations.get(verb, ()))

    def _evidence_for(self, node: SubtaskNode) -> dict[str, Any]:
        if self.schema is None:
            return {}
        evidence = list(self.schema.structural_stats.get("step_evidence", ()))
        try:
            index = self.nodes.index(node)
        except ValueError:
            return {}
        return evidence[index] if index < len(evidence) and isinstance(evidence[index], dict) else {}

    def _check_contract_boundaries(
        self,
        action: str,
        observation: str,
        accepted: bool,
    ) -> None:
        if self.schema is None:
            return
        node_by_id = {node.node_id: node for node in self.nodes}
        retry_edges = set(self.blocked_contract_edges)
        for edge in self.schema.edges:
            boundary = (edge.source_node, edge.target_node)
            if edge.contract_id is None:
                continue
            if edge.source_node not in self.completed:
                continue
            if boundary not in self.checked_contract_edges or boundary in retry_edges:
                self._check_edge_contract(
                    node_by_id[edge.source_node],
                    node_by_id[edge.target_node],
                    action,
                    observation,
                    accepted,
                )

    def _check_edge_contract(
        self,
        source: SubtaskNode,
        target: SubtaskNode,
        action: str,
        observation: str,
        accepted: bool,
    ) -> None:
        if self.schema is None:
            return
        contract = self.schema.get_contract_for_edge(source.node_id, target.node_id)
        if contract is None:
            return
        event = HandoffEvent(
            interface=contract.interface,
            source_role=source.role,
            target_role=target.role,
            artifact={
                "action": action,
                "completed_node": source.node_id,
                "target_node": target.node_id,
                "target_object": self.entities.target,
                "destination": self.entities.destination,
            },
            observable_state={
                "task_id": self.task_id,
                "intent": self.task,
                "last_action_error": "" if accepted else observation,
            },
        )
        eligible = contract.is_eligible(event)
        record: dict[str, Any] = {
            "contract_id": contract.contract_id,
            "source_node": source.node_id,
            "target_node": target.node_id,
            "eligible": eligible,
        }
        if eligible:
            verification = contract.verify(event, cost=0.0)
            record.update(
                passed=verification.passed,
                reason=verification.reason,
                recovery_route=None if verification.passed else contract.recovery_route,
            )
            if not verification.passed:
                self.blocked_contract_edges[(source.node_id, target.node_id)] = (
                    contract.recovery_route
                )
            else:
                self.blocked_contract_edges.pop((source.node_id, target.node_id), None)
        self.checked_contract_edges.add((source.node_id, target.node_id))
        self.contract_checks.append(record)
