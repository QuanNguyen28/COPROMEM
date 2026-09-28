import hashlib
import json

import pytest

from copromem.learning import (
    ActionObservation, LearningCore, ReplayOutcome, ValidationTask,
)
from copromem.copromem_memory_module import COPROMEMMemoryModule
from copromem.benchmarks.appworld.adapter import (
    AcquisitionIdentity, CoProMemAppWorldAdapter, RawAcquisitionTrajectory, TrialInput,
)


def events(operation="lookup"):
    return (
        ActionObservation(operation, ("query",), ("record",), check="record exists"),
        ActionObservation("inspect", ("record",), ("answer",), check="answer matches query"),
    )


class Evaluator:
    def __init__(self, scores):
        self.scores = scores
        self.calls = []

    def evaluate(self, task, guidance, variant):
        self.calls.append((task.task_id, task.seed, variant, guidance))
        return ReplayOutcome(self.scores[task.task_id][variant], 1, f"{task.task_id}:{variant}")

    def upper_bound(self, task, variant):
        return 1


def test_structural_identity_and_episode_resume():
    core = LearningCore()
    first = core.observe("ep1", "source", events(), True)
    assert first != core.observe("ep2", "other", events("delete"), True)
    assert first == core.observe("ep3", "other", events("LOOKUP"), True)
    before = core.export_state()
    assert LearningCore.from_state(before).observe("ep1", "source", events(), True) == first
    assert core.export_state() == before
    with pytest.raises(ValueError, match="different content"):
        core.observe("ep1", "source", events("delete"), True)
    assert core.observe("weak", "source", (ActionObservation("lookup"),), True).startswith("candidate_")
    assert core.retrieve("general", (ActionObservation("lookup"),)).compatibility == "unknown"


def test_promoted_schema_uses_winning_episode_evidence_after_resume():
    core = LearningCore()
    failed = (ActionObservation("lookup", ("query",), ("record",),
                                precondition="wrong assumption", check="wrong check"),)
    winner = (ActionObservation("lookup", ("query",), ("record",),
                                precondition="verified input", check="record observed"),)
    core.observe("failed", "task", failed, False)
    core.observe("winner", "task", winner, True)
    core = LearningCore.from_state(core.export_state())
    assert core.promote_episode("winner")
    guidance = core.retrieve("general", winner).text
    assert "verified input" in guidance and "record observed" in guidance
    assert "wrong assumption" not in guidance and "wrong check" not in guidance


def test_optional_paired_diagnostic_and_online_step_scoped_prompt():
    core = LearningCore()
    sid = core.observe("ep", "source", events(), True)
    tasks = (ValidationTask("source", 5), ValidationTask("v1", 5), ValidationTask("v2", 5))
    evaluator = Evaluator({"v1": {"no_memory": 0, "schema": 1, "schema_procedure": 1},
                           "v2": {"no_memory": 0, "schema": 0, "schema_procedure": 1}})
    assert core.validate(sid, tasks, evaluator, 6)
    assert [call[2] for call in evaluator.calls] == ["no_memory", "schema", "schema_procedure"] * 2
    assert all(call[0] != "source" for call in evaluator.calls)
    assert core.retrieve("general", events()).schema_id is None
    assert core.promote_episode("ep")
    retrieved = core.retrieve("general", events())
    assert retrieved.compatibility == "compatible"
    assert retrieved.schema_id == sid and len(retrieved.procedure_ids) == 2
    assert retrieved.text.index("step_1") < retrieved.text.index("step_2")
    assert retrieved.text.index("record exists") < retrieved.text.index("step_2")
    assert core.retrieve("general", events("delete")).compatibility == "unknown"
    assert sid not in core.retrieve("general", events("delete")).text


def test_harm_budget_and_missing_evidence_stay_pending():
    core = LearningCore()
    sid = core.observe("ep", "source", events(), True)
    tasks = (ValidationTask("v1", 1), ValidationTask("v2", 1))
    good = Evaluator({"v1": {"no_memory": 0, "schema": 1, "schema_procedure": 1},
                      "v2": {"no_memory": 1, "schema": 0, "schema_procedure": 1}})
    assert not core.validate(sid, tasks, good, 6)
    assert core.schemas[sid].status == "candidate"
    assert not core.validate(sid, tasks, good, 2)
    assert not core.validate(sid, tasks[:1], good, 6)
    assert not core.validate(sid, tasks, None, 6)
    assert core.retrieve("general", events()).schema_id is None


