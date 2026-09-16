"""Counterfactual checkpoint replay and empirical clause minimization."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from .bank import ContractBank
from .contracts import Contract
from .types import JoinTask, ReplayEvidence, RoleProfile, RunMode
from .workflow import WorkflowEngine


def compare_at_checkpoint(
    contract: Contract,
    tasks: Iterable[JoinTask],
    profile: RoleProfile,
    seed: int,
) -> ReplayEvidence:
    """Run matched arms from the planner-to-solver checkpoint.

    The synthetic engine uses per-role deterministic draws, so each arm has the
    same underlying role behaviour. Only its checkpoint intervention differs.
    """

    bank = ContractBank()
    bank.contracts.append(contract.admitted())
    engine = WorkflowEngine(bank)
    arms: dict[RunMode, list[bool]] = defaultdict(list)
    beneficial = harmful = 0
    total_verifier_cost = 0.0
    task_list = list(tasks)
    for task in task_list:
        results = {
            mode: engine.run(task, profile, mode, seed)
            for mode in (
                RunMode.NO_MEMORY,
                RunMode.TEXT_RULE,
                RunMode.SHAM_RETRY,
                RunMode.CONTRACT_CHECK,
            )
        }
        for mode, run in results.items():
            arms[mode].append(run.success)
        total_verifier_cost += results[RunMode.CONTRACT_CHECK].cost.verifier_cost
        if (
            not results[RunMode.NO_MEMORY].success
            and results[RunMode.CONTRACT_CHECK].success
        ):
            beneficial += 1
        if (
            results[RunMode.NO_MEMORY].success
            and not results[RunMode.CONTRACT_CHECK].success
        ):
            harmful += 1
    denominator = max(1, len(task_list))
    return ReplayEvidence(
        checkpoint_count=len(task_list),
        no_memory_success=sum(arms[RunMode.NO_MEMORY]) / denominator,
        text_rule_success=sum(arms[RunMode.TEXT_RULE]) / denominator,
        sham_retry_success=sum(arms[RunMode.SHAM_RETRY]) / denominator,
        contract_success=sum(arms[RunMode.CONTRACT_CHECK]) / denominator,
        beneficial_flips=beneficial,
        harmful_flips=harmful,
        verifier_cost=total_verifier_cost,
    )


def minimize_by_clause_deletion(
    contract: Contract,
    validation_tasks: Iterable[JoinTask],
    profile: RoleProfile,
    seed: int,
    min_gain: float = 0.05,
    harm_cap: int = 0,
) -> tuple[Contract, ReplayEvidence]:
    """Greedily delete verifier fields while preserving observed replay gates.

    The result is empirical 1-minimal only for this contract language and this
    deletion set; callers should retain that qualification in reports.
    """

    current = contract
    current_evidence = compare_at_checkpoint(current, validation_tasks, profile, seed)
    # Try optional explanatory fields first. This priority keeps the semantic
    # join-cardinality invariant when either field alone passes this toy replay.
    for field_name in reversed(tuple(current.required_fields)):
        candidate = current.without_required_field(field_name)
        if not candidate.required_fields:
            continue
        evidence = compare_at_checkpoint(candidate, validation_tasks, profile, seed)
        if (
            evidence.net_gain_over_text >= min_gain
            and evidence.harmful_flips <= harm_cap
        ):
            current, current_evidence = candidate, evidence
    return current, current_evidence
