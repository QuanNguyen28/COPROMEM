"""Outcome-backed eligibility for procedural-memory injection.

Only paired calibration outcomes are evidence. A successful source trajectory
alone says that a procedure exists; it does not say that injecting it helps.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


SCOPE_KEYS = (
    "target_type", "temporal_scope", "status", "aggregation",
    "cardinality", "sentiment", "rank",
)


def scope_signature(constraints: dict[str, str]) -> tuple[tuple[str, str], ...]:
    """Keep structural constraints, excluding instance names and identifiers."""
    return tuple((key, str(constraints[key]).strip().lower())
                 for key in SCOPE_KEYS if constraints.get(key))


@dataclass(frozen=True)
class TransferObservation:
    memory_id: str
    task_id: str
    source_task_id: str
    family: str
    constraints: dict[str, str]
    without_memory_success: bool
    with_memory_success: bool
    initial_state_digest: str

    def __post_init__(self) -> None:
        if not self.memory_id or not self.task_id or not self.source_task_id or not self.family:
            raise ValueError("memory, calibration task, and source task IDs are required")
        if self.task_id == self.source_task_id:
            raise ValueError("source task cannot calibrate its own memory")
        if not self.initial_state_digest:
            raise ValueError("paired outcomes require a matching initial-state digest")

    @property
    def benefit(self) -> int:
        return int(self.with_memory_success) - int(self.without_memory_success)


@dataclass
class EvidenceBank:
    observations: list[TransferObservation] = field(default_factory=list)
    evaluation_task_ids: set[str] = field(default_factory=set)
    frozen: bool = False

    def add(self, observation: TransferObservation) -> None:
        if self.frozen:
            raise ValueError("evaluation bank is frozen")
        if observation.task_id in self.evaluation_task_ids:
            raise ValueError("evaluation task cannot supply calibration evidence")
        if any(item.memory_id == observation.memory_id and
               item.task_id == observation.task_id for item in self.observations):
            raise ValueError("duplicate memory/task calibration pair")
        self.observations.append(observation)

    def freeze(self, evaluation_task_ids: set[str]) -> None:
        if not evaluation_task_ids:
            raise ValueError("evaluation task IDs must be declared before freezing")
        source_or_calibration_ids = {
            item.task_id for item in self.observations
        } | {item.source_task_id for item in self.observations}
        if source_or_calibration_ids & evaluation_task_ids:
            raise ValueError("evaluation tasks overlap source or calibration tasks")
        self.evaluation_task_ids = set(evaluation_task_ids)
        self.frozen = True

    def decision(self, memory_id: str, constraints: dict[str, str]) -> tuple[bool, str]:
        signature = scope_signature(constraints)
        relevant = [item for item in self.observations
                    if item.memory_id == memory_id
                    and scope_signature(item.constraints) == signature]
        gains = sum(item.benefit > 0 for item in relevant)
        harms = sum(item.benefit < 0 for item in relevant)
        if len(relevant) < 2:
            return False, f"insufficient paired evidence ({len(relevant)}/2)"
        if harms:
            return False, f"observed harmful flips ({harms})"
        if not gains:
            return False, "no observed beneficial flip"
        return True, f"paired support={len(relevant)}, gains={gains}, harms=0"

    def as_dict(self) -> dict[str, Any]:
        return {
            "observations": [asdict(item) for item in self.observations],
            "evaluation_task_ids": sorted(self.evaluation_task_ids),
            "frozen": self.frozen,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> EvidenceBank:
        bank = cls(
            observations=[TransferObservation(**item) for item in raw.get("observations", ())],
            evaluation_task_ids=set(raw.get("evaluation_task_ids", ())),
            frozen=bool(raw.get("frozen", False)),
        )
        if bank.frozen and not bank.evaluation_task_ids:
            raise ValueError("frozen evidence bank lacks evaluation task IDs")
        return bank
