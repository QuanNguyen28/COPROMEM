from __future__ import annotations

import json
import os

import pytest


def test_two_arm_budget_registers_no_reme_roles():
    from copromem.experiments.reme_copromem.runner import v5_budget_bound
    bound = v5_budget_bound(call_limits={"executor": 240, "reme_lifecycle": 0,
                                         "reme_embedding": 0, "copromem_decomposition": 0},
                            historical_usd=0.168808788)
    assert bound["all_in_usd"] < 100.0
    assert bound["reme_lifecycle_calls"] == bound["embedding_calls"] == 0


def test_flat_public_descriptor_is_valid_and_unknown_on_empty_bank():
    from copromem.benchmarks.appworld.adapter import CoProMemAppWorldAdapter
    from copromem.learning import ActionObservation, LearningCore
    from scripts.reme_copromem.prepare_task_boundary_v6 import FLAT_SPOTIFY_DESCRIPTOR
    events = tuple(ActionObservation(**item) for item in FLAT_SPOTIFY_DESCRIPTOR)
    assert LearningCore.signature(events)
    assert CoProMemAppWorldAdapter(api_key="").module.learning.retrieve("appworld", events).compatibility == "unknown"


def test_task_boundary_module_does_not_initialize_reme(monkeypatch, tmp_path):
    monkeypatch.setenv("COPROMEM_RUN_DIR", str(tmp_path))
    monkeypatch.delenv("COPROMEM_REME_SERVICE_STARTED", raising=False)
    import importlib
    import copromem.experiments.reme_copromem.task_boundary_v6 as module
    module = importlib.reload(module)
    assert module.RUN == tmp_path
    assert "ReMeService" not in module.__dict__


def test_duplicate_lock_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("COPROMEM_RUN_DIR", str(tmp_path))
    import importlib
    import copromem.experiments.reme_copromem.task_boundary_v6 as module
    module = importlib.reload(module)
    module.MANIFEST_SHA.parent.mkdir(parents=True, exist_ok=True)
    module.MANIFEST_SHA.write_text("hash\n")
    module._lock()
    with pytest.raises(RuntimeError):
        module._lock()
