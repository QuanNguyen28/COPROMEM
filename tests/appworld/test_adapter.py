from copromem.appworld_comparison_adapter import (
    AcquisitionIdentity,
    AppWorldPlumbingCallGate,
    CoProMemAppWorldAdapter,
    RawAcquisitionTrajectory,
    TrialInput,
    no_memory_prompt,
)
from copromem.checkpoints import RunStore
from copromem.decomposition import RecursiveTaskDecomposer
from copromem.copromem_memory_module import ProceduralMemoryItem, extract_intent_constraints
from copromem.providers import BudgetExceeded
from copromem.reme_paper_lifecycle import ReMeMemory, ReMePaperLifecycle


def _trajectory(index: int, success: bool = True, task_id: str = "dev_train_01") -> RawAcquisitionTrajectory:
    return RawAcquisitionTrajectory(
        AcquisitionIdentity(task_id, 17, index),
        "find pending orders and identify the most recent customer",
        "appworld",
        success,
        ("search_orders()", "inspect_customer()"),
    )


def test_intent_constraints_do_not_turn_count_into_identifier():
    count = extract_intent_constraints('Tell me the number of reviews mentioning "disappointed"')
    assert count["aggregation"] == "count"
    assert "entity_id" not in count
    assert extract_intent_constraints("Show me the customers who expressed dissatisfaction")["sentiment"] == "negative"
    phone = extract_intent_constraints("Find the customer name and email with phone number 2137418080")
    assert phone["target_type"] == "customer"
    assert phone["entity_id"] == "2137418080"


def test_comparison_adapter_starts_empty_and_preserves_unique_episodes():
    adapter = CoProMemAppWorldAdapter(api_key="")
    assert adapter.module.memories == []  # generic defaults removed only in adapter

    adapter.ingest(_trajectory(0, True))
    adapter.ingest(_trajectory(1, True))
    assert len(adapter.module.learning.pending) == 2
    adapter.consolidate()
    adapter.ingest(_trajectory(2, False))
    trace_ids = [trace.trace_id for trace in adapter.module.fast_buffer.traces]
    assert len(trace_ids) == len(set(trace_ids)) == 3
    assert trace_ids[0].endswith("trajectory=0")
    assert trace_ids[1].endswith("trajectory=1")
    assert adapter.module.fast_buffer.traces[2].success is False
    assert len(adapter.module.learning.pending) == 3

    assert adapter.module.bank.schemas == []
    adapter.ingest(_trajectory(3, True, "dev_train_02"))
    adapter.consolidate()
    assert adapter.module.bank.schemas == []
    assert adapter.module.memories == []
    assert len(adapter.module.learning.pending) == 4
    assert adapter.module.fast_buffer.traces[2].success is False


def test_copromem_retrieves_once_and_only_appends_registered_guidance():
    adapter = CoProMemAppWorldAdapter(api_key="")
    adapter.ingest(_trajectory(0, True))
    adapter.ingest(_trajectory(1, True, "dev_train_02"))
    adapter.consolidate()
    trial = TrialInput(
        "dev_eval_01", "find pending orders and identify the most recent customer",
        "appworld", base_prompt="COMMON EXECUTOR PROMPT", tool_spec={"same": "tools"},
    )
    state = adapter.export_state()
    guidance, provenance = adapter.retrieve_with_provenance(trial, 1)
    assert provenance["selected_memory_id"] is None
    assert provenance["selected_schema_id"] is None
    assert CoProMemAppWorldAdapter.reproduce_retrieval(state, provenance["task_input"], provenance) == guidance
    result = adapter.run_trial(trial, 0, lambda prompt, tools: {"prompt": prompt, "tools": tools}, lambda _: True)
    # Unknown structure is explicitly an empty retrieval, never generic text
    # that could be misreported as learned procedural guidance.
    assert result.injected_memory == ""
    assert no_memory_prompt(trial) == "COMMON EXECUTOR PROMPT"
    assert result.prompt == "COMMON EXECUTOR PROMPT"
    assert result.tool_spec == {"same": "tools"}
    assert result.scorer_input["task_id"] == "dev_eval_01"
    try:
        adapter.prepare_trial(trial, 0)
    except RuntimeError:
        pass
    else:
        raise AssertionError("second retrieval in one trial must be rejected")


