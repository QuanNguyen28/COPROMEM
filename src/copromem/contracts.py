"""Contract representation, executable verifier registry, and recovery metadata."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from .types import HandoffEvent, JoinIntent, VerificationResult

if TYPE_CHECKING:
    from .types import WorkflowRun


Verifier = Callable[[HandoffEvent, "Contract"], tuple[bool, str]]
ScopeGuard = Callable[[HandoffEvent], bool]


def join_preservation_scope(event: HandoffEvent) -> bool:
    return event.observable_state.get("intent") == JoinIntent.PRESERVE_ROWS.value


def alfworld_cleaning_scope(event: HandoffEvent) -> bool:
    return event.observable_state.get("intent") == JoinIntent.PRESERVE_ROWS.value


def appworld_order_receipt_scope(event: HandoffEvent) -> bool:
    return event.observable_state.get("intent") == JoinIntent.PRESERVE_ROWS.value


def webarena_checkout_scope(event: HandoffEvent) -> bool:
    return event.observable_state.get("intent") == JoinIntent.PRESERVE_ROWS.value


def browser_action_scope(event: HandoffEvent) -> bool:
    return event.interface == "agent_to_browser"


def browser_action_accepted(
    event: HandoffEvent, contract: Contract
) -> tuple[bool, str]:
    if not str(event.artifact.get("action", "")).strip():
        return False, "browser action is empty"
    error = str(event.observable_state.get("last_action_error", "")).strip()
    if error:
        return False, error
    return True, "browser accepted the action"


def plan_cardinality_present(
    event: HandoffEvent, contract: Contract
) -> tuple[bool, str]:
    required = contract.required_fields
    missing = [name for name in required if event.artifact.get(name) in (None, "")]
    if missing:
        return False, "missing required plan fields: " + ", ".join(missing)
    return True, "all required plan fields present"


VERIFIERS: dict[str, Verifier] = {
    "plan_cardinality_present": plan_cardinality_present,
    "browser_action_accepted": browser_action_accepted,
}
SCOPE_GUARDS: dict[str, ScopeGuard] = {
    "join_preservation_scope": join_preservation_scope,
    "alfworld_cleaning_scope": alfworld_cleaning_scope,
    "appworld_order_receipt_scope": appworld_order_receipt_scope,
    "webarena_checkout_scope": webarena_checkout_scope,
    "browser_action_scope": browser_action_scope,
}


@dataclass(frozen=True)
class Contract:
    """A compact, serializable procedural handoff contract.

    The verifier and scope guard are names resolved through registries rather than
    arbitrary code persisted in memory.  This makes contracts inspectable and
    avoids executing untrusted extraction output.
    """

    contract_id: str
    interface: str
    precondition: str
    postcondition: str
    verifier_name: str
    owner: str
    recovery_route: str
    scope_name: str
    counterexamples: tuple[str, ...]
    required_fields: tuple[str, ...] = ("declared_cardinality", "expected_rows")
    evidence: dict[str, object] = field(default_factory=dict)
    status: str = "candidate"

    @property
    def estimated_read_tokens(self) -> int:
        # Stable budget proxy; a production system should use its tokenizer.
        return max(1, len(self.render_for_owner().split()))

    @property
    def storage_tokens(self) -> int:
        return self.estimated_read_tokens + sum(
            len(item.split()) for item in self.counterexamples
        )

    def is_eligible(self, event: HandoffEvent) -> bool:
        task_id = str(event.observable_state.get("task_id", ""))
        intent = str(event.observable_state.get("intent", ""))
        if (task_id and task_id in self.counterexamples) or (
            intent and intent in self.counterexamples
        ):
            return False
        guard = SCOPE_GUARDS.get(self.scope_name)
        if guard is not None:
            return guard(event)
        return event.observable_state.get("intent") == JoinIntent.PRESERVE_ROWS.value

    def verify(self, event: HandoffEvent, cost: float = 0.05) -> VerificationResult:
        passed, reason = VERIFIERS[self.verifier_name](event, self)
        return VerificationResult(self.contract_id, passed, reason, cost)

    def render_for_owner(self) -> str:
        return (
            f"At {self.interface}: before {self.owner} proceeds, {self.precondition}. "
            f"Invariant: {self.postcondition}. If violated, {self.recovery_route}."
        )

    def without_required_field(self, field_name: str) -> Contract:
        return replace(
            self,
            required_fields=tuple(
                item for item in self.required_fields if item != field_name
            ),
        )

    def with_evidence(self, **evidence: object) -> Contract:
        merged = dict(self.evidence)
        merged.update(evidence)
        return replace(self, evidence=merged)

    def admitted(self) -> Contract:
        return replace(self, status="admitted")


def contract_from_failure(
    failed_run: WorkflowRun, successful_run: WorkflowRun
) -> Contract | None:
    """Extract a bounded hypothesis from a success/failure divergence.

    This is a deliberately deterministic extractor for the synthetic domain. In
    a real system, an LLM/tool extractor should emit this typed form, then this
    layer validates all vocabulary and executable references.
    """

    if failed_run.success or not successful_run.success:
        return None
    if failed_run.plan.declared_cardinality is not None:
        return None
    if successful_run.plan.declared_cardinality is None:
        return None
    return Contract(
        contract_id="join-cardinality-rationale-v1",
        interface="planner_to_solver",
        precondition="the plan names join keys, cardinality, and output-row rationale",
        postcondition="the solver receives a plan with declared cardinality before executing a row-preserving join",
        verifier_name="plan_cardinality_present",
        owner="planner",
        recovery_route="return_to_planner_for_cardinality_completion",
        scope_name="join_preservation_scope",
        counterexamples=("intentional many-to-many expansion",),
    )


def validate_contract(contract: Contract) -> None:
    if contract.verifier_name not in VERIFIERS:
        raise ValueError(f"unknown verifier: {contract.verifier_name}")
    if contract.scope_name not in SCOPE_GUARDS:
        raise ValueError(f"unknown scope guard: {contract.scope_name}")
    if not contract.required_fields:
        raise ValueError("contract must retain at least one executable required field")
    if contract.owner not in {"planner", "solver", "reviewer"}:
        raise ValueError(f"unknown owner: {contract.owner}")


def contracts_for_interface(
    contracts: Iterable[Contract], interface: str
) -> list[Contract]:
    return [contract for contract in contracts if contract.interface == interface]
