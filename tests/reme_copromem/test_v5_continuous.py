import json
import hashlib

import pytest

from copromem.benchmarks.appworld.adapter import CoProMemAppWorldAdapter
from copromem.experiments.reme_copromem import config
from copromem.experiments.reme_copromem.runner import (
    ReMeService, construct_copromem, digest, raw_acquisition_trajectories, write_json,
)
from copromem.integrations.reme.transport import AppendOnlyLedger


def test_train_warm_start_promotes_only_scored_winner(tmp_path):
    history = [{"role": "user", "content": "Find pending orders"},
               {"role": "assistant", "content": "print(orders.search(status='pending'))"},
               {"role": "user", "content": "Output: []"}]
    rows = [
        {"acquisition_identity": f"train::seed={seed}::trajectory={index}",
         "task_id": "train", "instruction": "Find pending orders", "history": history,
         "after_score": score, "history_sha256": f"history-{index}",
         "source_artifact_sha256": f"artifact-{index}"}
        for index, (seed, score) in enumerate(((11, 0.0), (12, 1.0)))
    ]
    state, _ = construct_copromem(
        run=tmp_path, progress=tmp_path / "progress.jsonl",
        ledger=AppendOnlyLedger(tmp_path / "ledger.jsonl", 1.0),
        api_key="", raw=raw_acquisition_trajectories(rows))
    assert len(state["learning"]["episodes"]) == 2
    assert state["learning"]["schemas"][0]["status"] == "provisional"
    assert state["learning"]["procedures"][0]["status"] == "provisional"


def test_task_boundary_merge_uses_one_snapshot_and_resume_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUN", tmp_path)
    monkeypatch.setattr(config, "LEDGER", tmp_path / "ledger.jsonl")
    adapter = CoProMemAppWorldAdapter(api_key="")
    before = adapter.export_state()
    write_json(tmp_path / "copromem/task_pre_states/task.json", before)
    for trial, operation, score in ((0, "orders.search", 0.0), (1, "orders.update", 1.0)):
        history = [{"role": "user", "content": "Update order"},
                   {"role": "assistant", "content": f"{operation}(id='123')"},
                   {"role": "user", "content": "Output: done"}]
        for arm, arm_score in (("copromem_dynamic", score), ("no_memory", 0.0)):
            write_json(config.artifact(arm, "task", trial), {
                "arm": arm, "task_id": "task", "trial_id": trial,
                "history": history, "history_sha256": digest(history),
                "after_score": arm_score, "actions": 1})
        write_json(tmp_path / "retrieval/copromem_dynamic/task" / f"trial-{trial}.json",
                   {"provenance": {"pre_state_sha256": digest(before),
                                   "selected_schema_id": None}})
    config.complete_copro_task(adapter, "task", [0, 1], [10, 11])
    first = adapter.export_state()
    marker = json.loads((tmp_path / "copromem/task_updates/task.json").read_text())
    pending = tmp_path / "copromem/task_updates_pending/task.json"
    assert pending.is_file()
    assert marker["pending_update_sha256"] == hashlib.sha256(pending.read_bytes()).hexdigest()
    assert marker["winner_episode_id"] == "task::seed=11::trajectory=1"
    assert len(first["learning"]["episodes"]) == 2
    assert sum(schema["status"] == "provisional" for schema in first["learning"]["schemas"]) == 1
    resumed = CoProMemAppWorldAdapter(api_key="")
    config.complete_copro_task(resumed, "task", [0, 1], [10, 11])
    assert resumed.export_state() == first
    provenance = tmp_path / "retrieval/copromem_dynamic/task/trial-0.json"
    row = json.loads(provenance.read_text())
    row["provenance"]["pre_state_sha256"] = "wrong"
    write_json(provenance, row)
    with pytest.raises(RuntimeError, match="retrieval provenance changed"):
        config.complete_copro_task(CoProMemAppWorldAdapter(api_key=""), "task", [0, 1], [10, 11])


def test_interrupted_task_merge_reconciles_from_pending_inputs_without_rescoring(tmp_path, monkeypatch):
    """A marker-loss interruption is resolved from completed local evidence only."""
    monkeypatch.setattr(config, "RUN", tmp_path)
    monkeypatch.setattr(config, "LEDGER", tmp_path / "ledger.jsonl")
    adapter = CoProMemAppWorldAdapter(api_key="")
    pre = adapter.export_state()
    write_json(tmp_path / "copromem/task_pre_states/task.json", pre)
    history = [{"role": "user", "content": "Update order"},
               {"role": "assistant", "content": "orders.update(id='123')"},
               {"role": "user", "content": "Output: done"}]
    for trial, seed, score in ((0, 10, 0.0), (1, 11, 1.0)):
        for arm, arm_score in (("copromem_dynamic", score), ("no_memory", 0.0)):
            write_json(config.artifact(arm, "task", trial), {
                "arm": arm, "task_id": "task", "trial_id": trial,
                "history": history, "history_sha256": digest(history),
                "after_score": arm_score, "actions": 1})
        write_json(tmp_path / "retrieval/copromem_dynamic/task" / f"trial-{trial}.json",
                   {"provenance": {"pre_state_sha256": digest(pre), "selected_schema_id": None}})
    config.complete_copro_task(adapter, "task", [0, 1], [10, 11])
    committed = adapter.export_state()
    # Simulate a crash only after the durable state snapshot: never call a
    # scorer or provider to recover, and recompute the pure merge from pre.
    (tmp_path / "copromem/task_updates/task.json").unlink()
    resumed = CoProMemAppWorldAdapter(api_key="")
    config.complete_copro_task(resumed, "task", [0, 1], [10, 11])
    assert resumed.export_state() == committed
    assert (tmp_path / "copromem/task_updates/task.json").is_file()


def test_reme_service_preserves_src_import_root_for_split_environment(tmp_path, monkeypatch):
    captured = {}

    class Process:
        def poll(self): return 0

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return Process()

    monkeypatch.setattr("copromem.experiments.reme_copromem.runner.subprocess.Popen", fake_popen)
    service = ReMeService(port=19999, name="fixture", run=tmp_path,
                          ledger=tmp_path / "ledger.jsonl", progress=tmp_path / "progress.jsonl",
                          cap_usd=1.0)
    try:
        roots = captured["env"]["PYTHONPATH"].split(__import__("os").pathsep)
        assert str(__import__("copromem.experiments.reme_copromem.runner", fromlist=["ROOT"]).ROOT / "src") in roots
        assert captured["command"][-2:] == ["-m", "copromem.integrations.reme.corrected_service"]
    finally:
        service._log.close()


def test_reme_service_cold_start_deadline_is_source_bound():
    from copromem.experiments.reme_copromem.runner import REME_SERVICE_HEALTH_TIMEOUT_SECONDS

    # The deadline must accommodate a cold import from the mounted upstream
    # environment, while remaining a fixed part of the executable source.
    assert REME_SERVICE_HEALTH_TIMEOUT_SECONDS == 300.0


def test_same_run_directory_refuses_a_duplicate_runner_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUN", tmp_path)
    monkeypatch.setattr(config, "MANIFEST_SHA", tmp_path / "manifest.sha256")
    (tmp_path / "manifest.sha256").write_text("frozen\n", encoding="utf-8")
    config.acquire_lock()
    with pytest.raises(RuntimeError, match="already active"):
        config.acquire_lock()
    (tmp_path / "runner.lock").unlink()
