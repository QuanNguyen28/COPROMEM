from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

SOURCE = Path("/mnt/e/Project/AAMAS/COPROMEM-review/artifacts/research/official_reme_copromem_pilot/v6_2_5_safe_terminal_slice_four_arm_overlay_012_recovery")
pytestmark = pytest.mark.skipif(not SOURCE.is_dir(), reason="requires immutable E012 evidence mounted at /mnt/e")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_e012_immutable_prefix_reconstructs_single_update_and_exact_300_grid():
    from scripts import run_v625_safe_terminal_slice_four_arm_overlay_recovery_009 as recovery

    watched = [SOURCE / "manifest.json", SOURCE / "ledger.jsonl",
               SOURCE / "copromem-dynamic-checkpoints/tasks/0005-8ce6779_1/pre-state.json"]
    watched.extend(sorted((SOURCE / "journals").glob("evaluation_copromem_v6_2_5_dynamic_8ce6779_1_trial_*.execution-evidence.jsonl")))
    before = {path: _sha(path) for path in watched}
    source = recovery.source()
    assert len(source["prefix"]) == 84
    assert len(source["remaining"]) == 72
    assert len(source["prefix"]) + 3 * len(source["remaining"]) == 300
    assert source["remaining"][:1] == ["9016950_1"]
    assert source["remaining"][-3:] == ["83a7951_3", "8749218_3", "8ce6779_3"]
    assert len(source["chains"]) == 22
    reconstruction = source["reconstructed_update"]
    assert reconstruction["task_id"] == "8ce6779_1"
    assert reconstruction["post_state_sha256"] == source["state"]["semantic_state_sha256"]
    assert reconstruction["legacy_pagination_reclassified_rows"]
    assert reconstruction["legacy_pagination_reclassified_rows"] == [1001, 1007, 5]
    assert before == {path: _sha(path) for path in watched}


