from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("v627_external_admission_runner", ROOT / "scripts" / "run_v627_external_admission.py")
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def _sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _bank(root: Path) -> Path:
    root.mkdir()
    state = {"contrastive_v6_schemas": {"candidate": {"terminal_effect": "apis.spotify.follow_artist"}}}
    (root / "fixed-bank.json").write_text(json.dumps(state), encoding="utf-8")
    (root / "recovery-report.json").write_text(json.dumps({"source": "immutable"}), encoding="utf-8")
    gate = {"version": "copromem-v6.2.7-seed-bank-promotion-v1", "passed": True, "provider_calls": 0,
            "state_sha256": _sha(state), "recovery_report_sha256": hashlib.sha256((root / "recovery-report.json").read_bytes()).hexdigest()}
    (root / "semantic-admission-gate.json").write_text(json.dumps(gate), encoding="utf-8")
    return root


def _paths(tmp_path: Path):
    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps({"unseen_train_tasks": [{"task_id": "fresh_1", "instruction": "Spotify task", "app_descriptions": {"spotify": "public"}}, {"task_id": "test_1", "instruction": "Spotify task", "app_descriptions": {"spotify": "public"}}]}), encoding="utf-8")
    evaluation = tmp_path / "evaluation.json"; evaluation.write_text(json.dumps({"selected_task_ids": ["test_1"]}), encoding="utf-8")
    registry = tmp_path / "registry.json"; registry.write_text(json.dumps({"registry_sha256": "registry"}), encoding="utf-8")
    return inventory, evaluation, registry


def test_allocation_is_one_fresh_task_and_hash_binds_candidate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    inventory, evaluation, registry = _paths(tmp_path); bank = _bank(tmp_path / "bank")
    monkeypatch.setattr(runner.base, "REG", registry)
    monkeypatch.setattr(runner, "_used_seed_task_ids", lambda: {"seed_1"})
    monkeypatch.setattr(runner, "build_intents", lambda _root: {"intents": "public"})
    monkeypatch.setattr(runner, "derive_task_query", lambda *_a, **_k: {"query_sha256": "query"})
    monkeypatch.setattr(runner, "candidate_validation_retrieve", lambda *_a, **_k: ("# guidance", {"guidance_nonempty": True, "retrieval_sha256": "retrieval", "guidance_sha256": "guidance"}))
    run = tmp_path / "run"
    runner.allocate(run, inventory, evaluation, bank, "fresh_1", "candidate")
    audit = json.loads((run / runner.ALLOCATION_NAME).read_text(encoding="utf-8"))
    assert audit["selected_task_ids"] == ["fresh_1"]
    assert audit["candidate_schema_id"] == "candidate"
    assert audit["provider_calls"] == 0
    assert audit["copromem_bank"]["semantic_state_sha256"] == _sha(json.loads((bank / "fixed-bank.json").read_text()))


def test_allocation_rejects_test_or_seed_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    inventory, evaluation, registry = _paths(tmp_path); bank = _bank(tmp_path / "bank")
    monkeypatch.setattr(runner.base, "REG", registry)
    monkeypatch.setattr(runner, "_used_seed_task_ids", lambda: {"fresh_1"})
    with pytest.raises(RuntimeError, match="already used"):
        runner.allocate(tmp_path / "run", inventory, evaluation, bank, "fresh_1", "candidate")
    monkeypatch.setattr(runner, "_used_seed_task_ids", lambda: set())
    with pytest.raises(RuntimeError, match="already used"):
        runner.allocate(tmp_path / "other", inventory, evaluation, bank, "test_1", "candidate")
