from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

SOURCE = Path("/mnt/e/Project/AAMAS/COPROMEM-review/artifacts/research/official_reme_copromem_pilot/v6_2_5_safe_terminal_slice_four_arm_overlay_013_recovery")
pytestmark = pytest.mark.skipif(not SOURCE.is_dir(), reason="requires immutable E013 evidence mounted at /mnt/e")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_e013_scored_batch_reconstructs_mixed_prefix_spine_update_without_replay():
    from scripts import run_v625_safe_terminal_slice_four_arm_overlay_recovery_010 as recovery

    watched = [SOURCE / "manifest.json", SOURCE / "ledger.jsonl", SOURCE / "recovery-custody.json",
               SOURCE / "copromem-dynamic-checkpoints/tasks/0001-9016950_1/pre-state.json"]
    watched.extend(sorted((SOURCE / "artifacts/9016950_1/copromem_v6_2_5_dynamic").glob("trial-*.json")))
    watched.extend(sorted((SOURCE / "journals").glob("evaluation_copromem_v6_2_5_dynamic_9016950_1_trial_*.execution-evidence.jsonl")))
    before = {path: _sha(path) for path in watched}
    source = recovery.source()
    assert len(source["prefix"]) == 87
    assert len(source["remaining"]) == 71
    assert len(source["prefix"]) + 3 * len(source["remaining"]) == 300
    assert source["remaining"][:1] == ["90adc3f_1"]
    assert source["reconstructed_update"]["task_id"] == "9016950_1"
    assert source["reconstructed_update"]["validator_compatibility"] == "v622_spine_with_legacy_v61_prefix"
    assert source["reconstructed_update"]["post_state_sha256"] == source["state"]["semantic_state_sha256"]
    assert before == {path: _sha(path) for path in watched}