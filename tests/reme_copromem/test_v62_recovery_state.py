from __future__ import annotations

import json
import pathlib

import pytest

from copromem.experiments.reme_copromem.recovery_import import RecoveryImportError
from copromem.experiments.reme_copromem.v62_recovery_prefix import import_real_prefix
from copromem.experiments.reme_copromem.v62_recovery_state import assemble, load_published, publish
from copromem.experiments.reme_copromem.v62_recovery_start import RecoveryStartError, admit


ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT / "artifacts/research/official_reme_copromem_pilot/v6_2_task_conditioned_evaluation_004_recovery"
FORENSIC = ROOT / "research/reme_copromem_fixed_dynamic_review/v6_2_evaluation_004_keyerror_forensic.json"
MANIFEST = "f93bbed7f2811fd736866d3d6ace3212e719007923e7cd5e672060aed24a803f"


def _import_and_assemble(tmp_path: pathlib.Path):
    target = tmp_path / "import"
    import_real_prefix(target_run=target, source_run=SOURCE, expected_manifest_sha256=MANIFEST,
                       successor_identity={"protocol": "zero-provider-shadow"}, recovery_bindings={})
    state = assemble(imported_root=target, source_run=SOURCE, forensic_json=FORENSIC,
                     successor_identity={"protocol": "zero-provider-shadow"}, historical_exposure=2.435839694)
    return target, state


@pytest.mark.skipif(not SOURCE.is_dir(), reason="immutable local recovery evidence is not available")
def test_real_prefix_assembles_complete_restart_state_and_publishes_idempotently(tmp_path):
    target, state = _import_and_assemble(tmp_path)
    # The importer computes this from the complete, ordered real envelope
    # inventory.  It is intentionally asserted against the import marker,
    # not a host-path-dependent presentation of source filenames.
    assert state["prefix_inventory_sha256"] == json.loads((target / "recovery-import-spec.json").read_text())["inventory_sha256"]
    assert state["progress"]["completed"] == state["progress"]["imported_completed"] == 20
    assert state["progress"]["newly_completed"] == 0
    assert all(row["completed"] == 4 for row in state["progress"]["per_arm"].values())
    assert state["copromem_dynamic"]["task1_committed"]["semantic_post_state_sha256"] == state["copromem_dynamic"]["task2_rejected_nonmutating"]["semantic_post_state_sha256"]
    assert state["copromem_dynamic"]["task2_rejected_nonmutating"]["candidate_schema"]["retrieval_visible"] is False
    assert len(state["reme_dynamic"]["updates"]) == 4
    assert state["next"] == {"task_id": "09b0ee6_1", "arm": "no_memory", "trial_id": 1, "seed": 11001}
    assert publish(root=target, state=state) == state
    assert publish(root=target, state=state) == state
    assert load_published(target) == state
    admitted = admit(marker_root=target, expected_source_identity={"protocol": "zero-provider-shadow"},
                     expected_manifest_sha256=MANIFEST)
    assert admitted.next == {"task_id": "09b0ee6_1", "arm": "no_memory", "trial_id": 1, "seed": 11001}
    assert admitted.imported_completed == 20


@pytest.mark.skipif(not SOURCE.is_dir(), reason="immutable local recovery evidence is not available")
def test_recovery_state_rejects_tampered_forensic_semantic_state(tmp_path):
    target, _state = _import_and_assemble(tmp_path)
    forensic = json.loads(FORENSIC.read_text(encoding="utf-8"))
    forensic["copromem_dynamic"]["offline_reconstruction"]["semantic_post_state"]["sha256"] = "0" * 64
    altered = tmp_path / "forensic.json"
    altered.write_text(json.dumps(forensic), encoding="utf-8")
    with pytest.raises(RecoveryImportError, match="mutated semantic state"):
        assemble(imported_root=target, source_run=SOURCE, forensic_json=altered,
                 successor_identity={"protocol": "zero-provider-shadow"}, historical_exposure=2.435839694)


@pytest.mark.skipif(not SOURCE.is_dir(), reason="immutable local recovery evidence is not available")
def test_recovery_start_rejects_source_identity_drift_before_a_runner_lock(tmp_path):
    target, state = _import_and_assemble(tmp_path)
    publish(root=target, state=state)
    with pytest.raises(RecoveryStartError, match="source identity drift"):
        admit(marker_root=target, expected_source_identity={"protocol": "different"},
              expected_manifest_sha256=MANIFEST)