def test_procedure_needs_incremental_gain_without_harm():
    core = LearningCore()
    sid = core.observe("ep", "source", events(), True)
    evaluator = Evaluator({"v1": {"no_memory": 0, "schema": 1, "schema_procedure": 0},
                           "v2": {"no_memory": 0, "schema": 1, "schema_procedure": 1}})
    assert core.validate(sid, (ValidationTask("v1", 1), ValidationTask("v2", 1)), evaluator, 6)
    assert core.admission[sid]["procedure_admitted"] is False
    result = core.retrieve("general", events())
    assert result.schema_id is None
    assert all(proc.status == "pending" for proc in core.procedures.values())


def test_task_values_are_parameterized_in_learned_procedure():
    core = LearningCore()
    event = ActionObservation("search order 123", ("order_id",), ("record",),
                              check="order 123 is visible", parameters={"order_id": "123"})
    sid = core.observe("one", "source", (event,), True)
    equivalent = ActionObservation("search order 456", ("order_id",), ("record",),
                                   check="order 456 is visible", parameters={"order_id": "456"})
    assert sid == core.observe("two", "another", (equivalent,), True)
    assert "123" not in next(iter(core.procedures.values())).text
    assert "{order_id}" in next(iter(core.procedures.values())).text


def test_offline_diagnostic_requires_distinct_task_ids_and_reserves_cost():
    core = LearningCore()
    sid = core.observe("ep", "source", events(), True)
    evaluator = Evaluator({"a": {"no_memory": 0, "schema": 1, "schema_procedure": 1},
                           "b": {"no_memory": 0, "schema": 1, "schema_procedure": 1}})
    tasks = (ValidationTask("a", 1), ValidationTask("a", 2), ValidationTask("b", 1))
    assert core.validate(sid, tasks, evaluator, 6)
    assert {task_id for task_id, _, _, _ in evaluator.calls} == {"a", "b"}
    evaluator.calls.clear()
    assert not core.validate(sid, tasks, evaluator, 0.5)
    assert evaluator.calls == []


def test_module_state_version_and_read_only_retrieval():
    module = COPROMEMMemoryModule(api_key="", seed_default_memories=False)
    sid = module.observe_events("ep", "source", events(), True)
    state = module.export_state()
    before = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
    result = module.retrieve_memory("copromem_v2", "v1", "lookup record", structural_events=events())
    assert result.selected_schema_id is None
    assert before == hashlib.sha256(json.dumps(module.export_state(), sort_keys=True).encode()).hexdigest()
    resumed = COPROMEMMemoryModule(api_key="", seed_default_memories=False)
    resumed.load_state(state)
    assert sid in resumed.learning.schemas
    with pytest.raises(ValueError, match="audit-only"):
        resumed.load_state({"schema_bank": {}})


def test_appworld_adapter_renders_only_admitted_structural_evidence():
    adapter = CoProMemAppWorldAdapter(api_key="")
    trajectory = RawAcquisitionTrajectory(
        AcquisitionIdentity("source", 1, 0), "lookup record", "appworld", True,
        events=events())
    adapter.ingest(trajectory)
    trial = TrialInput("v1", "lookup record", "appworld", structural_events=events())
    guidance, provenance = adapter.retrieve_with_provenance(trial, 1)
    assert "Workflow" not in guidance
    assert provenance["selected_schema_id"] is None
    sid = next(iter(adapter.module.learning.schemas))
    evaluator = Evaluator({"v1": {"no_memory": 0, "schema": 1, "schema_procedure": 1},
                           "v2": {"no_memory": 0, "schema": 0, "schema_procedure": 1}})
    assert adapter.module.admit_from_replay(sid, (ValidationTask("v1", 1),
                                                 ValidationTask("v2", 1)), evaluator, 6)
    assert adapter.module.promote_episode("source::seed=1::trajectory=0")
    before_resume = adapter.export_state()
    adapter.ingest(trajectory)
    assert adapter.export_state() == before_resume
    state = adapter.export_state()
    second = TrialInput("v2", "lookup record", "appworld", structural_events=events())
    guidance, provenance = adapter.retrieve_with_provenance(second, 2)
    assert provenance["selected_schema_id"] == sid
    assert len(provenance["injected_procedure_ids"]) == 2
    assert "record exists" in guidance
    assert CoProMemAppWorldAdapter.reproduce_retrieval(
        state, provenance["task_input"], provenance) == guidance
