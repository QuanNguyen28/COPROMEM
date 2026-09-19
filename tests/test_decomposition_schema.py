import pytest
from copromem.contracts import Contract
from copromem.schema import DecompositionSchema
from copromem.types import DependencyEdge, SubtaskNode


def test_schema_valid_dag_and_topological_sort():
    n1 = SubtaskNode("plan", "planner", "generate_plan", output_keys=("plan_spec",))
    n2 = SubtaskNode("fetch", "fetcher", "fetch_data", input_keys=("plan_spec",), output_keys=("raw_data",))
    n3 = SubtaskNode("clean", "cleaner", "clean_data", input_keys=("raw_data",), output_keys=("clean_data",))
    n4 = SubtaskNode("summarize", "writer", "write_summary", input_keys=("clean_data",), output_keys=("report",))

    edges = (
        DependencyEdge("plan", "fetch"),
        DependencyEdge("fetch", "clean"),
        DependencyEdge("clean", "summarize"),
    )

    schema = DecompositionSchema(
        schema_id="data_pipeline_v1",
        task_family="ETL",
        semantic_cues=("extract", "transform", "load"),
        nodes=(n4, n2, n1, n3),  # intentionally out of order
        edges=edges,
    )

    ordered = schema.topological_sort()
    assert [n.node_id for n in ordered] == ["plan", "fetch", "clean", "summarize"]

    waves = schema.parallel_waves()
    assert len(waves) == 4
    assert [w[0].node_id for w in waves] == ["plan", "fetch", "clean", "summarize"]


def test_schema_parallel_waves():
    n1 = SubtaskNode("plan", "planner", "plan")
    n2a = SubtaskNode("search_flights", "flight_agent", "search")
    n2b = SubtaskNode("search_hotels", "hotel_agent", "search")
    n3 = SubtaskNode("bundle", "aggregator", "bundle")

    edges = (
        DependencyEdge("plan", "search_flights"),
        DependencyEdge("plan", "search_hotels"),
        DependencyEdge("search_flights", "bundle"),
        DependencyEdge("search_hotels", "bundle"),
    )

    schema = DecompositionSchema(
        schema_id="travel_booking_v1",
        task_family="Travel",
        semantic_cues=("flight", "hotel"),
        nodes=(n1, n2a, n2b, n3),
        edges=edges,
    )

    waves = schema.parallel_waves()
    assert len(waves) == 3
    assert [n.node_id for n in waves[0]] == ["plan"]
    assert sorted(n.node_id for n in waves[1]) == ["search_flights", "search_hotels"]
    assert [n.node_id for n in waves[2]] == ["bundle"]


def test_schema_cycle_detection():
    n1 = SubtaskNode("A", "role_a", "step_a")
    n2 = SubtaskNode("B", "role_b", "step_b")

    edges = (
        DependencyEdge("A", "B"),
        DependencyEdge("B", "A"),
    )

    with pytest.raises(ValueError, match="Cycle detected"):
        DecompositionSchema(
            schema_id="cyclic_schema",
            task_family="Test",
            semantic_cues=("test",),
            nodes=(n1, n2),
            edges=edges,
        )


def test_schema_self_loop():
    n1 = SubtaskNode("A", "role_a", "step_a")
    with pytest.raises(ValueError, match="Self-loop"):
        DecompositionSchema(
            schema_id="self_loop_schema",
            task_family="Test",
            semantic_cues=("test",),
            nodes=(n1,),
            edges=(DependencyEdge("A", "A"),),
        )


def test_schema_missing_edge_node():
    n1 = SubtaskNode("A", "role_a", "step_a")
    with pytest.raises(ValueError, match="not found in nodes"):
        DecompositionSchema(
            schema_id="missing_node_schema",
            task_family="Test",
            semantic_cues=("test",),
            nodes=(n1,),
            edges=(DependencyEdge("A", "NON_EXISTENT"),),
        )


def test_schema_contracts_and_serialization():
    contract = Contract(
        contract_id="C_check_plan",
        interface="plan->exec",
        precondition="plan is non-empty",
        postcondition="plan is valid",
        verifier_name="plan_cardinality_present",
        owner="planner",
        recovery_route="replan",
        scope_name="join_preservation_scope",
        counterexamples=(),
    )
    n1 = SubtaskNode("plan", "planner", "plan")
    n2 = SubtaskNode("exec", "solver", "exec")
    edge = DependencyEdge("plan", "exec", contract_id="C_check_plan")

    schema = DecompositionSchema(
        schema_id="plan_exec_schema",
        task_family="Join",
        semantic_cues=("join",),
        nodes=(n1, n2),
        edges=(edge,),
        contracts=(contract,),
    )

    retrieved = schema.get_contract_for_edge("plan", "exec")
    assert retrieved is not None
    assert retrieved.contract_id == "C_check_plan"
    assert schema.get_contract_for_edge("exec", "plan") is None

    # Test serialization
    data = schema.as_dict()
    assert data["schema_id"] == "plan_exec_schema"
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1
