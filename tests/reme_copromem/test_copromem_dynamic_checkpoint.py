from __future__ import annotations

import json

import pytest

from copromem.contrastive_graph_v6 import digest
from copromem.experiments.reme_copromem.copromem_dynamic_checkpoint import (
    CoProMemDynamicCheckpointError,
    CoProMemDynamicCheckpointManager,
)


TASKS = ("task-a", "task-b")
INITIAL = {"state_format": "copromem-v6.1-semantic-state-v1", "semantic_schemas": {}}


def _manager(tmp_path):
    return CoProMemDynamicCheckpointManager(
        root=tmp_path / "dynamic", manifest_sha256="m" * 64, source_identity_sha256="s" * 64,
        registry_sha256="r" * 64, ordered_tasks=TASKS, fixed_initial_state=INITIAL,
        dynamic_initial_state=INITIAL,
    )


def _complete_task(manager, task, state):
    manager.freeze_task_pre_state(task, state)
    manager.record(task, "retrievals_materialized", task_query_hashes=["q"], retrieval_hashes=["r1", "r2"])
    manager.record(task, "trajectories_complete", artifact_hashes=["a1", "a2"], scorer_evidence_hashes=["s1", "s2"])
    manager.record(task, "batch_ready", semantic_projection_hashes=["g1", "g2"])
    manager.record(task, "semantic_plan_persisted", plan_sha256="p")
    manager.record(task, "validation_persisted", validation_sha256="v", validation_passed=True)
    manager.record(task, "commit_persisted", marker_sha256="c", state="committed", winner_schema_id="schema")
    post = {**state, "semantic_schemas": {task: {"id": task}}}
    manager.snapshot_post_state(task, post, marker_sha256="c", plan_sha256="p", validation_sha256="v")
    manager.record(task, "next_task_authorized", post_state_sha256=digest(post))
    return post


def test_exact_prefix_restores_state_and_never_replays_completed_task(tmp_path):
    manager = _manager(tmp_path)
    post = _complete_task(manager, "task-a", INITIAL)
    state = manager.reconcile(ledger_reconciled=True, fixed_current_state=INITIAL)
    assert state["completed_task_count"] == 1
    assert state["next_task_id"] == "task-b"
    assert state["next_transition"] == "task_pre_state_frozen"
    assert state["dynamic_state"] == post
    with pytest.raises(CoProMemDynamicCheckpointError, match="conflict"):
        manager.record("task-a", "retrievals_materialized", task_query_hashes=["changed"], retrieval_hashes=["r1", "r2"])


@pytest.mark.parametrize("transition", (
    "task_pre_state_frozen", "retrievals_materialized", "trajectories_complete", "batch_ready",
    "semantic_plan_persisted", "validation_persisted", "commit_persisted", "post_state_snapshot_persisted",
    "next_task_authorized",
))
def test_crash_matrix_reports_exact_missing_transition_without_mutation(tmp_path, transition):
    manager = _manager(tmp_path)
    if transition != "task_pre_state_frozen":
        manager.freeze_task_pre_state("task-a", INITIAL)
    names = ["retrievals_materialized", "trajectories_complete", "batch_ready", "semantic_plan_persisted",
             "validation_persisted", "commit_persisted"]
    values = {
        "retrievals_materialized": dict(task_query_hashes=["q"], retrieval_hashes=["r1", "r2"]),
        "trajectories_complete": dict(artifact_hashes=["a1", "a2"], scorer_evidence_hashes=["s1", "s2"]),
        "batch_ready": dict(semantic_projection_hashes=["g1", "g2"]),
        "semantic_plan_persisted": dict(plan_sha256="p"),
        "validation_persisted": dict(validation_sha256="v", validation_passed=True),
        "commit_persisted": dict(marker_sha256="c", state="committed", winner_schema_id="schema"),
    }
    if transition != "task_pre_state_frozen":
        for name in names:
            if name == transition:
                break
            manager.record("task-a", name, **values[name])
        if transition in {"post_state_snapshot_persisted", "next_task_authorized"}:
            for name in names:
                if not manager._record_path("task-a", name).exists():
                    manager.record("task-a", name, **values[name])
        if transition == "next_task_authorized":
            post = {**INITIAL, "semantic_schemas": {"task-a": {"id": "task-a"}}}
            manager.snapshot_post_state("task-a", post, marker_sha256="c", plan_sha256="p", validation_sha256="v")
    state = manager.reconcile(ledger_reconciled=True, fixed_current_state=INITIAL)
    assert state["next_task_id"] == "task-a"
    assert state["next_transition"] == transition


def test_tamper_and_ambiguous_post_state_fail_closed(tmp_path):
    manager = _manager(tmp_path)
    _complete_task(manager, "task-a", INITIAL)
    path = manager._record_path("task-a", "commit_persisted")
    value = json.loads(path.read_text())
    value["winner_schema_id"] = "tampered"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(CoProMemDynamicCheckpointError, match="hash"):
        manager.reconcile(ledger_reconciled=True, fixed_current_state=INITIAL)


def test_fixed_drift_unsettled_ledger_and_reordered_task_fail_closed(tmp_path):
    manager = _manager(tmp_path)
    with pytest.raises(CoProMemDynamicCheckpointError, match="unresolved"):
        manager.reconcile(ledger_reconciled=False, fixed_current_state=INITIAL)
    with pytest.raises(CoProMemDynamicCheckpointError, match="Fixed"):
        manager.reconcile(ledger_reconciled=True, fixed_current_state={"mutated": True})
    with pytest.raises(CoProMemDynamicCheckpointError, match="outside"):
        manager.freeze_task_pre_state("not-registered", INITIAL)


def test_run_reconciled_is_global_content_addressed_and_tamper_detected(tmp_path):
    manager = _manager(tmp_path)
    state = _complete_task(manager, "task-a", INITIAL)
    _complete_task(manager, "task-b", state)
    marker = manager.record_run_reconciled(
        runtime_identity_file_sha256="runtime", terminal_reconciliation_sha256="terminal",
        scored_artifact_inventory_sha256="artifacts", expected_trajectories=20,
    )
    assert manager.validate_run_reconciled() == marker
    path = manager.run_reconciled_path
    value = json.loads(path.read_text(encoding="utf-8")); value["expected_trajectories"] = 99
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(CoProMemDynamicCheckpointError, match="hash"):
        manager.validate_run_reconciled()
