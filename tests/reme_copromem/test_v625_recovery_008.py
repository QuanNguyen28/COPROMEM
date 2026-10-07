"""Read-only admission checks for the E011 no-replay successor."""
from __future__ import annotations

from pathlib import Path
import pytest

SOURCE = Path("/mnt/e/Project/AAMAS/COPROMEM-review/artifacts/research/official_reme_copromem_pilot/v6_2_5_safe_terminal_slice_four_arm_overlay_011_recovery")

@pytest.mark.skipif(not SOURCE.is_dir(), reason="immutable E011 local evidence is unavailable")
def test_e011_admission_excludes_incomplete_batch_and_restores_last_complete_state():
    from scripts import run_v625_safe_terminal_slice_four_arm_overlay_recovery_008 as recovery
    admitted = recovery.source()
    assert len(admitted["prefix"]) == 65
    assert len(admitted["sidecar"]) == 4
    assert len(admitted["chains"]) == 18
    assert admitted["failure"]["task_id"] == "6b6ca61_2"
    assert admitted["remaining"][0] == "6f4b9a5_2"
    assert len(admitted["remaining"]) == 74
    assert admitted["state"]["semantic_state_sha256"] == "b82831ea66b300cac9eab899fc49a2e15af018501e72b88fc8398c3a6df80b19"
    assert admitted["failure"]["provider_calls_replayed"] is False