def test_cold_copromem_has_no_retrieved_procedural_memory_and_conflict_is_excluded():
    adapter = CoProMemAppWorldAdapter(api_key="")
    cold = adapter.prepare_trial(TrialInput("cold", "find approved orders", "appworld"), 0)
    assert "Observed Successful Procedure" not in cold
    assert adapter.module.memories == []

    adapter.module.memories = [ProceduralMemoryItem(
        "bad", "find approved orders", "bad", "", "DANGEROUS APPROVED PROCEDURE",
        constraints={"status": "approved"}, domain="appworld", success=True,
    )]
    warm = adapter.prepare_trial(TrialInput("conflict", "find pending orders", "appworld"), 0)
    assert "DANGEROUS APPROVED PROCEDURE" not in warm


def test_reme_fixed_freezes_and_dynamic_has_independent_trial_streams():
    acquired = [ReMeMemory("base", utility=1, frequency=1)]
    fixed = ReMePaperLifecycle(acquired, dynamic=False)
    fixed.after_evaluation(stream=0, retrieved_ids=["base"], success=True, validated_addition=ReMeMemory("new"))
    assert "new" not in fixed.state_for_trial_stream(0).memories
    assert fixed.state_for_trial_stream(0).memories["base"].frequency == 1

    dynamic = ReMePaperLifecycle(acquired, dynamic=True)
    dynamic.after_evaluation(stream=0, retrieved_ids=["base"], success=True, validated_addition=ReMeMemory("new"))
    assert "new" in dynamic.state_for_trial_stream(0).memories
    assert dynamic.state_for_trial_stream(0).memories["base"].utility == 2
    assert "new" not in dynamic.state_for_trial_stream(1).memories


def test_keyed_decomposition_cap_fails_closed_before_any_network_call():
    decomposer = RecursiveTaskDecomposer(api_key="configured-but-never-used", max_llm_calls=0)
    try:
        decomposer.assess_complexity("find the correct customer and update its order")
    except RuntimeError as exc:
        assert "call cap exhausted" in str(exc)
    else:
        raise AssertionError("a configured decomposer must not silently fall back after cap exhaustion")


def test_smoke_gate_is_append_only_and_never_reserves_past_one_usd(tmp_path):
    gate = AppWorldPlumbingCallGate(RunStore(tmp_path), max_calls=4)
    first = gate.reserve("executor", 0.60)
    second = gate.reserve("reme_lifecycle", 0.40)
    assert gate.charged_or_reserved == 1.0
    assert (tmp_path / "plumbing_call_roles" / f"{first}.json").exists()
    assert (tmp_path / "plumbing_call_roles" / f"{second}.json").exists()
    try:
        gate.reserve("copromem_decomposition", 0.000001)
    except BudgetExceeded:
        pass
    else:
        raise AssertionError("a request beyond charged-plus-reserved cap must not start")
    resumed = AppWorldPlumbingCallGate(RunStore(tmp_path), max_calls=4)
    assert resumed.charged_or_reserved == 1.0
    try:
        resumed.reserve("executor", 0.000001)
    except BudgetExceeded:
        pass
    else:
        raise AssertionError("a resumed run must retain all prior reservations")


def test_decomposition_reserves_before_keyed_request(tmp_path, monkeypatch):
    gate = AppWorldPlumbingCallGate(RunStore(tmp_path), max_calls=1)
    adapter = CoProMemAppWorldAdapter(
        api_key="configured-but-never-used",
        decomposition_call_cap=1,
        call_gate=gate,
        decomposition_reserve_usd=1.0,
    )
    monkeypatch.setattr(
        "copromem.decomposition._call_openrouter_json",
        lambda *args, **kwargs: {"is_compound": False, "rationale": "fixture"},
    )
    adapter.module.decomposer.assess_complexity("find the correct customer")
    assert gate.charged_or_reserved == 1.0
