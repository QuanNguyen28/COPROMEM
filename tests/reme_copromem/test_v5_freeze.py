import hashlib
import json

import pytest

from copromem.experiments.reme_copromem import freeze_v5, prepare_v5
from copromem.experiments.reme_copromem.runner import write_json


def test_freeze_pins_new_bank_gate_export_and_dependency(tmp_path, monkeypatch):
    run = tmp_path / "new-run"
    state = {"memories": [], "pending_memories": [], "schema_bank": {"schemas": [], "traces": [],
        "max_capacity": 200, "consolidated_trace_ids": []}}
    write_json(run / "copromem/initial-state.json", state)
    canonical = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    write_json(run / "copromem/acquisition-retrieval-gate.json",
        {"passed": True, "bank_sha256": hashlib.sha256(canonical).hexdigest()})
    rows = [{"task_id": "acq"}]
    acquisition = tmp_path / "acquisition.json"
    write_json(acquisition, rows)
    write_json(run / "copromem/acquisition-code.json",
        {"git_commit": "commit-id", "source_export_sha256": freeze_v5.sha(acquisition)})
    template = tmp_path / "template.json"
    write_json(template, {"protocol": "continuous_copromem_v5",
        "arms": ["no_memory", "official_upstream_reme_fixed", "official_upstream_reme_dynamic", "copromem_dynamic"],
        "acquisition": {"expected_trajectories": 1},
        "evaluation": {"task_ids": ["eval"], "descriptors": {"eval": [
            {"operation": "lookup", "input_slots": ["query"], "output_slots": ["record"]}]}}})
    dependency = tmp_path / "upstream.py"
    dependency.write_text("# pinned\n", encoding="utf-8")

    def fake_git(arguments, **_):
        return "" if "status" in arguments else "commit-id\n"
    monkeypatch.setattr(freeze_v5.subprocess, "check_output", fake_git)
    manifest = freeze_v5.freeze(template, acquisition, run, [dependency])
    value = json.loads(manifest.read_text(encoding="utf-8"))
    assert value["git_commit"] == "commit-id"
    assert value["acquisition"]["export_sha256"] == freeze_v5.sha(acquisition)
    assert value["acquisition"]["retrieval_gate_sha256"] == freeze_v5.sha(run / "copromem/acquisition-retrieval-gate.json")
    assert (run / "manifest.sha256").read_text().strip() == freeze_v5.sha(manifest)
    with pytest.raises(FileExistsError):
        freeze_v5.freeze(template, acquisition, run, [dependency])


def test_prepare_rejects_unpinned_export_before_any_paid_call(tmp_path, monkeypatch):
    monkeypatch.setattr(prepare_v5.subprocess, "check_output",
        lambda arguments, **_: "" if "status" in arguments else "commit-id\n")
    acquisition = tmp_path / "acquisition.json"
    write_json(acquisition, [{"task_id": "acq"}])
    template = tmp_path / "template.json"
    write_json(template, {"protocol": "continuous_copromem_v5",
        "arms": ["no_memory", "official_upstream_reme_fixed", "official_upstream_reme_dynamic", "copromem_dynamic"],
        "acquisition": {"expected_trajectories": 1, "source_export_sha256": "0" * 64},
        "evaluation": {"task_ids": ["eval"], "descriptors": {"eval": [
            {"operation": "lookup", "input_slots": ["query"], "output_slots": ["record"]}]}}})
    with pytest.raises(RuntimeError, match="not pinned"):
        prepare_v5.prepare(template, acquisition, tmp_path / "new-run")
