"""Read-only admission checks for the E010 no-replay successor."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.mark.skipif(
    not Path("/mnt/e/Project/AAMAS/COPROMEM-review/artifacts/research/official_reme_copromem_pilot/v6_2_5_safe_terminal_slice_four_arm_overlay_010_recovery").is_dir(),
    reason="immutable E010 local evidence is unavailable",
)
def test_e010_admission_excludes_only_interrupted_task_and_persists_identity_binding(tmp_path):
    from scripts import run_v625_safe_terminal_slice_four_arm_overlay_recovery_007 as recovery

    source = recovery.source()
    assert source["remaining"][0] == "3d9a636_2"
    assert len(source["remaining"]) == 83
    assert len(source["prefix"]) == 41
    assert len(source["sidecar"]) == 2
    assert len(source["chains"]) == 10
    assert source["failure"]["task_id"] == "3b8fb7a_2"
    assert source["failure"]["settled_executor_reservations"] == 10
    assert source["failure"]["provider_calls_replayed"] is False

    run = tmp_path / "successor"
    recovery.prepare(run)
    custody = json.loads((run / recovery.CUSTODY).read_text(encoding="utf-8"))
    binding = json.loads((run / "runtime-identity.binding.json").read_text(encoding="utf-8"))
    runtime = json.loads((run / "runtime-identity.json").read_text(encoding="utf-8"))
    assert custody["next_task_id"] == "3d9a636_2"
    assert custody["remaining_task_count"] == 83
    assert custody["composite_expected_scored_trajectories"] == 292
    assert binding["runtime_identity_sha256"] == runtime["runtime_identity_sha256"]
    assert binding["runtime_identity_record_sha256"] == recovery.sha(run / "runtime-identity.json")
    assert recovery.verify(run)["remaining"][0] == "3d9a636_2"
