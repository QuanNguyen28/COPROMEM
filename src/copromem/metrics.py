"""Metrics and group-cluster bootstrap used by the synthetic report."""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from .types import WorkflowRun


@dataclass(frozen=True)
class ArmMetrics:
    task_count: int
    success_rate: float
    macro_group_success: float
    downstream_error_rate: float
    runtime_cost_per_task: float
    verifier_cost_per_task: float
    recovery_success_rate: float


@dataclass(frozen=True)
class PairedMetrics:
    beneficial_flips: int
    harmful_flips: int
    net_gain: int


def summarize(runs: Sequence[WorkflowRun]) -> ArmMetrics:
    group_successes: dict[str, list[bool]] = defaultdict(list)
    for run in runs:
        group_successes[run.task.group_id].append(run.success)
    count = max(1, len(runs))
    recovery_events = [event for run in runs for event in run.recoveries]
    return ArmMetrics(
        task_count=len(runs),
        success_rate=sum(run.success for run in runs) / count,
        macro_group_success=sum(
            sum(values) / len(values) for values in group_successes.values()
        )
        / max(1, len(group_successes)),
        downstream_error_rate=sum(run.downstream_errors for run in runs) / count,
        runtime_cost_per_task=sum(run.cost.runtime_cost for run in runs) / count,
        verifier_cost_per_task=sum(run.cost.verifier_cost for run in runs) / count,
        recovery_success_rate=(
            sum(event.successful for event in recovery_events) / len(recovery_events)
        )
        if recovery_events
        else 0.0,
    )


def paired(
    reference: Sequence[WorkflowRun], treatment: Sequence[WorkflowRun]
) -> PairedMetrics:
    if [run.task.task_id for run in reference] != [
        run.task.task_id for run in treatment
    ]:
        raise ValueError("paired comparison requires task-aligned runs")
    beneficial = sum(
        not old.success and new.success for old, new in zip(reference, treatment)
    )
    harmful = sum(
        old.success and not new.success for old, new in zip(reference, treatment)
    )
    return PairedMetrics(beneficial, harmful, beneficial - harmful)


def clustered_bootstrap_success_delta(
    reference: Sequence[WorkflowRun],
    treatment: Sequence[WorkflowRun],
    seed: int,
    samples: int = 1_000,
) -> tuple[float, float]:
    """95% percentile interval resampling source/template groups, not variants."""

    by_group: dict[str, list[tuple[bool, bool]]] = defaultdict(list)
    for old, new in zip(reference, treatment):
        if old.task.group_id != new.task.group_id:
            raise ValueError("paired runs have mismatched source groups")
        by_group[old.task.group_id].append((old.success, new.success))
    groups = list(by_group.values())
    if not groups:
        return (0.0, 0.0)
    rng = random.Random(seed)
    deltas: list[float] = []
    for _ in range(samples):
        drawn = [groups[rng.randrange(len(groups))] for _ in groups]
        old_values = [old for group in drawn for old, _ in group]
        new_values = [new for group in drawn for _, new in group]
        deltas.append(
            sum(new_values) / len(new_values) - sum(old_values) / len(old_values)
        )
    deltas.sort()
    return (deltas[int(0.025 * (samples - 1))], deltas[int(0.975 * (samples - 1))])
