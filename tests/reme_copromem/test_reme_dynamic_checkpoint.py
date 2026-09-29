from __future__ import annotations

import copy
import json
import pathlib

import pytest

from copromem.experiments.reme_copromem.runner import invoke_post_score_update
from copromem.integrations.reme.dynamic_checkpoint import (
    DynamicCheckpointError,
    DynamicUpdateIdentity,
    ReMeDynamicCheckpointManager,
)


def _write_rows(path: pathlib.Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


class _LocalService:
    def __init__(self) -> None:
        self.rows = [{"memory_id": "m0", "memory": "initial", "vector": [0.1, 0.2]}]
        self.provider_calls = 0

    def dump(self, path: pathlib.Path) -> None:
        _write_rows(path, self.rows)

    def load(self, path: pathlib.Path) -> None:
        self.rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def verifier_dump(self, snapshot: pathlib.Path, target: pathlib.Path) -> None:
        # A fresh, local verifier that never makes a lifecycle/embedding call.
        rows = [json.loads(line) for line in snapshot.read_text(encoding="utf-8").splitlines()]
        _write_rows(target, copy.deepcopy(rows))


def _identity(index: int) -> DynamicUpdateIdentity:
    return DynamicUpdateIdentity(f"evaluation:official_upstream_reme_dynamic:t{index}:trial=1:seed={100+index}", f"t{index}", 1, 100 + index)


def _artifact(tmp_path: pathlib.Path, identity: DynamicUpdateIdentity) -> tuple[pathlib.Path, dict]:
    journal = tmp_path / "evidence" / f"{identity.task_id}.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text('{"event":"response_attested"}\n', encoding="utf-8")
    import hashlib
    evidence_hash = hashlib.sha256(journal.read_bytes()).hexdigest()
    artifact = tmp_path / "artifacts" / f"{identity.task_id}.json"
    result = {"trajectory_id": identity.trajectory_id, "task_id": identity.task_id, "trial_id": identity.trial_id,
              "seed": identity.seed, "after_score": 1.0, "history_sha256": f"history-{identity.task_id}",
              "execution_evidence_path": str(journal.resolve()), "execution_evidence_sha256": evidence_hash,
              "upstream_retrieval_identity": f"official:{identity.value()}"}
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
    return artifact, result


def _manager(tmp_path: pathlib.Path, *, count: int = 2, mismatch: bool = False, settlements=None, validate=None,
             marker_validate=None, verifier_guard=None):
    service = _LocalService()
    order = [_identity(i) for i in range(1, count + 1)]
    def update(_agent, _score, _event):
        service.rows.append({"memory_id": f"m{len(service.rows)}", "memory": "updated", "vector": [0.3, 0.4]})
    def verifier(snapshot, target):
        service.verifier_dump(snapshot, target)
        if mismatch:
            rows = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
            rows[0]["vector"][0] = 9.0
            _write_rows(target, rows)
    manager = ReMeDynamicCheckpointManager(root=tmp_path / "checkpoints", ordered_updates=order,
        dump_current=service.dump, load_current=service.load, dump_verifier=verifier,
        official_update=update, ledger_offset=lambda: 7,
        settled_ids=settlements or (lambda offset: [f"settled-after-{offset}"]),
        validate_settlements=validate or (lambda _offset, _ids: None),
        validate_marker_settlements=marker_validate or (lambda _marker: None),
        verify_no_provider_calls=verifier_guard or (lambda _offset: None))
    return manager, service, order


def test_first_second_update_restart_and_two_verifiers(tmp_path):
    manager, service, order = _manager(tmp_path)
    first_path, first = _artifact(tmp_path, order[0])
    marker1 = manager.complete(agent=object(), result=first, artifact_path=first_path)
    assert marker1["ordered_update_index"] == 1
    second_path, second = _artifact(tmp_path, order[1])
    marker2 = manager.complete(agent=object(), result=second, artifact_path=second_path)
    assert marker2["predecessor_completion_marker_sha256"]
    assert manager.reconcile()["next_identity"] is None
    service.rows = []
    assert manager.restore_latest()["completed_count"] == 2
    assert len(service.rows) == 3


def test_valid_completed_update_never_replays(tmp_path):
    manager, service, order = _manager(tmp_path, count=1)
    path, result = _artifact(tmp_path, order[0])
    manager.complete(agent=object(), result=result, artifact_path=path)
    before = len(service.rows)
    manager.restore_latest()
    with pytest.raises(DynamicCheckpointError, match="replay"):
        manager.complete(agent=object(), result=result, artifact_path=path)
    assert len(service.rows) == before


@pytest.mark.parametrize("fault", ["intent_only", "snapshot_only", "marker_without_snapshot", "bad_pre", "bad_post", "bad_artifact", "bad_journal", "bad_predecessor", "out_of_order", "duplicate"])
def test_ambiguous_or_mismatched_checkpoint_fails_closed(tmp_path, fault):
    manager, _service, order = _manager(tmp_path)
    path, result = _artifact(tmp_path, order[0])
    if fault == "intent_only":
        manager.dump_current(manager.snapshots / "pre-0001.jsonl")
        manager._write_intent(index=1, identity=order[0], result=result, artifact=path, pre_hash="x")
    elif fault == "snapshot_only":
        manager.dump_current(manager._snapshot(1))
    else:
        manager.complete(agent=object(), result=result, artifact_path=path)
        marker = manager._path(manager.markers, 1)
        value = json.loads(marker.read_text())
        if fault == "marker_without_snapshot": manager._snapshot(1).unlink()
        elif fault == "bad_pre": value["pre_update_semantic_sha256"] = "bad"
        elif fault == "bad_post": value["post_update_semantic_sha256"] = "bad"
        elif fault == "bad_artifact": (path.write_text("tampered", encoding="utf-8"))
        elif fault == "bad_journal": pathlib.Path(result["execution_evidence_path"]).write_text("tampered", encoding="utf-8")
        elif fault == "bad_predecessor": value["predecessor_completion_marker_sha256"] = "bad"
        elif fault == "out_of_order": value["ordered_update_index"] = 2
        elif fault == "duplicate":
            (manager.intents / "update-0002.json").write_text("{}", encoding="utf-8")
        if fault not in {"bad_artifact", "bad_journal", "duplicate", "marker_without_snapshot"}:
            marker.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(DynamicCheckpointError): manager.reconcile()


def test_verifier_vector_mismatch_fixed_isolation_and_settlement_binding(tmp_path):
    manager, _service, order = _manager(tmp_path, count=1, mismatch=True, settlements=lambda _o: ["l1", "e1"])
    path, result = _artifact(tmp_path, order[0])
    with pytest.raises(DynamicCheckpointError, match="equivalence"):
        manager.complete(agent=object(), result=result, artifact_path=path)
    assert not manager._path(manager.markers, 1).exists()


def test_fixed_bank_mutation_and_unknown_or_unresolved_settlement_fail_closed(tmp_path):
    manager, service, order = _manager(tmp_path, count=1)
    fixed = tmp_path / "fixed.jsonl"; service.dump(fixed)
    from copromem.integrations.reme.bank import semantic_bank_hash
    manager.verify_fixed_bank(fixed, semantic_bank_hash(fixed))
    fixed.write_text('{"memory_id":"mutated","vector":[1.0]}\n', encoding="utf-8")
    with pytest.raises(DynamicCheckpointError, match="Fixed"):
        manager.verify_fixed_bank(fixed, "not-the-mutated-hash")
    rejecting, _service, rejecting_order = _manager(tmp_path / "settlement", count=1,
        settlements=lambda _offset: ["unknown"],
        validate=lambda _offset, ids: (_ for _ in ()).throw(DynamicCheckpointError("unknown or unresolved settlement")))
    artifact, result = _artifact(tmp_path / "settlement", rejecting_order[0])
    with pytest.raises(DynamicCheckpointError, match="settlement"):
        rejecting.complete(agent=object(), result=result, artifact_path=artifact)


def test_strict_callback_propagates_but_legacy_is_best_effort(tmp_path):
    progress = tmp_path / "progress.jsonl"
    def boom(*_args): raise ValueError("checkpoint failed")
    invoke_post_score_update(boom, object(), {}, object(), strict=False, progress=progress, trajectory_id="t", arm="legacy")
    with pytest.raises(ValueError):
        invoke_post_score_update(boom, object(), {}, object(), strict=True, progress=progress, trajectory_id="t", arm="dynamic")
    rows = [json.loads(line) for line in progress.read_text().splitlines()]
    assert rows[-1]["strict"] is True and len(rows) == 2


def test_unresolved_or_unknown_settlement_is_rejected_by_caller_contract(tmp_path):
    manager, _service, order = _manager(tmp_path, count=1, settlements=lambda _o: [])
    path, result = _artifact(tmp_path, order[0])
    marker = manager.complete(agent=object(), result=result, artifact_path=path)
    assert marker["newly_settled_lifecycle_or_embedding_ids"] == []


def test_verifier_never_calls_provider_and_ordered_next_identity(tmp_path):
    manager, service, order = _manager(tmp_path)
    artifact, result = _artifact(tmp_path, order[0])
    manager.complete(agent=object(), result=result, artifact_path=artifact)
    state = manager.reconcile()
    assert state["next_identity"] == order[1].__dict__
    assert service.provider_calls == 0


def test_verifier_provider_attempt_and_marker_settlement_tamper_fail_closed(tmp_path):
    guarded, _service, order = _manager(tmp_path / "provider", count=1,
        verifier_guard=lambda _offset: (_ for _ in ()).throw(DynamicCheckpointError("verifier provider call")))
    artifact, result = _artifact(tmp_path / "provider", order[0])
    with pytest.raises(DynamicCheckpointError, match="verifier provider"):
        guarded.complete(agent=object(), result=result, artifact_path=artifact)
    manager, _service, order = _manager(tmp_path / "marker", count=1)
    artifact, result = _artifact(tmp_path / "marker", order[0])
    manager.complete(agent=object(), result=result, artifact_path=artifact)
    manager.validate_marker_settlements = lambda _marker: (_ for _ in ()).throw(DynamicCheckpointError("invalid settlement binding"))
    with pytest.raises(DynamicCheckpointError, match="settlement"):
        manager.reconcile()
