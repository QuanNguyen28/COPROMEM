import sys

import pytest

from copromem.benchmarks.appworld.adapter import AcquisitionIdentity, CoProMemAppWorldAdapter, RawAcquisitionTrajectory
from copromem.experiments.reme_copromem.gate import build_gate
from copromem.experiments.reme_copromem import config
from copromem.experiments.reme_copromem.runner import digest, write_json


def _fixtures():
    adapter = CoProMemAppWorldAdapter(api_key="")
    rows = []
    for index, task_id in enumerate(("a", "b")):
        identity = AcquisitionIdentity(task_id, 1, index)
        adapter.ingest(RawAcquisitionTrajectory(identity, "Find pending orders", "appworld", False))
        rows.append({"acquisition_identity": identity.value, "task_id": task_id,
                     "instruction": "Find pending orders", "after_score": 0,
                     "history": [{"role": "user", "content": "Find pending orders"}]})
    return adapter.export_state(), rows


def test_warm_start_audit_accepts_pending_evidence_and_rejects_missing_episode():
    state, rows = _fixtures()
    gate = build_gate(state, rows)
    assert gate["passed"] and gate["episode_count"] == 2
    assert not build_gate(state, rows[:1])["passed"]


def test_preflight_checks_audit_hash_and_public_descriptor(tmp_path, monkeypatch):
    state, rows = _fixtures()
    run = tmp_path / "run"
    source = tmp_path / "acquisition.json"
    write_json(source, rows)
    gate_path = run / "copromem/acquisition-retrieval-gate.json"
    write_json(run / "copromem/initial-state.json", state)
    write_json(gate_path, build_gate(state, rows))
    manifest_sha = run / "manifest.sha256"
    manifest_sha.write_text("dummy\n", encoding="utf-8")
    monkeypatch.setattr(config, "RUN", run)
    monkeypatch.setattr(config, "PROGRESS", run / "progress.jsonl")
    monkeypatch.setattr(config, "MANIFEST_SHA", manifest_sha)
    monkeypatch.setattr(config, "c_free_gb", lambda: 10.0)
    monkeypatch.setenv("COPROMEM_ACQUISITION_POOL", str(source))
    for name in ("COPROMEM_REME_PYTHON", "COPROMEM_REME_SOURCE",
                 "COPROMEM_APPWORLD_PYTHON", "COPROMEM_APPWORLD_ROOT"):
        monkeypatch.setenv(name, sys.executable)
    value = {"acquisition": {"export_sha256": config.file_sha(source),
                             "retrieval_gate_sha256": config.file_sha(gate_path),
                             "copromem_bank_sha256": digest(state)},
             "evaluation": {"task_ids": ["eval"], "descriptors": {"eval": [
                 {"operation": "lookup", "input_slots": ["query"], "output_slots": ["record"]}]}}}
    config.preflight(value)
    assert (run / "copromem/descriptor-audit.json").is_file()
    assert config.descriptor_audit(value, state) == {"eval": "unknown"}
    value["evaluation"]["expected_initial_compatibility"] = {"eval": "compatible"}
    with pytest.raises(RuntimeError, match="initial descriptor compatibility mismatch"):
        config.preflight(value)
    value["evaluation"].pop("expected_initial_compatibility")
    bad = dict(value)
    bad["evaluation"] = {"task_ids": ["eval"], "descriptors": {}}
    with pytest.raises(RuntimeError, match="missing public structural descriptor"):
        config.preflight(bad)
    gate = build_gate(state, rows)
    gate["episode_count"] = 0
    write_json(gate_path, gate)
    value["acquisition"]["retrieval_gate_sha256"] = config.file_sha(gate_path)
    with pytest.raises(RuntimeError, match="warm-start audit"):
        config.preflight(value)
