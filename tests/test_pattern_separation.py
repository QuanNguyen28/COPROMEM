from copromem.contracts import Contract
from copromem.pattern_separation import (
    PatternSeparationEngine,
    calculate_graph_distance,
    token_jaccard_similarity,
)
from copromem.schema import DecompositionSchema
from copromem.types import DependencyEdge, SubtaskNode


def test_token_jaccard_similarity():
    tokens_1 = ("join", "tables", "customer", "rows")
    tokens_2 = ("join", "tables", "customer", "expansion")
    # intersection: join, tables, customer (3)
    # union: join, tables, customer, rows, expansion (5) -> 3/5 = 0.60
    sim = token_jaccard_similarity(tokens_1, tokens_2)
    assert abs(sim - 0.60) < 1e-4

    assert token_jaccard_similarity((), ()) == 1.0
    assert token_jaccard_similarity(("a",), ("b",)) == 0.0


def test_calculate_graph_distance():
    n1 = SubtaskNode("A", "role_a", "intent_a")
    n2 = SubtaskNode("B", "role_b", "intent_b")
    n3 = SubtaskNode("C", "role_c", "intent_c")

    schema_1 = DecompositionSchema(
        schema_id="s1",
        task_family="Join",
        semantic_cues=("join",),
        nodes=(n1, n2, n3),
        edges=(DependencyEdge("A", "B"), DependencyEdge("B", "C")),
    )

    # Identical structure
    assert calculate_graph_distance(schema_1, schema_1) == 0.0

    # Inverted dependency: C -> B -> A
    schema_inverted = DecompositionSchema(
        schema_id="s2",
        task_family="Join",
        semantic_cues=("join",),
        nodes=(n3, n2, n1),
        edges=(DependencyEdge("C", "B"), DependencyEdge("B", "A")),
    )
    dist = calculate_graph_distance(schema_1, schema_inverted)
    assert dist > 0.0


def test_pattern_separation_on_twin_tasks():
    """Twin-task negative transfer stress test."""
    contract = Contract(
        contract_id="C_preserve_rows",
        interface="plan->exec",
        precondition="declared_cardinality is set",
        postcondition="cardinality matches input",
        verifier_name="plan_cardinality_present",
        owner="planner",
        recovery_route="replan",
        scope_name="join_preservation_scope",
        counterexamples=("intentional_expansion", "task_expansion_01"),
    )

    n1 = SubtaskNode("plan", "planner", "generate_plan")
    n2 = SubtaskNode("exec", "solver", "run_join")

    schema_preserve = DecompositionSchema(
        schema_id="schema_preserve_rows",
        task_family="DataJoin",
        semantic_cues=("join", "customer", "tables", "data", "rows"),
        nodes=(n1, n2),
        edges=(DependencyEdge("plan", "exec", contract_id="C_preserve_rows"),),
        contracts=(contract,),
    )

    engine = PatternSeparationEngine(semantic_threshold=0.40, causal_threshold=0.35)

    # Task A: Compatible task
    task_a_cues = ("join", "customer", "tables", "preserve", "rows")
    task_a_state = {"task_id": "task_preserve_01", "intent": "preserve_rows"}
    decision_a = engine.evaluate(
        task_a_cues,
        task_a_state,
        schema_preserve,
        candidate_state={"intent": "preserve_rows"},
    )
    assert not decision_a.should_separate
    assert decision_a.semantic_similarity >= 0.50

    # Task B: Twin task with deceptive surface similarity but conflicting intent
    task_b_cues = ("join", "customer", "tables", "many_to_many", "expansion")
    task_b_state = {"task_id": "task_expansion_01", "intent": "intentional_expansion"}
    decision_b = engine.evaluate(
        task_b_cues,
        task_b_state,
        schema_preserve,
        candidate_state={"intent": "preserve_rows"},
    )

    # Must trigger pattern separation to protect against negative transfer
    assert decision_b.should_separate
    assert decision_b.suggested_variant_id is not None
    assert "schema_preserve_rows_variant_intentional_expansion" in decision_b.suggested_variant_id
    assert "Negative transfer risk" in decision_b.reason
