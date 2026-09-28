from __future__ import annotations

import importlib


def test_task_boundary_runner_reads_exported_credential_without_env_file(monkeypatch, tmp_path):
    monkeypatch.setenv("COPROMEM_RUN_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "fixture-process-only")
    module = importlib.import_module("copromem.experiments.reme_copromem.task_boundary_v6")
    assert module._env("OPENROUTER_API_KEY") == "fixture-process-only"
