"""Failure localization, bounded contract proposal, scope and transfer evaluation."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from .bank import ContractBank
from .contracts import Contract, contract_from_failure
from .types import (
    JoinTask,
    RoleProfile,
    RunMode,
    ScopeEvidence,
    WorkflowRun,
)
from .workflow import WorkflowEngine


def localize_handoff_failures(runs: Iterable[WorkflowRun]) -> list[WorkflowRun]:
    """Keep failures whose first observable divergence is an incomplete plan."""

    return [
        run for run in runs if not run.success and run.plan.declared_cardinality is None
    ]


def propose_contracts(
    runs: Iterable[WorkflowRun], max_per_failure: int = 3
) -> list[Contract]:
    """Propose typed hypotheses from failure/success pairs in a source group."""

    by_group: dict[str, list[WorkflowRun]] = defaultdict(list)
    for run in runs:
        by_group[run.task.group_id].append(run)
    candidates: dict[str, Contract] = {}
    for group_runs in by_group.values():
        failures = localize_handoff_failures(group_runs)
        successes = [run for run in group_runs if run.success]
        for failed in failures:
            for successful in successes[:max_per_failure]:
                candidate = contract_from_failure(failed, successful)
                if candidate is not None:
                    candidates[candidate.contract_id] = candidate
    return list(candidates.values())


def evaluate_scope_and_counterexamples(
    contract: Contract,
    in_scope_tasks: Iterable[JoinTask],
    boundary_tasks: Iterable[JoinTask],
    transfer_profile: RoleProfile,
    seed: int,
) -> ScopeEvidence:
    bank = ContractBank()
    bank.contracts.append(contract.admitted())
    engine = WorkflowEngine(bank)
    in_scope = list(in_scope_tasks)
    boundary = list(boundary_tasks)
    contract_runs = [
        engine.run(task, transfer_profile, RunMode.CONTRACT_CHECK, seed)
        for task in in_scope
    ]
    no_memory = [
        engine.run(task, transfer_profile, RunMode.NO_MEMORY, seed) for task in boundary
    ]
    boundary_contract = [
        engine.run(task, transfer_profile, RunMode.CONTRACT_CHECK, seed)
        for task in boundary
    ]
    eligible = [run for run in contract_runs if run.handoffs[0].verifier_results]
    harmful = sum(
        old.success and not new.success
        for old, new in zip(no_memory, boundary_contract)
    )
    vetoes = [not run.handoffs[0].verifier_results for run in boundary_contract]
    return ScopeEvidence(
        in_scope_coverage=len(eligible) / max(1, len(in_scope)),
        in_scope_success=sum(run.success for run in contract_runs)
        / max(1, len(in_scope)),
        boundary_harmful_flips=harmful,
        veto_accuracy=sum(vetoes) / max(1, len(boundary)),
        transfer_success=sum(run.success for run in contract_runs)
        / max(1, len(in_scope)),
    )
