from copromem.benchmarks.appworld.adapter import (
    AcquisitionIdentity, CoProMemAppWorldAdapter, RawAcquisitionTrajectory,
)
from copromem.learning import ActionObservation
from copromem.online import ScoredCandidate, apply_task_batch


def _candidate(events):
    trajectory = RawAcquisitionTrajectory(
        AcquisitionIdentity("fixture-task", 1, 0), "redacted", "appworld", True,
        events=tuple(events))
    return ScoredCandidate(trajectory, 1.0, 0.0, 1)


def test_success_with_unobserved_nested_step_is_recorded_but_not_promoted():
    adapter = CoProMemAppWorldAdapter(api_key="")
    candidate = _candidate((
        ActionObservation("apis.notes.search", ("query",), ("results",), "", "observed", observed=True),
        ActionObservation("results.extend", ("page",), (), observed=False),
    ))
    assert apply_task_batch(adapter, [candidate]) is None
    episode_id = candidate.trajectory.identity.value
    schema_id = adapter.module.learning.episode_schemas[episode_id]
    assert schema_id.startswith("candidate_")
    assert adapter.module.learning.episode_procedures[episode_id] == []


def test_fully_observed_structural_steps_remain_promotable():
    adapter = CoProMemAppWorldAdapter(api_key="")
    candidate = _candidate((
        ActionObservation("apis.notes.search", ("query",), ("results",), "", "observed", observed=True),
        ActionObservation("apis.notes.show", ("note_id", "results"), ("note",), "", "observed", observed=True),
    ))
    winner = apply_task_batch(adapter, [candidate])
    assert winner == candidate.trajectory.identity.value
    schema_id = adapter.module.learning.episode_schemas[winner]
    assert adapter.module.learning.schemas[schema_id].status == "provisional"
