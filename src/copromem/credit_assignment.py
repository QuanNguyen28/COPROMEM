"""Four-Tier Structural Credit Assignment: Pinpointing failure causes across task hierarchy."""

from __future__ import annotations

from typing import Any

from .schema import DecompositionSchema
from .types import CreditAssignmentResult, FailureTier, WorkflowRun


def localize_structural_failure(
    run: WorkflowRun,
    schema: DecompositionSchema | None = None,
    observed_context: dict[str, Any] | None = None,
) -> CreditAssignmentResult | None:
    """Classify the root cause of a task failure into one of 4 structural tiers:

    1. Handoff Violation (Tier 1): A boundary contract failed verification.
    2. Dependency Conflict (Tier 2): DAG edge missing or prerequisite inputs unfulfilled.
    3. Scope Mismatch (Tier 3): Contract mistakenly applied to out-of-scope task.
    4. Leaf Execution Error (Tier 4): Leaf solver failed despite correct inputs and structure.
    """
    ctx = observed_context or (run.task.observable_state() if hasattr(run.task, "observable_state") else {})

    # If the task succeeded, there is no structural failure
    if run.success:
        return None

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
            if any(
                recovery.contract_id == v.contract_id and recovery.successful
                for recovery in run.recoveries
            ):
                continue
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
        predecessors: dict[str, set[str]] = {node.node_id: set() for node in schema.nodes}
        for edge in schema.edges:
            predecessors[edge.target_node].add(edge.source_node)
        producers: dict[str, set[str]] = {}
        for node in schema.nodes:
            for key in node.output_keys:
                producers.setdefault(key, set()).add(node.node_id)

        def ancestors(node_id: str) -> set[str]:
            seen: set[str] = set()
            pending = list(predecessors[node_id])
            while pending:
                parent = pending.pop()
                if parent in seen:
                    continue
                seen.add(parent)
                pending.extend(predecessors[parent])
            return seen

        for node in schema.nodes:
            upstream = ancestors(node.node_id)
            for key in node.input_keys:
                expected_producers = producers.get(key, set()) - {node.node_id}
                if expected_producers and not expected_producers.intersection(upstream):
                    return CreditAssignmentResult(
                        tier=FailureTier.DEPENDENCY_CONFLICT,
                        responsible_entity=node.node_id,
                        reason=(f"Dependency conflict: '{key}' is produced by "
                                f"{sorted(expected_producers)} but no dependency path reaches "
                                f"node '{node.node_id}'."),
                        suggested_patch=f"Add an upstream dependency path for '{key}'.",
                        confidence=0.9,
                    )

        # Check node inputs against available artifacts
        available_keys = {key for key, value in ctx.items() if value is not None}
        if hasattr(run, "plan") and run.plan:
            available_keys.update(
                key for key, value in run.plan.fields().items() if value is not None
            )

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
    if any(v.passed for handoff in run.handoffs for v in handoff.verifier_results):
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

    # Failure without a valid observed boundary cannot be attributed to a leaf.
    return CreditAssignmentResult(
        tier=FailureTier.UNKNOWN,
        responsible_entity="unknown",
        reason="No passing handoff verifier establishes valid leaf inputs.",
        suggested_patch="Collect boundary verification evidence before assigning a tier.",
        confidence=0.0,
    )
