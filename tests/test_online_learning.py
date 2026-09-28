from copromem.benchmarks.appworld.adapter import (
    AcquisitionIdentity, CoProMemAppWorldAdapter, RawAcquisitionTrajectory,
    normalize_appworld_history,
)
from copromem.learning import ActionObservation
from copromem.online import ScoredCandidate, apply_task_batch


def _trial(task, trial, success=True, operation="lookup"):
    events = (ActionObservation(operation, ("query",), ("record",),
                                check="record observed"),)
    return RawAcquisitionTrajectory(
        AcquisitionIdentity(task, trial + 10, trial), "lookup record", "appworld",
        success, events=events)


def test_task_batch_promotes_one_winner_and_resume_is_idempotent():
    adapter = CoProMemAppWorldAdapter(api_key="")
    start = adapter.export_state()
    first = _trial("task-a", 1)
    second = _trial("task-a", 2, operation="delete")
    candidates = [ScoredCandidate(first, 1.0, 0.2, 3),
                  ScoredCandidate(second, 1.0, 0.1, 4)]
    assert apply_task_batch(adapter, candidates) == second.identity.value
    state = adapter.export_state()
    assert start != state
    assert len(state["learning"]["episodes"]) == 2
    statuses = {schema["nodes"][0]["intent"]: schema["status"]
                for schema in state["learning"]["schemas"]}
    assert statuses == {"lookup": "candidate", "delete": "provisional"}
    assert apply_task_batch(adapter, candidates) == second.identity.value
    assert adapter.export_state() == state


def test_failed_task_stays_pending_and_two_harmed_tasks_quarantine():
    adapter = CoProMemAppWorldAdapter(api_key="")
    source = _trial("train", 1)
    adapter.ingest(source, promote=True)
    sid = next(iter(adapter.module.learning.schemas))
    failed = _trial("val-a", 1, success=False)
    assert apply_task_batch(adapter, [ScoredCandidate(
        failed, 0.0, 0.0, 1, sid, 1.0)]) is None
    assert adapter.module.learning.schemas[sid].status == "provisional"
    failed_b = _trial("val-b", 1, success=False)
    assert apply_task_batch(adapter, [ScoredCandidate(
        failed_b, 0.0, 0.0, 1, sid, 1.0)]) is None
    assert adapter.module.learning.schemas[sid].status == "quarantined"
    assert adapter.module.learning.retrieve("appworld", source.events).compatibility == "conflict"


def test_history_normalizer_uses_public_shape_and_requires_success_for_procedure():
    history = [{"role": "user", "content": "Find order 123"},
               {"role": "assistant", "content": "orders.search(status='pending')"},
               {"role": "user", "content": "Output: private order 123"}]
    event, = normalize_appworld_history(history, True)
    assert event.operation == "orders.search" and event.input_slots == ("status",)
    assert "123" not in repr(event)
    assert event.check == "API response observed"
    assert normalize_appworld_history(history, False)[0].check == "API response observed"
    assert normalize_appworld_history([
        {"role": "assistant", "content": "print(1)"}], True) == ()


def test_normalizer_does_not_attribute_task_success_to_last_call_or_assume_loop_ran():
    history = [{"role": "assistant", "content": "orders.update(id='123')\norders.search(status='done')"},
               {"role": "user", "content": "Output: done"}]
    events = normalize_appworld_history(history, True)
    assert [event.operation for event in events] == ["orders.update", "orders.search"]
    assert all(event.check == "API response observed" for event in events)
    assert all("task success" not in event.check for event in events)
    loop = normalize_appworld_history([
        {"role": "assistant", "content": "for item in items:\n    orders.update(item)"},
        {"role": "user", "content": "Output: done"}], True)
    assert len(loop) == 1 and not loop[0].observed
    assert loop[0].operation == "orders.update"
    assert normalize_appworld_history([
        {"role": "assistant", "content": "orders.update(id='123')"},
        {"role": "user", "content": "Traceback (most recent call last): failure"}], True)[0].check == ""
