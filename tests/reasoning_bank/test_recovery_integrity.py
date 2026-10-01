from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from copromem.integrations.reasoning_bank import recovery


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    source = tmp_path / "source"
    manifest = {
        "git_commit": "a" * 40, "protocol_sha256": "b" * 64, "registry_sha256": "c" * 64,
        "initial_bank_sha256": "d" * 64, "execution": {"model": "fixture"},
        "embedding": {"model": "fixture-embedding"},
        "protocol": {"upstream_commit": "e" * 40},
        "evaluation": {"task_ids": ["task_1", "task_2"], "seeds": [9701, 9702]},
        "arms": ["no_memory", "reasoningbank_dynamic"],
    }
    _write_json(source / "manifest.json", manifest)
    (source / "manifest.sha256").write_text(recovery.file_sha256(source / "manifest.json") + "\n", encoding="utf-8")
    journal = source / "journals" / "evidence.jsonl"
    journal.parent.mkdir(parents=True); journal.write_text('{"event":"call"}\n', encoding="utf-8")
    scorer = source / "journals" / "scorer.jsonl"; scorer.write_text('{"score":1}\n', encoding="utf-8")
    artifact = {
        "task_id": "task_1", "arm": "no_memory", "trial_id": 1, "seed": 9701,
        "trajectory_id": "evaluation:no_memory:task_1:trial=1:seed=9701",
        "history_sha256": "f" * 64, "after_score": 1.0, "actions": 3, "termination": "completed",
        "execution_evidence_path": str(journal.resolve()), "execution_evidence_run_relative": "journals/evidence.jsonl",
        "execution_evidence_sha256": recovery.file_sha256(journal), "execution_evidence_rows": 1,
        "execution_evidence_registry_sha256": "c" * 64,
        "official_scorer_evidence": {"path": str(scorer.resolve()), "sha256": recovery.file_sha256(scorer),
                                     "history_sha256": "f" * 64},
    }
    _write_json(source / "artifacts" / "task_1" / "no_memory" / "trial-1.json", artifact)
    role = "executor:no_memory:task_1:trial=1:seed=9701"
    records = [
        {"event": "reserve", "id": "call-1", "role": role, "usd": 1.0},
        {"event": "settle", "id": "call-1", "role": role, "usd": .1},
    ]
    (source / "ledger.jsonl").write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in records), encoding="utf-8")
    monkeypatch.setattr(recovery, "validate_evidence", lambda *args, **kwargs: None)
    return source


def _envelope(source: Path) -> dict:
    return recovery.build_envelope(source, task_id="task_1", arm="no_memory", trial_id=1, seed=9701)


def test_marker_is_atomic_exact_and_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = _source(tmp_path, monkeypatch); envelope = _envelope(source); marker = tmp_path / "successor" / "recovery-import-completed.json"
    first = recovery.publish_marker(marker, envelope=envelope)
    assert recovery.publish_marker(marker, envelope=envelope) == first
    changed = copy.deepcopy(envelope); changed["key"]["seed"] = 9702
    with pytest.raises(recovery.RecoveryIntegrityError):
        recovery.publish_marker(marker, envelope=changed)
    assert json.loads(marker.read_text(encoding="utf-8")) == first


def test_partial_marker_fails_without_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = _source(tmp_path, monkeypatch); envelope = _envelope(source); marker = tmp_path / "successor" / "recovery-import-completed.json"
    marker.parent.mkdir(); marker.with_suffix(".json.tmp").write_text("partial", encoding="utf-8")
    with pytest.raises(recovery.RecoveryIntegrityError, match="partial"):
        recovery.publish_marker(marker, envelope=envelope)
    assert not marker.exists()


@pytest.mark.parametrize("target", ["artifact", "journal", "scorer", "ledger", "manifest"])
def test_every_source_evidence_domain_is_hash_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str):
    source = _source(tmp_path, monkeypatch); envelope = _envelope(source)
    paths = {
        "artifact": source / "artifacts/task_1/no_memory/trial-1.json",
        "journal": source / "journals/evidence.jsonl",
        "scorer": source / "journals/scorer.jsonl",
        "ledger": source / "ledger.jsonl",
        "manifest": source / "manifest.json",
    }
    with paths[target].open("a", encoding="utf-8") as handle: handle.write(" \n")
    with pytest.raises((recovery.RecoveryIntegrityError, json.JSONDecodeError, KeyError, ValueError)):
        recovery.validate_envelope(envelope, source)


