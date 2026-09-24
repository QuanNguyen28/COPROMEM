"""Integration checks for the live memory module's episode/replay lifecycle."""

from copromem.copromem_memory_module import COPROMEMMemoryModule, ProceduralMemoryItem
from copromem.contracts import Contract, validate_contract
from copromem.decomposition import RecursiveTaskDecomposer
from copromem.pattern_separation import PatternSeparationEngine
from copromem.schema import DecompositionSchema
from copromem.types import DependencyEdge, FailureTier, HandoffEvent, SubtaskNode


def test_episode_replay_is_offline_deduplicated_and_resumable():
    module = COPROMEMMemoryModule(api_key="")
    module.memories = []
    first = module.retrieve_memory("copromem_v2", "t1", "Find product", "shop")
    schema_id = first.schema.schema_id
    module.record_episode("t1", "copromem_v2", True, {"intent": "Find product"}, first.schema)

    assert module.fast_buffer is module.bank.fast_buffer
    assert module.bank.schemas[0].execution_count == 0
    assert module.bank.consolidate_offline(min_priority=0.2) == 1
    assert module.bank.consolidate_offline(min_priority=0.2) == 0

    second = module.retrieve_memory("copromem_v2", "t2", "Find product", "shop")
    assert second.schema.schema_id == schema_id
    assert second.schema.execution_count == 1
    module.record_episode("t2", "copromem_v2", True, {"intent": "Find product"}, second.schema)
    assert module.bank.consolidate_offline(min_priority=0.2) == 1
    assert next(s for s in module.bank.schemas if s.schema_id == schema_id).status == "admitted"

    restored = COPROMEMMemoryModule(api_key="")
    restored.load_state(module.export_state())
    assert restored.bank.consolidate_offline(min_priority=0.2) == 0
    assert restored.retrieve_memory("copromem_v2", "t3", "Find product", "shop").schema.execution_count == 2


def test_induced_procedure_waits_for_schema_admission():
    module = COPROMEMMemoryModule(api_key="")
    module.memories = []
    intent = "find approved orders"
    result = module.retrieve_memory("copromem_v2", "t1", intent, "shop")
    module.add_memory(ProceduralMemoryItem(
        "learned", intent, "learned", "", "ADMITTED PROCEDURE",
        constraints={"status": "approved"}, schema_id=result.schema.schema_id,
    ), defer_until_admitted=True)
    assert not module.memories
    assert len(module.pending_memories) == 1

    module.record_episode("t1", "copromem_v2", True, {}, result.schema)
    module.consolidate_offline()
    assert not module.memories

    module.record_episode("t2", "copromem_v2", True, {}, result.schema)
    module.consolidate_offline()
    assert [item.memory_id for item in module.memories] == ["learned"]
    assert not module.pending_memories


def test_failure_without_boundary_evidence_is_unknown():
    module = COPROMEMMemoryModule(api_key="")
    result = module.retrieve_memory("copromem_v2", "t1", "Find product", "shop")
    credit = module.record_episode(
        "t1", "copromem_v2", False, {"intent": "Find product"}, result.schema
    )
    assert credit.tier is FailureTier.UNKNOWN
    assert module.fast_buffer.traces[0].credit_result == credit


def test_browser_action_verifier_attributes_only_unrecovered_error():
    contract = Contract(
        "browser_action_accepted_v1", "agent_to_browser", "action exists",
        "browser reports no error", "browser_action_accepted", "planner",
        "inspect browser error and retry", "browser_action_scope", (), ("action",),
    )
    validate_contract(contract)
    bad_event = HandoffEvent(
        "agent_to_browser", "agent", "browser", {"action": "click('missing')"},
        {"last_action_error": "element missing"},
    )
    bad_event = HandoffEvent(
        bad_event.interface, bad_event.source_role, bad_event.target_role,
        bad_event.artifact, bad_event.observable_state,
        (contract.verify(bad_event),),
    )
    good_event = HandoffEvent(
        "agent_to_browser", "agent", "browser", {"action": "click('valid')"},
        {"last_action_error": ""},
    )
    good_event = HandoffEvent(
        good_event.interface, good_event.source_role, good_event.target_role,
        good_event.artifact, good_event.observable_state,
        (contract.verify(good_event),),
    )
    module = COPROMEMMemoryModule(api_key="")
    unresolved = module.record_episode(
        "bad", "copromem_v2", False, {}, None, [bad_event]
    )
    recovered = module.record_episode(
        "recovered", "copromem_v2", False, {}, None,
        [bad_event, good_event],
    )
    assert unresolved.tier is FailureTier.HANDOFF_VIOLATION
    assert recovered.tier is FailureTier.UNKNOWN
    restored = COPROMEMMemoryModule(api_key="")
    restored.load_state(module.export_state())
    assert not restored.fast_buffer.traces[0].handoff_events[0].verifier_results[0].passed
    assert restored.fast_buffer.traces[0].credit_result.tier is FailureTier.HANDOFF_VIOLATION


