from copromem.credit_assignment import localize_structural_failure
from copromem.schema import DecompositionSchema
from copromem.types import (
    CostLedger,
    DependencyEdge,
    FailureTier,
    HandoffEvent,
    JoinIntent,
    JoinTask,
    PlanArtifact,
    ReviewArtifact,
    RunMode,
    SolverArtifact,
    SubtaskNode,
    VerificationResult,
    WorkflowRun,
)


def create_base_run(
    task_intent=JoinIntent.PRESERVE_ROWS,
    expected_rows=10,
    output_rows=10,
    preserves_semantics=False,
    verifier_passed=True,
    verifier_reason="ok",
):
    task = JoinTask(
        task_id="t1",
        group_id="g1",
        left_rows=10,
        actual_cardinality="one_to_one",
        expected_rows=expected_rows,
        intent=task_intent,
    )
    plan = PlanArtifact(
        join_keys=("customer_id",),
        declared_cardinality="one_to_one",
        expected_rows=expected_rows,
        rationale="plan",
    )
    solver = SolverArtifact(
        assumed_cardinality="one_to_one",
        output_rows=output_rows,
        preserves_row_semantics=preserves_semantics,
    )
    review = ReviewArtifact(detected_mismatch=False, checklist_complete=True)
    v_res = VerificationResult("C1", verifier_passed, verifier_reason, 0.05)
    handoff = HandoffEvent(
        interface="planner->solver",
        source_role="planner",
        target_role="solver",
        artifact={"declared_cardinality": "one_to_one"},
        observable_state=task.observable_state(),
        verifier_results=(v_res,),
    )
    return WorkflowRun(
        task=task,
        mode=RunMode.CONTRACT_CHECK,
        plan=plan,
        solution=solver,
        review=review,
        handoffs=[handoff],
        recoveries=[],
        cost=CostLedger(),
    )


def test_credit_assignment_tier1_handoff_violation():
    # Handoff contract fails verification
    run = create_base_run(
        verifier_passed=False,
        verifier_reason="missing declared_cardinality",
    )
    result = localize_structural_failure(run)
    assert result.tier == FailureTier.HANDOFF_VIOLATION
    assert "planner->solver:C1" in result.responsible_entity
    assert "missing declared_cardinality" in result.reason


def test_credit_assignment_tier2_dependency_conflict():
    # Schema requires an input that is not in the plan/task
    run = create_base_run(verifier_passed=True)
    n1 = SubtaskNode("plan", "planner", "plan", output_keys=("declared_cardinality",))
    n2 = SubtaskNode("solve", "solver", "solve", input_keys=("missing_foreign_key",))
    schema = DecompositionSchema(
        schema_id="s_dep",
        task_family="Join",
        semantic_cues=("join",),
        nodes=(n1, n2),
        edges=(DependencyEdge("plan", "solve"),),
    )
    result = localize_structural_failure(run, schema=schema)
    assert result.tier == FailureTier.DEPENDENCY_CONFLICT
    assert result.responsible_entity == "solve"
    assert "missing_foreign_key" in result.reason


def test_dependency_conflict_detects_missing_edge_even_with_present_artifact():
    run = create_base_run(verifier_passed=True)
    schema = DecompositionSchema(
        schema_id="missing_edge", task_family="Join", semantic_cues=("join",),
        nodes=(
            SubtaskNode("plan", "planner", "plan", output_keys=("declared_cardinality",)),
            SubtaskNode("solve", "solver", "solve", input_keys=("declared_cardinality",)),
        ),
        edges=(),
    )
    result = localize_structural_failure(run, schema=schema)
    assert result.tier is FailureTier.DEPENDENCY_CONFLICT
    assert "no dependency path" in result.reason


def test_credit_assignment_tier3_scope_mismatch():
    # Task has intentional_expansion intent, but contract intervened and failed
    run = create_base_run(
        task_intent=JoinIntent.INTENTIONAL_EXPANSION,
        verifier_passed=False,
        verifier_reason="cardinality changed",
    )
    result = localize_structural_failure(run)
    assert result.tier == FailureTier.SCOPE_MISMATCH
    assert result.responsible_entity == "C1"
    assert "out-of-scope task" in result.reason


def test_credit_assignment_tier4_leaf_execution_error():
    # Everything in handoff passed, but solver made an execution mistake
    run = create_base_run(
        verifier_passed=True,
        output_rows=5,  # expected 10
        preserves_semantics=False,
    )
    result = localize_structural_failure(run)
    assert result.tier == FailureTier.LEAF_EXECUTION_ERROR
    assert result.responsible_entity == "solver"
    assert "Leaf execution error" in result.reason
    assert "Preserve global DAG schema" in result.suggested_patch