def test_ledger_order_and_duplicate_ids_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = _source(tmp_path, monkeypatch); envelope = _envelope(source); ledger = source / "ledger.jsonl"
    lines = ledger.read_text(encoding="utf-8").splitlines()
    ledger.write_text("\n".join(reversed(lines)) + "\n", encoding="utf-8")
    with pytest.raises(recovery.RecoveryIntegrityError): recovery.validate_envelope(envelope, source)
    source = _source(tmp_path / "again", monkeypatch); ledger = source / "ledger.jsonl"
    with ledger.open("a", encoding="utf-8") as handle: handle.write(ledger.read_text(encoding="utf-8").splitlines()[0] + "\n")
    with pytest.raises(recovery.RecoveryIntegrityError, match="duplicated"):
        _envelope(source)


def test_successor_position_and_manifest_runtime_identity_are_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    envelope = _envelope(_source(tmp_path, monkeypatch))
    assert envelope["successor_allocation_position"] == 0
    runtime = envelope["source_runtime_identity"]
    assert runtime["version"] == "reasoningbank-manifest-bound-legacy-runtime-identity-v1"
    assert runtime["executable_source_commit"] == "a" * 40
    assert runtime["runtime_identity_sha256"] == recovery.digest({key: value for key, value in runtime.items()
                                                                   if key != "runtime_identity_sha256"})


def test_real_engineering_002_artifact_validates_read_only():
    source = Path("E:/Project/AAMAS/reasoningbank-appworld-artifacts/reasoningbank_appworld_engineering_002")
    if not source.is_dir(): pytest.skip("real immutable Engineering 002 evidence is unavailable")
    envelope = recovery.build_envelope(source, task_id="fac291d_1", arm="no_memory", trial_id=1, seed=9701)
    assert envelope["source_artifact_file_sha256"] == "6dae6fab4531e70151701e26633c3570aac8ec5b3276ee7687dea8942d04114e"
    assert envelope["source_journal_file_sha256"] == "a054d0b9f5ff2b99df19232931ca9dc97aa2cb3140d2e91384eba713e8b8570d"
    assert len(envelope["source_ledger"]["ordered_settlement_ids"]) == 10


def _runner():
    path = Path(__file__).parents[2] / "scripts" / "run_reasoningbank_appworld_engineering.py"
    spec = importlib.util.spec_from_file_location("reasoningbank_recovery_runner", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_imported_summary_is_one_of_twelve_without_charging_arm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    runner = _runner(); source = _source(tmp_path / "fixture", monkeypatch); envelope = _envelope(source)
    run = tmp_path / "successor"; run.mkdir()
    manifest = {"evaluation": {"task_ids": ["task_1", "task_2", "task_3"]},
                "historical_infrastructure_exposure_usd": .25,
                "historical_carry_forward_id": runner.HISTORICAL_CARRY_ID,
                "recovery_import": envelope}
    recovery.publish_marker(run / "recovery-import-completed.json", envelope=envelope)
    rows = [{"event": "reserve", "id": runner.HISTORICAL_CARRY_ID, "role": "historical_carry_forward", "usd": .25},
            {"event": "settle", "id": runner.HISTORICAL_CARRY_ID, "role": "historical_carry_forward", "usd": .25}]
    (run / "ledger.jsonl").write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    runner._summary(run, manifest, "recovery_imported")
    summary = json.loads((run / "live-summary.json").read_text(encoding="utf-8"))
    assert summary["completed"] == 1 and summary["expected"] == 12
    assert summary["arms"]["no_memory"]["Completed"] == 1
    assert summary["arms"]["reasoningbank_dynamic"]["Completed"] == 0
    assert summary["arms"]["no_memory"]["TotalCost"] == 0
    assert summary["arms"]["no_memory"]["SuccessRate"] == 1
    assert summary["historical_settled_exposure"] == pytest.approx(.25)


def test_imported_prefix_admits_exact_next_work_and_rejects_gap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    runner = _runner(); source = _source(tmp_path / "fixture", monkeypatch); envelope = _envelope(source)
    run = tmp_path / "successor"; run.mkdir()
    manifest = {"evaluation": {"task_ids": ["task_1", "task_2"], "seeds": [9701, 9702]},
                "arms": ["no_memory", "reasoningbank_dynamic"], "registry_sha256": "c" * 64,
                "recovery_import": envelope}
    recovery.publish_marker(run / "recovery-import-completed.json", envelope=envelope)
    count, next_key = runner._reconcile_execution_prefix(manifest, run)
    assert count == 1 and next_key == ("no_memory", "task_1", 2, 9702)
    gap = run / "artifacts" / "task_1" / "reasoningbank_dynamic" / "trial-1.json"
    _write_json(gap, {"arm": "reasoningbank_dynamic", "task_id": "task_1", "trial_id": 1, "seed": 9701})
    monkeypatch.setattr(runner, "validate_evidence", lambda *args, **kwargs: None)
    with pytest.raises(RuntimeError, match="ordered schedule prefix"):
        runner._reconcile_execution_prefix(manifest, run)
