from __future__ import annotations

import hashlib
import importlib
import json

import pytest


runner = importlib.import_module("scripts.run_v61_exploratory_evaluation")


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _manifest():
    return {"evaluation": {"task_ids": ["task-a", "task-b"], "seeds": [11, 12, 13],
                            "pause_milestones": [1]}, "arms": ["a", "b"]}


def test_pause_request_requires_manifest_binding_and_preregistered_boundary(tmp_path, monkeypatch):
    manifest_path = tmp_path / "manifest.json"; _write(manifest_path, _manifest())
    manifest = _manifest(); bound = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    _write(tmp_path / "pause-request.json", {"version": "task-boundary-pause-v1",
                                               "manifest_sha256": bound, "after_completed_tasks": 1})
    assert runner._pause_request(tmp_path, manifest, completed_task_count=1)["after_completed_tasks"] == 1
    assert runner._pause_request(tmp_path, manifest, completed_task_count=2) is None
    _write(tmp_path / "pause-request.json", {"version": "task-boundary-pause-v1",
                                               "manifest_sha256": bound, "after_completed_tasks": 2})
    with pytest.raises(RuntimeError, match="not preregistered"):
        runner._pause_request(tmp_path, manifest, completed_task_count=2)


def test_pause_marker_requires_complete_task_prefix(tmp_path, monkeypatch):
    manifest_path = tmp_path / "manifest.json"; manifest = _manifest(); _write(manifest_path, manifest)
    _write(tmp_path / "ledger.jsonl", {"event": "settle"})
    _write(tmp_path / "live-summary.json", {"completed": 2})
    # One arm is absent: safe pausing is rejected rather than creating a
    # marker that a later run might mistake for a complete task boundary.
    _write(tmp_path / "artifacts" / "task-a" / "a" / "trial-1.json", {"ok": True})

    class CoPro:
        fixed_initial_state = {}
        def reconcile(self, **_kwargs): return {"completed_task_count": 1, "dynamic_state": {}}
    class Dynamic:
        def reconcile(self): return {"completed_count": 3}
    monkeypatch.setattr(runner, "_ledger_reconciled", lambda _path: True)
    with pytest.raises(RuntimeError, match="artifact prefix is incomplete"):
        runner._record_pause(tmp_path, manifest, task_position=1, task_id="task-a",
                             copro_checkpoint=CoPro(), dynamic_checkpoint=Dynamic(),
                             fixed_marker={"checkpoint_sha256": "f" * 64})
