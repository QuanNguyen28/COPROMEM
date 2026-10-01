from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def _runner():
    path = Path(__file__).parents[2] / "scripts" / "run_reasoningbank_appworld_engineering.py"
    spec = importlib.util.spec_from_file_location("reasoningbank_runtime_runner", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def _manifest(runner):
    value = {"git_commit": "a" * 40, "protocol_sha256": "b" * 64, "registry_sha256": "c" * 64,
             "initial_bank_sha256": "d" * 64, "execution": {"model": "fixture"},
             "embedding": {"model": "fixture"}, "allocation": {"frozen": True}}
    value["runtime_identity_version"] = runner.RUNTIME_IDENTITY_VERSION
    value["runtime_identity_sha256"] = runner._runtime_identity_digest(value)
    return value


def test_runtime_identity_is_manifest_derived_persisted_and_restart_stable(tmp_path):
    runner = _runner(); manifest = _manifest(runner); run = tmp_path / "run"; run.mkdir()
    (run / "manifest.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    first = runner._runtime_identity(run, manifest)
    assert len(first) == 64 and (run / "runtime-identity.json").is_file()
    assert runner._runtime_identity(run, manifest) == first
    record = json.loads((run / "runtime-identity.json").read_text(encoding="utf-8"))
    assert record["runtime_identity_sha256"] == manifest["runtime_identity_sha256"]
    assert record["material"]["executable_commit"] == manifest["git_commit"]


def test_missing_or_changed_manifest_runtime_identity_fails_before_dispatch(tmp_path):
    runner = _runner(); manifest = _manifest(runner); run = tmp_path / "run"; run.mkdir()
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    missing = dict(manifest); missing.pop("runtime_identity_sha256")
    with pytest.raises(RuntimeError, match="runtime-content identity"):
        runner._runtime_identity(run, missing)
    runner._runtime_identity(run, manifest)
    changed = dict(manifest); changed["runtime_identity_sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="runtime-content identity"):
        runner._runtime_identity(run, changed)


def test_production_runner_passes_frozen_runtime_identity_to_all_reasoningbank_arms():
    path = Path(__file__).parents[2] / "scripts" / "run_reasoningbank_appworld_engineering.py"
    source = path.read_text(encoding="utf-8")
    assert "runtime_identity_sha256 = _runtime_identity(run, manifest)" in source
    assert '"runtime_identity_sha256": runtime_identity_sha256' in source
    assert "for arm in ARMS" in source and "execute_trajectory(" in source


def test_production_runner_constructs_one_complete_identity_for_retrieval_and_prompt_seal():
    path = Path(__file__).parents[2] / "scripts" / "run_reasoningbank_appworld_engineering.py"
    source = path.read_text(encoding="utf-8")
    start = source.index("def _retrieval_identity(")
    boundary = source[start:source.index("def _reconcile_execution_prefix(", start)]
    for field in ("trajectory_id", "task_id", "arm", "trial_id", "seed", "benchmark",
                  "manifest_sha256", "runtime_identity_sha256", "registry_sha256"):
        assert f'"{field}"' in boundary
    assert "MappingProxyType(canonical_identity(" in boundary
    assert "runtime.retrieval_callback(retrieval_path, identity=identity)" in source
    assert "runtime.prompt_binding_callback(retrieval_path, identity=identity)" in source
    assert "_retrieval_identity(manifest, run, arm, task, trial, seed)" in source


def test_frozen_production_identity_has_nonempty_hashes_and_cannot_mutate(tmp_path):
    runner = _runner(); manifest = _manifest(runner); run = tmp_path / "run"; run.mkdir()
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    identity = runner._retrieval_identity(manifest, run, "reasoningbank_dynamic", "task_1", 1, 9701)
    assert identity["manifest_sha256"] == runner.file_sha(run / "manifest.json")
    assert identity["runtime_identity_sha256"] == manifest["runtime_identity_sha256"]
    assert identity["registry_sha256"] == manifest["registry_sha256"]
    with pytest.raises(TypeError):
        identity["manifest_sha256"] = "0" * 64


def test_execution_boundary_rejects_a_missing_or_mismatched_runtime_identity_before_agent_load():
    path = Path(__file__).parents[2] / "src" / "copromem" / "experiments" / "reme_copromem" / "runner.py"
    source = path.read_text(encoding="utf-8")
    boundary = source[source.index("def execute_trajectory"):]
    assert "execution evidence runtime identity is absent or differs from its frozen record" in source
    assert boundary.index("execution evidence runtime identity") < boundary.index("load_official_agent")
    assert "result[\"runtime_identity_sha256\"] = runtime_identity_sha256" in source
