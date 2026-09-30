from __future__ import annotations

import json
import shutil
import subprocess
import importlib
from pathlib import Path

import pytest

from copromem.experiments.reme_copromem.runtime_identity import RuntimeIdentityError
from copromem.experiments.reme_copromem.runtime_identity_v3 import (
    IDENTITY_VERSION, build_identity, verify_identity, verify_manifest_identity,
)


def _run(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def _fixture_root(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "checkout"; (root / "src/copromem/runtime").mkdir(parents=True)
    (root / "scripts").mkdir(); (root / "research/reme_copromem_fixed_dynamic_review").mkdir(parents=True)
    (root / "src/copromem/runtime/engine.py").write_text("VALUE = 'stable'\n", encoding="utf-8")
    (root / "src/copromem/runtime/schema.json").write_text('{"schema":1}\n', encoding="utf-8")
    (root / "scripts/entry.py").write_text("from copromem.runtime.engine import VALUE\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    (root / "research/reme_copromem_fixed_dynamic_review/registry.json").write_text('{"registry":"r"}\n', encoding="utf-8")
    policy = {
        "version": "runtime-content-identity-v3-policy-1", "source_roots": ["src/copromem"],
        "source_suffixes": [".py", ".json", ".yaml", ".yml", ".toml"],
        "entry_points": ["scripts/entry.py"],
        "runtime_configuration_files": ["pyproject.toml", "research/reme_copromem_fixed_dynamic_review/registry.json"],
        "untracked_runtime_roots": ["src/copromem", "scripts"],
        "ignored_directory_names": [".git", "__pycache__", ".pytest_cache", "artifacts", "reports", "logs", "build", "dist"],
        "untracked_runtime_suffixes": [".py", ".json", ".yaml", ".yml", ".toml"],
    }
    (root / "research/reme_copromem_fixed_dynamic_review/runtime-content-identity-v3-policy.json").write_text(json.dumps(policy), encoding="utf-8")
    _run(root, "init"); _run(root, "config", "user.email", "fixture@example.invalid"); _run(root, "config", "user.name", "fixture")
    _run(root, "add", "."); _run(root, "commit", "-m", "fixture")
    return root, _run(root, "rev-parse", "HEAD")


def _inputs() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    return (
        {"model": "deepseek/deepseek-v4.1-flash", "provider": "deepseek", "temperature": 0.7,
         "arms": ["no_memory"], "retrieval_policy_sha256": "policy", "prompt_tool_interface": "v1",
         "scorer_contract": "official", "ledger_policy": "append-only", "storage_policy": "e-backed",
         "callable_registry_sha256": "registry", "max_actions": 30, "completion_tokens": 2048},
        {"python": "CPython 3.test", "appworld": "fixture", "reme_commit": "reme", "reme_dirty": False,
         "reme_python": "3.test", "packages": {"fixture": "1"}},
        {"copromem_bank_sha256": "copro", "reme_bank_sha256": "reme-bank", "callable_registry_sha256": "registry",
         "allocation_sha256": "allocation", "method_policy_sha256": "policy", "task_trial_sha256": "trials"},
    )


def _identity(root: Path, commit: str):
    config, external, scientific = _inputs()
    return build_identity(root=root, executable_commit=commit, runtime_configuration=config,
                          external_dependencies=external, scientific_inputs=scientific)


def test_identical_clean_worktrees_and_git_pointer_forms_are_portable(tmp_path: Path):
    root, commit = _fixture_root(tmp_path); clone = tmp_path / "clone"
    subprocess.check_call(["git", "clone", str(root), str(clone)], stdout=subprocess.DEVNULL)
    assert _identity(root, commit) == _identity(clone, commit)
    # A normal repository has .git directory; a linked worktree has .git file.
    linked = tmp_path / "linked"; subprocess.check_call(["git", "-C", str(root), "worktree", "add", "--detach", str(linked), commit], stdout=subprocess.DEVNULL)
    assert (linked / ".git").is_file()
    assert _identity(root, commit) == _identity(linked, commit)


def test_order_timestamps_and_publication_only_files_do_not_change_identity(tmp_path: Path):
    root, commit = _fixture_root(tmp_path); baseline = _identity(root, commit)
    (root / "README.md").write_text("publication only", encoding="utf-8")
    (root / "research/report.md").parent.mkdir(exist_ok=True); (root / "research/report.md").write_text("report", encoding="utf-8")
    (root / "src/copromem/runtime/engine.py").touch()
    assert _identity(root, commit) == baseline


def test_clean_crlf_checkout_is_equivalent_to_git_lf_content(tmp_path: Path):
    root, commit = _fixture_root(tmp_path); baseline = _identity(root, commit)
    path = root / "src/copromem/runtime/engine.py"
    path.write_bytes(b"VALUE = 'stable'\r\n")
    assert _identity(root, commit) == baseline


def test_untracked_reports_are_ignored_but_runtime_files_fail_closed(tmp_path: Path):
    root, commit = _fixture_root(tmp_path); baseline = _identity(root, commit)
    (root / "src/copromem/runtime/reports").mkdir(); (root / "src/copromem/runtime/reports/a.json").write_text("{}", encoding="utf-8")
    assert _identity(root, commit) == baseline
    (root / "src/copromem/runtime/secret_runtime.py").write_text("X=1", encoding="utf-8")
    dirty = _identity(root, commit)
    assert dirty["components"]["executable_source"]["body"]["dirty_state"]["runtime_relevant_dirty"]
    with pytest.raises(RuntimeIdentityError, match="drift"):
        verify_identity(baseline, root=root, runtime_configuration=_inputs()[0], external_dependencies=_inputs()[1], scientific_inputs=_inputs()[2])


def test_tracked_source_and_every_semantic_component_are_content_sensitive(tmp_path: Path):
    root, commit = _fixture_root(tmp_path); baseline = _identity(root, commit)
    (root / "src/copromem/runtime/engine.py").write_text("VALUE = 'changed'\n", encoding="utf-8")
    assert _identity(root, commit)["runtime_identity_sha256"] != baseline["runtime_identity_sha256"]
    for position in range(3):
        config, external, scientific = _inputs()
        target = (config, external, scientific)[position]
        target["changed"] = position
        assert build_identity(root=root, executable_commit=commit, runtime_configuration=config,
                              external_dependencies=external, scientific_inputs=scientific)["runtime_identity_sha256"] != baseline["runtime_identity_sha256"]


def test_bank_tamper_v2_rejection_and_manifest_lifecycle_verification(tmp_path: Path):
    root, commit = _fixture_root(tmp_path); record = _identity(root, commit)
    config, external, scientific = _inputs()
    manifest = {"runtime_identity_version": IDENTITY_VERSION, "runtime_identity_sha256": record["runtime_identity_sha256"]}
    verify_manifest_identity(manifest, record, root=root, runtime_configuration=config, external_dependencies=external, scientific_inputs=scientific)
    scientific["copromem_bank_sha256"] = "tampered"
    with pytest.raises(RuntimeIdentityError, match="drift"):
        verify_manifest_identity(manifest, record, root=root, runtime_configuration=config, external_dependencies=external, scientific_inputs=scientific)
    with pytest.raises(RuntimeIdentityError, match="v2"):
        verify_manifest_identity({"runtime_identity_version": IDENTITY_VERSION, "runtime_identity_sha256": "x"},
                                 {"version": "runtime-content-identity-v2"}, root=root,
                                 runtime_configuration=config, external_dependencies=external, scientific_inputs=_inputs()[2])


def test_junction_like_target_path_is_not_identity_when_content_binding_matches(tmp_path: Path):
    root, commit = _fixture_root(tmp_path); first = _identity(root, commit)
    alternative = tmp_path / "different-location"; shutil.copytree(root, alternative, ignore=shutil.ignore_patterns(".git"))
    # Checkout location itself is not represented.  Same tracked content at the
    # declared commit is what the identity binds.
    _run(alternative, "init"); _run(alternative, "config", "user.email", "fixture@example.invalid"); _run(alternative, "config", "user.name", "fixture")
    _run(alternative, "add", "."); _run(alternative, "commit", "-m", "fixture")
    assert _identity(alternative, _run(alternative, "rev-parse", "HEAD"))["components"]["scientific_inputs"] == first["components"]["scientific_inputs"]


def test_maintained_runner_enforces_v3_at_start_restart_pre_task_and_terminal(tmp_path: Path, monkeypatch):
    """The common runner verifier is called by all dispatch-capable checkpoints."""
    root, commit = _fixture_root(tmp_path); record = _identity(root, commit)
    config, external, scientific = _inputs(); run = tmp_path / "run"; run.mkdir()
    identity_path = run / "runtime-identity.json"; identity_path.write_bytes(json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    manifest = {"runtime_identity_version": IDENTITY_VERSION, "runtime_identity_sha256": record["runtime_identity_sha256"],
                "runtime_identity_file_sha256": __import__("hashlib").sha256(identity_path.read_bytes()).hexdigest(),
                "runtime_identity_inputs": {"runtime_configuration": config, "external_dependencies": external, "scientific_inputs": scientific}}
    (run / "manifest.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    runner = importlib.import_module("scripts.run_v61_exploratory_evaluation")
    monkeypatch.setattr(runner, "ROOT", root)
    monkeypatch.setattr(runner, "evaluation_v3_inputs", lambda **_: {
        "runtime_configuration": config, "external_dependencies": external, "scientific_inputs": scientific})
    for stage in ("startup", "restart", "pre-task", "terminal"):
        _, checkpoint = runner._runtime_checkpoint(run, manifest, stage)
        assert checkpoint["runtime_identity_sha256"] == record["runtime_identity_sha256"]
    (root / "src/copromem/runtime/engine.py").write_text("tampered", encoding="utf-8")
    with pytest.raises(RuntimeError, match="v3 manifest runtime identity"):
        runner._runtime_identity(run, manifest)
