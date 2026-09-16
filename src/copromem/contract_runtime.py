"""One execution and recovery pathway for induced and manually authored predicates."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .checkpoints import PlannerCheckpoint, RecordedCallError, canonical, matched_seed
from .induction import InducedContract, Predicate, ReplayOutcome
from .paired_gsm8k import GSM8KAdapter
from .real_gsm8k_experiment import PLANNER_SYSTEM, Example


def static_schema_contract() -> InducedContract:
    """Explicit human-authored control, never presented as an induced contract."""
    clauses = tuple(
        sorted(
            [
                *(
                    Predicate((field,), "nonempty")
                    for field in ("operations", "answer_unit", "check")
                ),
                Predicate(("operations",), "type", "list"),
                Predicate(("operations",), "list_of", "string"),
            ]
        )
    )
    return InducedContract("planner_to_solver", clauses, (), (), ())


def execute_policy(
    adapter: GSM8KAdapter,
    checkpoint: PlannerCheckpoint,
    example: Example,
    contract: InducedContract | None,
    *,
    mode: str = "contract",
    public_context: dict[str, Any] | None = None,
    memory: str = "",
) -> dict[str, Any]:
    """Evaluate a candidate at dev/audit checkpoints; final requires admission.

    Origin and evidence never enter the recovery prompt. Thus a manually written
    and an induced copy of the same predicate set use the same physical request.
    """
    if mode not in {"contract", "sham", "none", "text"}:
        raise ValueError("unknown execution mode")
    if (
        example.example_id != checkpoint.task_id
        or example.question != checkpoint.question
    ):
        raise ValueError("checkpoint/task mismatch")
    if (
        checkpoint.split == "final"
        and contract is not None
        and contract.status != "admitted"
    ):
        raise ValueError("unadmitted candidate cannot run on final checkpoints")
    original_id = checkpoint.checkpoint_id
    plan = checkpoint.artifact()
    context = public_context or {}
    eligible = contract is not None and contract.eligible("planner_to_solver", context)
    violations = contract.violations(plan) if eligible else []
    calls = []
    triggered = bool(violations) and mode in {"contract", "sham"}
    failure = None
    solver = None
    try:
        if triggered:
            prompt = (
                f"Problem:\n{checkpoint.question}\nCurrent artifact:\n{canonical(plan)}"
            )
            if mode == "sham":
                prompt += "\nReview and regenerate the artifact. Return ONLY JSON and no final answer."
            else:
                executable = {
                    "interface": contract.interface,
                    "predicates": [asdict(x) for x in contract.predicates],
                    "owner": contract.owner,
                    "recovery_route": contract.recovery_route,
                }
                prompt += (
                    f"\nVerifier violations: {canonical(violations)}\nExecutable contract: {canonical(executable)}"
                    "\nRepair the artifact. Return ONLY JSON and no final answer."
                )
            repaired = adapter.service.call(
                PLANNER_SYSTEM,
                prompt,
                adapter.config.planner_tokens,
                matched_seed(
                    adapter.config.seed,
                    checkpoint.task_id,
                    "recovery",
                    checkpoint.replicate,
                ),
            )
            calls.append(repaired)
            from .real_gsm8k_experiment import parse_plan

            plan = parse_plan(repaired.text)
        if mode == "text" and contract is not None:
            memory = "Prior corrective constraints: " + canonical(
                [asdict(x) for x in contract.predicates]
            )
        solver = adapter.solve(checkpoint, plan, memory)
        calls.append(solver)
    except RecordedCallError as exc:
        failure = str(exc)
    if checkpoint.checkpoint_id != original_id:
        raise RuntimeError("checkpoint mutated during execution")
    return {
        "task_id": checkpoint.task_id,
        "checkpoint_id": original_id,
        "replicate": checkpoint.replicate,
        "contract_id": contract.contract_id if contract else None,
        "mode": mode,
        "eligible": eligible,
        "violation": bool(violations),
        "violations": violations,
        "triggered": triggered,
        "success": adapter.score(example, solver.text) if solver else False,
        "recovery_success": triggered and eligible and not contract.violations(plan),
        "artifact_changed": canonical(plan) != checkpoint.artifact_json,
        "provider_failure": failure,
        "call_ids": [x.request_id for x in calls],
        "logical_calls": len(calls),
        "logical_usd": sum(x.usage["usd"] for x in calls),
        "logical_tokens": sum(x.usage["total_tokens"] for x in calls),
    }


def replay_outcome(
    contract: InducedContract,
    baseline: dict[str, Any],
    treatment: dict[str, Any],
    partition: str,
) -> ReplayOutcome:
    if (
        baseline["checkpoint_id"] != treatment["checkpoint_id"]
        or baseline["task_id"] != treatment["task_id"]
    ):
        raise ValueError("replay must continue the same task checkpoint")
    return ReplayOutcome(
        baseline["task_id"],
        baseline["checkpoint_id"],
        contract.contract_id,
        partition,
        baseline["success"],
        treatment["success"],
        treatment["triggered"],
        treatment["violation"],
        baseline["provider_failure"] is not None
        or treatment["provider_failure"] is not None,
        treatment["recovery_success"],
        treatment["logical_usd"] - baseline["logical_usd"],
    )
