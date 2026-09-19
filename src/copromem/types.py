"""Typed, observable records used by the workflow and contract bank.

The library intentionally logs artifacts and tool-like checks, never hidden model
reasoning.  All records are plain dataclasses so a caller can serialize only the
observable workflow state it is allowed to retain.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class JoinIntent(str, Enum):
    PRESERVE_ROWS = "preserve_rows"
    INTENTIONAL_EXPANSION = "intentional_expansion"


class RunMode(str, Enum):
    NO_MEMORY = "no_memory"
    SUCCESS_ONLY_MEMORY = "success_only_memory"
    TEXT_RULE = "text_rule"
    CONTRASTIVE_PATCH = "contrastive_patch"
    SHAM_RETRY = "sham_retry"
    STATIC_VERIFIER = "static_verifier"
    CONTRACT_CHECK = "contract_check"


@dataclass(frozen=True)
class JoinTask:
    """A public data-transformation task used by the synthetic pilot.

    ``actual_cardinality`` and ``expected_rows`` are task inputs in this toy
    domain, analogous to public table statistics or a declared data contract;
    they are not a hidden evaluator answer.  The task intent is the observable
    boundary condition used by the contract veto.
    """

    task_id: str
    group_id: str
    left_rows: int
    actual_cardinality: str
    expected_rows: int
    intent: JoinIntent = JoinIntent.PRESERVE_ROWS
    join_keys: tuple[str, ...] = ("customer_id",)
    instruction: str = ""
    sites: tuple[str, ...] = ()
    start_url: str = ""
    require_login: bool = False
    eval_spec: Mapping[str, Any] = field(default_factory=dict)

    @property
    def requires_cardinality_rationale(self) -> bool:
        return self.intent is JoinIntent.PRESERVE_ROWS

    def observable_state(self) -> dict[str, Any]:
        state: dict[str, Any] = {
            "task_id": self.task_id,
            "group_id": self.group_id,
            "left_rows": self.left_rows,
            "actual_cardinality": self.actual_cardinality,
            "expected_rows": self.expected_rows,
            "intent": self.intent.value,
            "join_keys": list(self.join_keys),
        }
        if self.instruction:
            state["instruction"] = self.instruction
        if self.sites:
            state["sites"] = list(self.sites)
        if self.start_url:
            state["start_url"] = self.start_url
        if self.require_login:
            state["require_login"] = self.require_login
        return state


@dataclass(frozen=True)
class PlanArtifact:
    join_keys: tuple[str, ...]
    declared_cardinality: str | None
    expected_rows: int | None
    rationale: str | None

    def fields(self) -> Mapping[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SolverArtifact:
    assumed_cardinality: str
    output_rows: int
    preserves_row_semantics: bool


@dataclass(frozen=True)
class ReviewArtifact:
    detected_mismatch: bool
    checklist_complete: bool


@dataclass(frozen=True)
class HandoffEvent:
    interface: str
    source_role: str
    target_role: str
    artifact: Mapping[str, Any]
    observable_state: Mapping[str, Any]
    verifier_results: tuple[VerificationResult, ...] = ()


@dataclass(frozen=True)
class VerificationResult:
    contract_id: str
    passed: bool
    reason: str
    cost: float


@dataclass(frozen=True)
class RecoveryEvent:
    contract_id: str
    route: str
    owner: str
    successful: bool


@dataclass
class CostLedger:
    planner_calls: int = 0
    solver_calls: int = 0
    reviewer_calls: int = 0
    verifier_cost: float = 0.0
    injected_contract_tokens: int = 0
    trace_collection_cost: float = 0.0
    extraction_cost: float = 0.0
    replay_cost: float = 0.0
    boundary_cost: float = 0.0

    @property
    def runtime_cost(self) -> float:
        return (
            self.planner_calls
            + self.solver_calls
            + self.reviewer_calls
            + self.verifier_cost
        )

    @property
    def lifecycle_cost(self) -> float:
        return (
            self.runtime_cost
            + self.trace_collection_cost
            + self.extraction_cost
            + self.replay_cost
            + self.boundary_cost
        )


@dataclass
class WorkflowRun:
    task: JoinTask
    mode: RunMode
    plan: PlanArtifact
    solution: SolverArtifact
    review: ReviewArtifact
    handoffs: list[HandoffEvent]
    recoveries: list[RecoveryEvent]
    cost: CostLedger

    @property
    def success(self) -> bool:
        return (
            self.solution.output_rows == self.task.expected_rows
            and self.solution.preserves_row_semantics
        )

    @property
    def downstream_errors(self) -> int:
        return int(not self.success)


@dataclass(frozen=True)
class RoleProfile:
    """Observable-behaviour approximation for a role/model in a pilot."""

    name: str
    planner_omission_rate: float
    solver_ignore_plan_rate: float
    reviewer_detection_rate: float
    success_memory_compliance: float = 0.55
    text_rule_compliance: float = 0.45
    patch_compliance: float = 0.70


@dataclass(frozen=True)
class ReplayEvidence:
    checkpoint_count: int
    no_memory_success: float
    text_rule_success: float
    sham_retry_success: float
    contract_success: float
    beneficial_flips: int
    harmful_flips: int
    verifier_cost: float

    @property
    def net_gain_over_text(self) -> float:
        return self.contract_success - self.text_rule_success


@dataclass(frozen=True)
class ScopeEvidence:
    in_scope_coverage: float
    in_scope_success: float
    boundary_harmful_flips: int
    veto_accuracy: float
    transfer_success: float


@dataclass(frozen=True)
class AdmissionDecision:
    admitted: bool
    reasons: tuple[str, ...]


def as_jsonable(value: Any) -> Any:
    """Convert nested dataclasses/enums to JSON-safe data without dependencies."""

    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return as_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): as_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_jsonable(item) for item in value]
    return value


@dataclass(frozen=True)
class SubtaskNode:
    """A subtask node in a task decomposition DAG."""

    node_id: str
    role: str
    intent: str
    input_keys: tuple[str, ...] = ()
    output_keys: tuple[str, ...] = ()

    def observable_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "role": self.role,
            "intent": self.intent,
            "input_keys": list(self.input_keys),
            "output_keys": list(self.output_keys),
        }


@dataclass(frozen=True)
class DependencyEdge:
    """A directed dependency edge between subtask nodes with optional contract."""

    source_node: str
    target_node: str
    contract_id: str | None = None
    condition: str | None = None

    @property
    def as_tuple(self) -> tuple[str, str]:
        return (self.source_node, self.target_node)


class FailureTier(str, Enum):
    """The 4 tiers of structural failure attribution in COPROMEM 2.0."""

    HANDOFF_VIOLATION = "handoff_violation"      # Tier 1: contract violated at boundary
    DEPENDENCY_CONFLICT = "dependency_conflict"  # Tier 2: DAG dependency missing or inverted
    SCOPE_MISMATCH = "scope_mismatch"            # Tier 3: contract vetoed or admitted incorrectly
    LEAF_EXECUTION_ERROR = "leaf_execution_error"# Tier 4: leaf solver/tool runtime crash


@dataclass(frozen=True)
class CreditAssignmentResult:
    """Precise structural attribution of an observed task outcome."""

    tier: FailureTier
    responsible_entity: str
    reason: str
    suggested_patch: str
    confidence: float = 1.0


@dataclass(frozen=True)
class EpisodicTrace:
    """Episodic memory record for fast storage and prioritized offline replay."""

    trace_id: str
    task_id: str
    task_state: Mapping[str, Any]
    schema_id: str | None
    handoff_events: tuple[HandoffEvent, ...]
    success: bool
    credit_result: CreditAssignmentResult | None = None
    surprise: float = 0.0
    uncertainty: float = 0.0
    replay_priority: float = 0.0