def test_graph_conflict_is_separated_when_graph_is_observable():
    nodes = (SubtaskNode("a", "planner", "plan"), SubtaskNode("b", "solver", "solve"))
    old = DecompositionSchema("old", "x", ("same", "task"), nodes, (DependencyEdge("a", "b"),))
    new = DecompositionSchema("new", "x", ("same", "task"), nodes, (DependencyEdge("b", "a"),))
    decision = PatternSeparationEngine(0.4, 0.35).evaluate(
        ("same", "task"), {"intent": "same task"}, old, task_schema=new
    )
    assert decision.should_separate
    assert "dag" in decision.divergent_constraints


def test_compatible_memory_is_considered_after_vetoed_candidate():
    module = COPROMEMMemoryModule(api_key="")
    module.memories = [
        ProceduralMemoryItem("bad", "find pending orders", "bad", "", "bad procedure",
                             constraints={"status": "approved"}),
        ProceduralMemoryItem("good", "find pending order", "good", "", "good procedure",
                             constraints={"status": "pending"}),
    ]
    result = module.retrieve_memory(
        "copromem_v2", "t", "find pending orders", "shop"
    )
    assert not result.should_veto
    assert "good procedure" in result.injected_text


def test_vetoed_macro_never_enters_decomposition_prompt():
    module = COPROMEMMemoryModule(api_key="")
    intent = "Get the customer of the most recent pending order"
    module.memories = [
        ProceduralMemoryItem(
            "bad", intent, "bad", "", "DANGEROUS APPROVED-ONLY PROCEDURE",
            constraints={"status": "approved"},
        )
    ]
    result = module.retrieve_memory("copromem_v2", "t", intent, "shop")
    assert result.should_veto
    assert "DANGEROUS APPROVED-ONLY PROCEDURE" not in result.injected_text


def test_decomposition_cache_tracks_memory_content():
    decomposer = RecursiveTaskDecomposer(api_key="")
    intent = "Get the customer of the most recent pending order"
    first = ProceduralMemoryItem("first", intent, "first", "", "FIRST PROCEDURE")
    second = ProceduralMemoryItem("second", intent, "second", "", "SECOND PROCEDURE")
    assert "FIRST PROCEDURE" in decomposer.decompose(intent, [first]).injected_prompt_text
    second_plan = decomposer.decompose(intent, [second])
    assert "SECOND PROCEDURE" in second_plan.injected_prompt_text
    assert "FIRST PROCEDURE" not in second_plan.injected_prompt_text


def test_compatible_macro_does_not_claim_pattern_separation():
    module = COPROMEMMemoryModule(api_key="")
    intent = "Get the customer of the most recent pending order"
    module.memories = [
        ProceduralMemoryItem(
            "prior", intent, "prior", "", "OBSERVED PROCEDURE",
            constraints={"status": "pending"},
        )
    ]
    result = module.retrieve_memory("copromem_v2", "t", intent, "shop")
    assert "OBSERVED PROCEDURE" in result.injected_text
    assert not result.should_veto
    assert not result.separated


def test_conflicting_task_creates_distinct_schema_and_counterexample():
    module = COPROMEMMemoryModule(api_key="", include_contract_guidance=True)
    module.memories = []
    source_intent = "find approved orders"
    source = module.retrieve_memory("copromem_v2", "source_1", source_intent, "shop")
    for task_id in ("source_1", "source_2"):
        module.record_episode(
            task_id, "copromem_v2", True, {"intent": source_intent}, source.schema
        )
    module.bank.consolidate_offline(min_priority=0.2)
    module.add_memory(ProceduralMemoryItem(
        "learned", source_intent, "approved", "", "approved procedure",
        constraints={"status": "approved"}, schema_id=source.schema.schema_id,
    ))

    target = module.retrieve_memory(
        "copromem_v2", "target", "find pending orders", "shop"
    )
    assert target.should_veto
    assert target.schema.schema_id != source.schema.schema_id
    prior = next(s for s in module.bank.schemas if s.schema_id == source.schema.schema_id)
    assert "target" in prior.structural_stats["counterexamples"]
    assert "approved procedure" not in target.injected_text


def test_retrieval_does_not_use_memory_from_another_domain():
    module = COPROMEMMemoryModule(api_key="")
    module.memories = [ProceduralMemoryItem(
        "other", "find pending orders", "other", "", "OTHER DOMAIN PROCEDURE",
        domain="other_domain",
    )]
    result = module.retrieve_memory(
        "copromem_v2", "t", "find pending orders", "shop"
    )
    assert "OTHER DOMAIN PROCEDURE" not in result.injected_text
