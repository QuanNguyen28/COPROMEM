from __future__ import annotations

import json

from copromem.experiments.reme_copromem.terminal_reconciliation import validate_terminal_run


def test_terminal_validator_collects_multiple_failures_without_mutation(tmp_path):
    manifest = {"evaluation": {"task_ids": ["t"], "seeds": [1], "expected_trajectories": 5}}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "manifest.sha256").write_text("wrong\n")
    output = validate_terminal_run(run_root=tmp_path, manifest=manifest,
        runtime_verify=lambda: (_ for _ in ()).throw(RuntimeError("runtime drift")),
        copro_reconcile=lambda: (_ for _ in ()).throw(RuntimeError("copro gap")),
        reme_dynamic_reconcile=lambda: {}, reme_fixed_reconcile=lambda: {},
        active_processes=lambda: True, historical_exposure=0.0)
    assert output["valid"] is False
    assert {item["gate"] for item in output["failures"]} >= {"manifest", "runtime_identity", "copromem_dynamic_prefix", "process_ownership"}
