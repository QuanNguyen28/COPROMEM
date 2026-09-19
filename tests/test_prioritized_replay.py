from copromem.bank import FastEpisodicBuffer, StructuralSchemaBank
from copromem.schema import DecompositionSchema
from copromem.types import DependencyEdge, EpisodicTrace, SubtaskNode


def test_fast_episodic_buffer_priority_and_sampling():
    buffer = FastEpisodicBuffer(max_capacity=5)

    # Success trace with low surprise
    t_success = EpisodicTrace(
        trace_id="tr_1",
        task_id="t1",
        task_state={"intent": "preserve_rows"},
        schema_id="s1",
        handoff_events=(),
        success=True,
        surprise=0.0,
        uncertainty=0.0,
    )

    # Failure trace with high surprise & uncertainty
    t_failure = EpisodicTrace(
        trace_id="tr_2",
        task_id="t2",
        task_state={"intent": "preserve_rows"},
        schema_id="s1",
        handoff_events=(),
        success=False,
        surprise=0.8,
        uncertainty=0.5,
    )

    e_succ = buffer.add_trace(t_success, task_frequency=1.0)
    e_fail = buffer.add_trace(t_failure, task_frequency=1.0)

    # Mattar-Daw priority of surprising failure should be substantially higher than routine success
    assert e_fail.replay_priority > e_succ.replay_priority

    # Sample top prioritized trace
    top = buffer.sample_prioritized(batch_size=1)
    assert len(top) == 1
    assert top[0].trace_id == "tr_2"


def test_schema_bank_anti_lockin_retrieval():
    bank = StructuralSchemaBank()

    # Schema 1: Sequential plan -> solve
    n1 = SubtaskNode("A", "planner", "plan")
    n2 = SubtaskNode("B", "solver", "solve")
    s1 = DecompositionSchema(
        schema_id="s_seq",
        task_family="Join",
        semantic_cues=("join", "customer", "data"),
        nodes=(n1, n2),
        edges=(DependencyEdge("A", "B"),),
        structural_stats={"execution_count": 15, "transfer_reliability": 0.85},
    )

    # Schema 2: Parallel plan -> [search, filter] -> solve
    n_search = SubtaskNode("search", "searcher", "search")
    n_filter = SubtaskNode("filter", "filterer", "filter")
    n_solve = SubtaskNode("solve", "solver", "solve")
    s2 = DecompositionSchema(
        schema_id="s_par",
        task_family="Join",
        semantic_cues=("join", "customer", "data"),
        nodes=(n_search, n_filter, n_solve),
        edges=(
            DependencyEdge("search", "solve"),
            DependencyEdge("filter", "solve"),
        ),
        structural_stats={"execution_count": 5, "transfer_reliability": 0.80},
    )

    bank.admit_schema(s1)
    bank.admit_schema(s2)

    task_cues = ("join", "customer", "data")
    task_state = {"intent": "preserve_rows"}

    exploit, alt, should_explore = bank.retrieve_with_anti_lockin(task_cues, task_state)

    # S1 has higher reliability -> exploit
    assert exploit is not None
    assert exploit.schema_id == "s_seq"

    # S2 has divergent graph structure -> returned as diverse alternative
    assert alt is not None
    assert alt.schema_id == "s_par"
    assert not should_explore


def test_offline_consolidation():
    bank = StructuralSchemaBank()
    n1 = SubtaskNode("A", "planner", "plan")
    n2 = SubtaskNode("B", "solver", "solve")
    s = DecompositionSchema(
        schema_id="s_target",
        task_family="Join",
        semantic_cues=("join",),
        nodes=(n1, n2),
        edges=(DependencyEdge("A", "B"),),
        structural_stats={"execution_count": 1, "transfer_reliability": 0.50},
    )
    bank.admit_schema(s)

    # Add a successful high-priority trace to fast buffer
    trace = EpisodicTrace(
        trace_id="tr_cons",
        task_id="task_1",
        task_state={"intent": "preserve_rows"},
        schema_id="s_target",
        handoff_events=(),
        success=True,
        surprise=0.6,
        uncertainty=0.4,
    )
    bank.fast_buffer.add_trace(trace, task_frequency=2.0)

    # Consolidate offline
    consolidated = bank.consolidate_offline(min_priority=0.40)
    assert consolidated == 1

    updated_schema = next(sc for sc in bank.schemas if sc.schema_id == "s_target")
    assert updated_schema.execution_count == 2
    assert updated_schema.transfer_reliability > 0.50
