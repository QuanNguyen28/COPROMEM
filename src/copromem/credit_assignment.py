"""Four-Tier Structural Credit Assignment: Pinpointing failure causes across task hierarchy."""

from __future__ import annotations

from typing import Any

from .schema import DecompositionSchema
from .types import CreditAssignmentResult, FailureTier, WorkflowRun


def localize_structural_failure(
    run: WorkflowRun,
    schema: DecompositionSchema | None = None,
    observed_context: dict[str, Any] | None = None,
) -> CreditAssignmentResult:
    """Classify the root cause of a task failure into one of 4 structural tiers:

    1. Handoff Violation (Tier 1): A boundary contract failed verification.
    2. Dependency Conflict (Tier 2): DAG edge missing or prerequisite inputs unfulfilled.
    3. Scope Mismatch (Tier 3): Contract mistakenly applied to out-of-scope task.
    4. Leaf Execution Error (Tier 4): Leaf solver failed despite correct inputs and structure.
    """
    ctx = observed_context or (run.task.observable_state() if hasattr(run.task, "observable_state") else {})

    # If the task succeeded, there is no structural failure
    if run.success:
        return CreditAssignmentResult(
            tier=FailureTier.LEAF_EXECUTION_ERROR,
            responsible_entity="none",
            reason="Task succeeded. No structural failure detected.",
            suggested_patch="None",
            confidence=1.0,
        )

    # Tier 3 Check: Scope Mismatch
    # Did a contract intervene on an out-of-scope or intentional alternative task?
    task_intent = ctx.get("intent")
    for handoff in run.handoffs:
        for v in handoff.verifier_results:
            # If the task was intentional expansion and contract failed/fired unexpectedly
            if task_intent == "intentional_expansion" and not v.passed:
                return CreditAssignmentResult(
                    tier=FailureTier.SCOPE_MISMATCH,
                    responsible_entity=v.contract_id,
                    reason=(
                        f"Scope mismatch: Contract '{v.contract_id}' intervened on an "
                        f"out-of-scope task with intent '{task_intent}'."
                    ),
                    suggested_patch=(
                        f"Add task_id/intent '{task_intent}' to contract counterexamples "
                        "or tighten scope guard."
                    ),
                    confidence=0.95,
                )

    # Tier 1 Check: Handoff Violation
    # Did any contract fail verification during handoff?
    for handoff in run.handoffs:
        for v in handoff.verifier_results:
            if not v.passed:
                return CreditAssignmentResult(
                    tier=FailureTier.HANDOFF_VIOLATION,
                    responsible_entity=f"{handoff.interface}:{v.contract_id}",
                    reason=f"Handoff contract '{v.contract_id}' failed: {v.reason}",
                    suggested_patch=f"Enforce contract recovery route on owner '{handoff.source_role}'.",
                    confidence=0.90,
                )

    # Tier 2 Check: Dependency Conflict
    # Were prerequisite inputs required by downstream nodes missing in upstream outputs?
    if schema:
        # Check node inputs against available artifacts
        available_keys = set(ctx.keys())
        if hasattr(run, "plan") and run.plan:
            available_keys.update(run.plan.fields().keys() if hasattr(run.plan, "fields") else {})

        for node in schema.nodes:
            missing_inputs = [k for k in node.input_keys if k not in available_keys]
            if missing_inputs:
                return CreditAssignmentResult(
                    tier=FailureTier.DEPENDENCY_CONFLICT,
                    responsible_entity=node.node_id,
                    reason=(
                        f"Dependency conflict: Node '{node.node_id}' requires inputs "
                        f"{missing_inputs} which were not produced by prior dependencies."
                    ),
                    suggested_patch=(
                        f"Add missing prerequisite dependency edge leading into node '{node.node_id}'."
                    ),
                    confidence=0.85,
                )

    # Tier 4 Check: Leaf Execution Error
    # High-level structure and handoff contracts passed, but solver made an execution mistake
    if not run.success:
        return CreditAssignmentResult(
            tier=FailureTier.LEAF_EXECUTION_ERROR,
            responsible_entity="solver",
            reason=(
                f"Leaf execution error: Solver output failed task criteria "
                f"(output_rows={run.solution.output_rows}, expected={run.task.expected_rows}) "
                f"despite valid handoff and dependency structure."
            ),
            suggested_patch=(
                "Update leaf executor prompt or tool execution logic. "
                "Preserve global DAG schema and handoff contracts unchanged."
            ),
            confidence=0.80,
        )

    # Task succeeded
    return CreditAssignmentResult(
        tier=FailureTier.LEAF_EXECUTION_ERROR,
        responsible_entity="none",
        reason="Task succeeded. No structural failure detected.",
        suggested_patch="None",
        confidence=1.0,
    )
