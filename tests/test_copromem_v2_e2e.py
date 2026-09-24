from copromem.bank import StructuralSchemaBank
from copromem.contracts import Contract
from copromem.schema import DecompositionSchema
from copromem.types import (
    DependencyEdge,
    FailureTier,
    JoinIntent,
    JoinTask,
    RoleProfile,
    SubtaskNode,
)
from copromem.workflow import WorkflowEngine


def test_copromem_v2_complete_loop():
    # 1. Setup Handoff Contract
    contract = Contract(
        contract_id="C_join_cardinality",
        interface="planner_to_solver",
        precondition="declared_cardinality is not empty",
        postcondition="cardinality bounds verified",
        verifier_name="plan_cardinality_present",
        owner="planner",
        recovery_route="return_to_planner_for_cardinality_completion",
        scope_name="join_preservation_scope",
        counterexamples=("intentional_expansion", "task_expansion_99"),
        required_fields=("declared_cardinality",),
    )

    # 2. Setup DecompositionSchema as First-Class Memory
    n_plan = SubtaskNode("plan", "planner", "generate_plan", output_keys=("declared_cardinality",))
    n_exec = SubtaskNode("exec", "solver", "execute_join", input_keys=("declared_cardinality",))
    n_rev = SubtaskNode("review", "reviewer", "review_output")

    schema = DecompositionSchema(
        schema_id="schema_join_standard",
        task_family="DataJoin",
        semantic_cues=("join", "customer", "tables", "records"),
        nodes=(n_plan, n_exec, n_rev),
        edges=(
            DependencyEdge("plan", "exec", contract_id="C_join_cardinality"),
            DependencyEdge("exec", "review"),
        ),
        contracts=(contract,),
        structural_stats={"execution_count": 5, "transfer_reliability": 0.80},
    )

    bank = StructuralSchemaBank()
    bank.admit_schema(schema)

    engine = WorkflowEngine(verifier_cost=0.05)
    # Role profile with 100% omission rate to force handoff contract test
    profile = RoleProfile(
        name="stress_profile",
        planner_omission_rate=1.0,  # always omits cardinality unless recovered
        solver_ignore_plan_rate=0.0,
        reviewer_detection_rate=1.0,
    )

    # 3. Test Task 1: Preserve Rows (Standard task)
    task_standard = JoinTask(
        task_id="task_standard_01",
        group_id="group_customers",
        left_rows=10,
        actual_cardinality="one_to_many",
        expected_rows=25,
        intent=JoinIntent.PRESERVE_ROWS,
    )

    exploit, alt, explore = bank.retrieve_with_anti_lockin(
        task_cues=("join", "customer", "tables"),
        task_state=task_standard.observable_state(),
    )
    assert exploit is not None
    assert exploit.schema_id == "schema_join_standard"

    run, trace = engine.run_with_schema(task_standard, profile, exploit, seed=42)

    # Verification should have caught missing cardinality and triggered recovery
    assert len(run.recoveries) == 1
    assert run.recoveries[0].successful
    assert run.success
    assert trace.success
    assert trace.credit_result is None  # successful tasks have no failure tier

    # Add trace to Fast Episodic Store
    bank.fast_buffer.add_trace(trace, task_frequency=1.0)
    assert len(bank.fast_buffer.traces) == 1

    # 4. Test Task 2: Deceptive Twin Task (Intentional Expansion)
    task_twin = JoinTask(
        task_id="task_expansion_99",
        group_id="group_customers",
        left_rows=10,
        actual_cardinality="one_to_many",
        expected_rows=100,
        intent=JoinIntent.INTENTIONAL_EXPANSION,
    )

    # Pattern separation should detect conflict and refuse to apply the preserve_rows schema blindly
    exploit_twin, _, _ = bank.retrieve_with_anti_lockin(
        task_cues=("join", "customer", "tables"),
        task_state=task_twin.observable_state(),
    )
    # Because task_expansion_99 is in counterexamples and intent differs,
    # PatternSeparation triggers should_separate=True, preventing negative transfer
    assert exploit_twin is None

    # 5. Offline Consolidation (CLS Slow Store update)
    consolidated = bank.consolidate_offline(min_priority=0.20)
    assert consolidated == 1
    updated_schema = bank.schemas[0]
    assert updated_schema.execution_count == 6
    assert updated_schema.transfer_reliability >= 0.80
