from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from copromem.contrastive_graph_v6 import digest
from copromem.experiments.reme_copromem.recovery_import import RecoveryImportError
from scripts import run_v61_exploratory_evaluation as base
from scripts import run_v622_parallel_real_pilot_recovery_003 as recovery


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _copro_fixture(tmp_path: Path, arm: str) -> tuple[Path, Path, dict, dict]:
    fixed = {"container": "fixed", "entries": [1]}
    dynamic = {"container": "dynamic", "entries": [2]}
    initial = {
        "fixed_initial_state": fixed,
        "fixed_initial_state_sha256": digest(fixed),
        "dynamic_initial_state": dynamic,
        "dynamic_initial_state_sha256": digest(dynamic),
    }
    source_run = tmp_path / "source"
    _write(source_run / "copromem-dynamic-checkpoints" / "initial.json", initial)
    source_artifact = source_run / "artifact.json"
    target_artifact = tmp_path / "target-artifact.json"
    source = {"arm": arm, "task_id": "task", "trial_id": 1,
              "pre_state_sha256": digest(fixed if arm == "copromem_v6_2_2_fixed" else dynamic),
              "initial_prompt_messages_sha256": "prompt", "model_visible_prompt_sha256": "prompt"}
    _write(source_artifact, source)
    _write(target_artifact, source)
    source_retrieval = source_run / "retrievals" / "task" / f"{arm}-1.json"
    target_retrieval = tmp_path / "target-retrieval.json"
    _write(source_retrieval, {"guidance": "", "task_query": {}, "provenance": {}})
    target_retrieval.write_bytes(source_retrieval.read_bytes())
    source_binding = source_retrieval.with_suffix(".binding.json")
    _write(source_binding, {})
    return target_artifact, target_retrieval, source, {"source_run": source_run, "source_artifact": source_artifact}


@pytest.mark.parametrize("arm", ["copromem_v6_2_2_fixed", "copromem_v6_2_2_dynamic"])
def test_recovery_003_selects_immutable_arm_state_and_callback_shape(tmp_path, monkeypatch, arm):
    artifact, retrieval, source, paths = _copro_fixture(tmp_path, arm)
    monkeypatch.setattr(recovery, "_source_of", lambda _path: (
        paths["source_run"], paths["source_artifact"], source, source))
    observed = []

    def fake_validate(**kwargs):
        observed.append(kwargs["state"])
        return {"valid": True}

    monkeypatch.setattr(recovery, "validate_copro_binding", fake_validate)
    callback_calls = []

    def memory_for_instruction(instruction, domain, tool_meta):
        callback_calls.append((instruction, domain, tool_meta))
        return ""

    memory_for_instruction("instruction", "appworld", {})
    recovery._validate_carried_copromem(
        tmp_path / "run", {}, artifact, retrieval, state={"successor": True},
        registry={}, reproduce=lambda *_args: "",
    )
    assert observed == [{"container": "fixed", "entries": [1]} if arm == "copromem_v6_2_2_fixed"
                      else {"container": "dynamic", "entries": [2]}]
    assert len(callback_calls) == 1


@pytest.mark.skipif(os.name != "posix", reason="the immutable custody pointers are WSL-native")
def test_recovery_003_exact_configurator_is_zero_provider(tmp_path):
    run = Path("/mnt/e/Project/AAMAS/COPROMEM-review/artifacts/research/official_reme_copromem_pilot/v6_2_2_real_pilot_100_019_recovery")
    if not run.is_dir():
        pytest.skip("immutable 019 recovery is unavailable")
    recovery._configure(run)
    assert base.EXTRA_CARRIED_COPRO_VALIDATOR is recovery._validate_carried_copromem
    assert base.EXTRA_EXISTING_VALIDATOR is recovery._validate_carried_reasoningbank


def test_recovery_003_rejects_altered_or_missing_immutable_arm_state(tmp_path, monkeypatch):
    artifact, retrieval, source, paths = _copro_fixture(tmp_path, recovery.COPRO_FIXED_ARM)
    monkeypatch.setattr(recovery, "_source_of", lambda _path: (
        paths["source_run"], paths["source_artifact"], source, source))
    monkeypatch.setattr(recovery, "validate_copro_binding", lambda **_kwargs: {"valid": True})
    initial_path = paths["source_run"] / "copromem-dynamic-checkpoints" / "initial.json"
    initial = json.loads(initial_path.read_text(encoding="utf-8"))
    initial["fixed_initial_state"] = {"altered": True}
    _write(initial_path, initial)
    with pytest.raises(RecoveryImportError, match="source pre-state"):
        recovery._validate_carried_copromem(tmp_path, {}, artifact, retrieval,
                                            state={}, registry={}, reproduce=lambda *_args: "")


def test_legacy_reasoningbank_exception_is_frozen_protocol_only(tmp_path, monkeypatch):
    artifact, retrieval, source, _paths = _copro_fixture(tmp_path, recovery.parallel.REASONINGBANK_ARM)
    source_run = tmp_path / "rb-source"
    source_artifact = source_run / "artifact.json"
    _write(source_artifact, {"initial_prompt_messages_sha256": "prompt"})
    source_retrieval = source_run / "retrievals" / "task" / f"{recovery.parallel.REASONINGBANK_ARM}-1.json"
    _write(source_retrieval, {"legacy": True})
    target_retrieval = tmp_path / "retrievals" / "task" / f"{recovery.parallel.REASONINGBANK_ARM}-1.json"
    target_retrieval.parent.mkdir(parents=True, exist_ok=True)
    target_retrieval.write_bytes(source_retrieval.read_bytes())
    target = json.loads(artifact.read_text(encoding="utf-8"))
    target["initial_prompt_messages_sha256"] = "prompt"
    _write(artifact, target)
    monkeypatch.setattr(recovery, "_source_of", lambda _path: (
        source_run, source_artifact,
        {"initial_prompt_messages_sha256": "prompt"}, target))
    monkeypatch.setattr(recovery.parallel, "_runtime_factory", lambda *_args: {"initial_sha256": "bank"})
    monkeypatch.setattr(recovery.parallel, "verify", lambda **_kwargs: {"identity": "identity"})
    monkeypatch.setattr(recovery.parallel, "_identity", lambda *_args: "identity")
    monkeypatch.setattr(recovery, "_load", lambda path: {
        "protocol": recovery.LEGACY_UNSEALED_REASONINGBANK_PROTOCOL,
        "budget": {"hard_cap_usd": 1.0},
    }
                        if path.name == "manifest.json" else {})
    monkeypatch.setattr(recovery, "_SOURCE_REASONINGBANK_CONTEXTS", {})
    context = {"initial_sha256": "bank"}
    recovery._validate_carried_reasoningbank(context, tmp_path, {}, recovery.parallel.REASONINGBANK_ARM, "task", 1, 1, artifact, target)
    audit = json.loads((tmp_path / recovery.LEGACY_REASONINGBANK_AUDIT).read_text(encoding="utf-8"))
    assert audit["source_protocol"] == recovery.LEGACY_UNSEALED_REASONINGBANK_PROTOCOL
    assert audit["records"][0]["prompt_binding"] == "legacy_unsealed_predecessor_evidence"
    monkeypatch.setattr(recovery, "_load", lambda path: {
        "protocol": "other-protocol", "budget": {"hard_cap_usd": 1.0},
    }
                        if path.name == "manifest.json" else {})
    with pytest.raises(RecoveryImportError, match="legacy custody protocol"):
        recovery._validate_carried_reasoningbank(context, tmp_path, {}, recovery.parallel.REASONINGBANK_ARM, "task", 1, 1, artifact, target)