"""Offline checks for the minimal maintained review package."""
from __future__ import annotations

import json
import pathlib

import pytest

from copromem.appworld_acquisition_gate import AcquisitionJournal as LegacyJournal
from copromem.appworld_comparison_adapter import CoProMemAppWorldAdapter as LegacyAdapter
from copromem.benchmarks.appworld.acquisition import AcquisitionJournal
from copromem.benchmarks.appworld.adapter import CoProMemAppWorldAdapter
from copromem.benchmarks.appworld import worker
from copromem.experiments.reme_copromem import config
from copromem.integrations.reme import upstream_executor


def test_only_retained_compatibility_shims_reexport_canonical_objects() -> None:
    assert LegacyJournal is AcquisitionJournal
    assert LegacyAdapter is CoProMemAppWorldAdapter


def test_reme_executor_uses_reviewed_native_worker() -> None:
    assert upstream_executor.WORKER.name == "worker.py"
    assert upstream_executor.WORKER.is_file()
    assert worker.main.__module__ == "copromem.benchmarks.appworld.worker"


def test_runner_requires_explicit_frozen_acquisition_export(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.delenv("COPROMEM_ACQUISITION_POOL", raising=False)
    with pytest.raises(RuntimeError, match="COPROMEM_ACQUISITION_POOL"):
        config.frozen_acquisition_pool()
    path = tmp_path / "acquisition.json"
    path.write_text(json.dumps([{"acquisition_identity": "a", "task_id": "task", "history": [], "after_score": 0.0}]), encoding="utf-8")
    monkeypatch.setenv("COPROMEM_ACQUISITION_POOL", str(path))
    assert config.frozen_acquisition_pool()[0]["acquisition_identity"] == "a"
