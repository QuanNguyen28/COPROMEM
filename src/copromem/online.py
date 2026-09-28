"""Deterministic task-boundary selection for continuous CoProMem learning."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from .benchmarks.appworld.adapter import CoProMemAppWorldAdapter, RawAcquisitionTrajectory


@dataclass(frozen=True)
class ScoredCandidate:
    trajectory: RawAcquisitionTrajectory
    score: float
    cost_usd: float
    actions: int
    selected_schema_id: str | None = None
    no_memory_score: float | None = None

    def __post_init__(self) -> None:
        if (not math.isfinite(self.score) or not 0 <= self.score <= 1
                or not math.isfinite(self.cost_usd) or self.cost_usd < 0
                or self.actions < 0):
            raise ValueError("candidate requires normalized score and nonnegative cost/actions")


def apply_task_batch(adapter: CoProMemAppWorldAdapter,
                     candidates: Sequence[ScoredCandidate]) -> str | None:
    """Record every trial, then promote one grounded successful candidate."""
    if not candidates:
        raise ValueError("task batch is empty")
    task_ids = {item.trajectory.identity.task_id for item in candidates}
    identities = [item.trajectory.identity.value for item in candidates]
    if len(task_ids) != 1 or len(set(identities)) != len(identities):
        raise ValueError("task batch requires one task and unique trial identities")
    for item in candidates:
        adapter.ingest(item.trajectory)
        if item.no_memory_score is not None:
            adapter.module.record_feedback(
                item.selected_schema_id, item.trajectory.identity.task_id,
                item.trajectory.identity.seed, item.score, item.no_memory_score)
    eligible = [item for item in candidates if item.trajectory.success
                and item.trajectory.events
                and any(event.check and event.output_slots for event in item.trajectory.events)
                and adapter.module.learning.signature(item.trajectory.events) is not None]
    if not eligible:
        return None
    winner = min(eligible, key=lambda item: (
        -item.score, item.cost_usd, item.actions,
        item.trajectory.identity.trajectory_index))
    episode_id = winner.trajectory.identity.value
    return episode_id if adapter.module.promote_episode(episode_id) else None
