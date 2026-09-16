"""Instrumented planner -> solver -> reviewer workflow with checkpoint execution."""

from __future__ import annotations

import hashlib
import random
from collections.abc import Iterable
from dataclasses import asdict

from .bank import ContractBank
from .contracts import Contract
from .types import (
    CostLedger,
    HandoffEvent,
    JoinTask,
    PlanArtifact,
    RecoveryEvent,
    ReviewArtifact,
    RoleProfile,
    RunMode,
    SolverArtifact,
    VerificationResult,
    WorkflowRun,
)


def _random_unit(seed: int, *parts: object) -> float:
    """A per-decision deterministic random draw, invariant to recovery branches."""

    payload = "|".join(str(part) for part in (seed, *parts)).encode("utf-8")
    return random.Random(
        int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    ).random()


class WorkflowEngine:
    """Runs a fixed, observable three-role workflow.

    ``RunMode`` is intentionally explicit: the matched controls differ only in
    how the same checkpoint is treated. The engine does not let a contract read
    ``expected_rows`` to repair the final answer; it only asks the planner to
    complete an already-public plan artifact from the public task schema.
    """

    def __init__(
        self,
        bank: ContractBank | None = None,
        verifier_cost: float = 0.05,
        success_memory_fields: tuple[str, ...] = (),
    ):
        self.bank = bank or ContractBank()
        self.verifier_cost = verifier_cost
        self.success_memory_fields = success_memory_fields

    def run(
        self, task: JoinTask, profile: RoleProfile, mode: RunMode, seed: int
    ) -> WorkflowRun:
        cost = CostLedger()
        handoffs: list[HandoffEvent] = []
        recoveries: list[RecoveryEvent] = []

        plan = self._plan(task, profile, mode, seed, attempt=0, force_complete=False)
        cost.planner_calls += 1
        event = HandoffEvent(
            interface="planner_to_solver",
            source_role="planner",
            target_role="solver",
            artifact=asdict(plan),
            observable_state=task.observable_state(),
        )

        verifications: list[VerificationResult] = []
        eligible_contracts = self._contracts_for_mode(mode, event)
        for contract in eligible_contracts:
            result = contract.verify(event, self.verifier_cost)
            verifications.append(result)
            cost.verifier_cost += result.cost
            cost.injected_contract_tokens += contract.estimated_read_tokens

        violation = bool(verifications) and not all(
            result.passed for result in verifications
        )
        if violation:
            if mode in {RunMode.CONTRACT_CHECK, RunMode.STATIC_VERIFIER}:
                # The contract declares that planner owns the incomplete plan.
                plan = self._plan(
                    task, profile, mode, seed, attempt=1, force_complete=True
                )
                cost.planner_calls += 1
                recoveries.append(
                    RecoveryEvent(
                        contract_id=eligible_contracts[0].contract_id,
                        route="return_to_planner_for_cardinality_completion",
                        owner="planner",
                        successful=plan.declared_cardinality is not None,
                    )
                )
            elif mode is RunMode.SHAM_RETRY:
                # Match the extra planner call but do not provide contract-guided
                # recovery. The new draw may happen to improve the artifact.
                plan = self._plan(
                    task, profile, mode, seed, attempt=1, force_complete=False
                )
                cost.planner_calls += 1
                recoveries.append(
                    RecoveryEvent(
                        contract_id="sham-retry",
                        route="retry_without_contract",
                        owner="planner",
                        successful=plan.declared_cardinality is not None,
                    )
                )

        handoffs.append(
            HandoffEvent(
                interface=event.interface,
                source_role=event.source_role,
                target_role=event.target_role,
                artifact=asdict(plan),
                observable_state=event.observable_state,
                verifier_results=tuple(verifications),
            )
        )
        solution = self._solve(task, plan, profile, seed)
        cost.solver_calls += 1
        solver_event = HandoffEvent(
            interface="solver_to_reviewer",
            source_role="solver",
            target_role="reviewer",
            artifact=asdict(solution),
            observable_state=task.observable_state(),
        )
        handoffs.append(solver_event)
        review = self._review(task, solution, profile, seed)
        cost.reviewer_calls += 1
        return WorkflowRun(
            task, mode, plan, solution, review, handoffs, recoveries, cost
        )

    def _contracts_for_mode(self, mode: RunMode, event: HandoffEvent) -> list[Contract]:
        if mode is RunMode.CONTRACT_CHECK:
            return self.bank.retrieve(event)
        if mode is RunMode.STATIC_VERIFIER:
            # Fixed control: the same check is available, but it was not learned
            # from traces and carries no admission/transfer evidence.
            static = Contract(
                contract_id="static-join-plan-check",
                interface="planner_to_solver",
                precondition="plan contains cardinality",
                postcondition="join plan is complete",
                verifier_name="plan_cardinality_present",
                owner="planner",
                recovery_route="return_to_planner_for_cardinality_completion",
                scope_name="join_preservation_scope",
                counterexamples=("intentional many-to-many expansion",),
                required_fields=("declared_cardinality",),
                status="admitted",
            )
            return [static] if static.is_eligible(event) else []
        if mode is RunMode.SHAM_RETRY:
            # Sham uses the same public check to decide whether to spend an extra
            # call, while concealing the contract's required field/recovery rule.
            sham = Contract(
                contract_id="sham-observation",
                interface="planner_to_solver",
                precondition="",
                postcondition="",
                verifier_name="plan_cardinality_present",
                owner="planner",
                recovery_route="retry_without_contract",
                scope_name="join_preservation_scope",
                counterexamples=(),
                required_fields=("declared_cardinality",),
                status="admitted",
            )
            return [sham] if sham.is_eligible(event) else []
        return []

    def _plan(
        self,
        task: JoinTask,
        profile: RoleProfile,
        mode: RunMode,
        seed: int,
        attempt: int,
        force_complete: bool,
    ) -> PlanArtifact:
        omission_rate = profile.planner_omission_rate
        if (
            mode is RunMode.SUCCESS_ONLY_MEMORY
            and "declared_cardinality" in self.success_memory_fields
        ):
            omission_rate *= 1.0 - profile.success_memory_compliance
        elif mode is RunMode.TEXT_RULE:
            omission_rate *= 1.0 - profile.text_rule_compliance
        elif mode is RunMode.CONTRASTIVE_PATCH:
            omission_rate *= 1.0 - profile.patch_compliance
        omit = (
            not force_complete
            and _random_unit(seed, task.task_id, "planner", attempt) < omission_rate
        )
        if omit:
            return PlanArtifact(task.join_keys, None, None, "join customer records")
        return PlanArtifact(
            task.join_keys,
            task.actual_cardinality,
            task.expected_rows,
            f"{task.actual_cardinality} join; output should have {task.expected_rows} rows",
        )

    def _solve(
        self, task: JoinTask, plan: PlanArtifact, profile: RoleProfile, seed: int
    ) -> SolverArtifact:
        ignores_plan = (
            _random_unit(seed, task.task_id, "solver") < profile.solver_ignore_plan_rate
        )
        if plan.declared_cardinality is None or ignores_plan:
            assumed = "one_to_one"
        else:
            assumed = plan.declared_cardinality
        correct = assumed == task.actual_cardinality
        # In a genuine one-to-one task, the fallback happens to be correct. All
        # non-one-to-one tasks expose the missing-cardinality coordination error.
        output_rows = task.expected_rows if correct else task.left_rows
        return SolverArtifact(assumed, output_rows, correct)

    def _review(
        self, task: JoinTask, solution: SolverArtifact, profile: RoleProfile, seed: int
    ) -> ReviewArtifact:
        mismatch = solution.output_rows != task.expected_rows
        detects = (
            mismatch
            and _random_unit(seed, task.task_id, "reviewer")
            < profile.reviewer_detection_rate
        )
        return ReviewArtifact(
            detected_mismatch=detects,
            checklist_complete=solution.preserves_row_semantics,
        )


def run_many(
    engine: WorkflowEngine,
    tasks: Iterable[JoinTask],
    profile: RoleProfile,
    mode: RunMode,
    seed: int,
) -> list[WorkflowRun]:
    return [engine.run(task, profile, mode, seed) for task in tasks]
