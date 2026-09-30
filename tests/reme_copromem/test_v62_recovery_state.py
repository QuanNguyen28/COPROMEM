from __future__ import annotations

import json
import pathlib

import pytest

from copromem.experiments.reme_copromem.recovery_import import RecoveryImportError
from copromem.experiments.reme_copromem.v62_recovery_prefix import import_real_prefix
from copromem.experiments.reme_copromem.v62_recovery_state import (assemble, load_published, publish,
                                                                    validate_published_custody)
from copromem.experiments.reme_copromem.v62_recovery_start import RecoveryStartError, admit
from copromem.experiments.reme_copromem.v62_recovery_custody import build_mapping, validate_mapping
from copromem.experiments.reme_copromem.recovery_import import canonical_sha256


ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT / "artifacts/research/official_reme_copromem_pilot/v6_2_task_conditioned_evaluation_004_recovery"
FORENSIC = ROOT / "research/reme_copromem_fixed_dynamic_review/v6_2_evaluation_004_keyerror_forensic.json"
MANIFEST = "f93bbed7f2811fd736866d3d6ace3212e719007923e7cd5e672060aed24a803f"


def _import_and_assemble(tmp_path: pathlib.Path):
    target = tmp_path / "import"
    import_real_prefix(target_run=target, source_run=SOURCE, expected_manifest_sha256=MANIFEST,
                       successor_identity={"protocol": "shadow"}, recovery_bindings={"next_task": "09b0ee6_1"})
    state = assemble(imported_root=target, source_run=SOURCE, forensic_json=FORENSIC,
                     successor_identity={"protocol": "shadow"}, historical_exposure=2.435839694)
    return target, state


@pytest.mark.skipif(not SOURCE.is_dir(), reason="immutable local recovery evidence is not available")
def test_real_prefix_assembles_complete_restart_state_and_publishes_idempotently(tmp_path):
    target, state = _import_and_assemble(tmp_path)
    assert state["source_prefix_inventory_sha256"] == "c40daeba9baf334f073125a52f4aec5ff59bd86181e346983bd0f8250f33b122"
    assert state["successor_envelope_inventory_sha256"] == "d1b26a6e0e497deaf9660d000e737893f6a666b60fe68d38db7375b6542d32be"
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
    admitted = admit(marker_root=target, expected_source_identity={"protocol": "shadow"},
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
                 successor_identity={"protocol": "shadow"}, historical_exposure=2.435839694)


@pytest.mark.skipif(not SOURCE.is_dir(), reason="immutable local recovery evidence is not available")
def test_recovery_start_rejects_source_identity_drift_before_a_runner_lock(tmp_path):
    target, state = _import_and_assemble(tmp_path)
    publish(root=target, state=state)
    with pytest.raises(RecoveryStartError, match="source identity drift"):
        admit(marker_root=target, expected_source_identity={"protocol": "different"},
              expected_manifest_sha256=MANIFEST)


@pytest.mark.skipif(not SOURCE.is_dir(), reason="immutable local recovery evidence is not available")
def test_dual_domain_custody_mapping_reproduces_legacy_hashes_and_rejects_tampering(tmp_path):
    target, _state = _import_and_assemble(tmp_path)
    mapping = build_mapping(source_run=SOURCE, expected_manifest_sha256=MANIFEST, imported_root=target,
                            expected_source_inventory_sha256="c40daeba9baf334f073125a52f4aec5ff59bd86181e346983bd0f8250f33b122",
                            expected_envelope_inventory_sha256="d1b26a6e0e497deaf9660d000e737893f6a666b60fe68d38db7375b6542d32be")
    assert len(mapping["entries"]) == 20
    assert validate_mapping(mapping) == mapping
    altered = json.loads(json.dumps(mapping))
    altered["entries"][0]["journal_sha256"] = "0" * 64
    with pytest.raises(RecoveryImportError, match="content identity"):
        validate_mapping(altered)


@pytest.mark.skipif(not SOURCE.is_dir(), reason="immutable local recovery evidence is not available")
def test_read_only_admission_rebuilds_custody_mapping_against_immutable_sources(tmp_path):
    target, state = _import_and_assemble(tmp_path)
    publish(root=target, state=state)
    marker = target / "recovery-state.json"
    altered = json.loads(marker.read_text())
    altered["custody_mapping"]["entries"][0]["history_sha256"] = "0" * 64
    altered["custody_mapping"]["custody_mapping_sha256"] = canonical_sha256(
        {key: value for key, value in altered["custody_mapping"].items() if key != "custody_mapping_sha256"}
    )
    altered["custody_mapping_sha256"] = altered["custody_mapping"]["custody_mapping_sha256"]
    altered["recovery_state_sha256"] = canonical_sha256(
        {key: value for key, value in altered.items() if key != "recovery_state_sha256"}
    )
    marker.write_text(json.dumps(altered, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    # Self-hashes alone are insufficient: the admission path must reconstruct
    # source/envelope custody without starting a service or runner.
    loaded = load_published(target)
    with pytest.raises(RecoveryImportError, match="diverges from immutable evidence"):
        validate_published_custody(target, loaded)


def _write_marker(path: pathlib.Path, marker: dict) -> None:
    marker["inventory_sha256"] = canonical_sha256(marker["records"])
    marker["marker_sha256"] = canonical_sha256({key: value for key, value in marker.items() if key != "marker_sha256"})
    path.write_text(json.dumps(marker, sort_keys=True, separators=(",", ":")), encoding="utf-8")


@pytest.mark.skipif(not SOURCE.is_dir(), reason="immutable local recovery evidence is not available")
@pytest.mark.parametrize("case", [
    "reordered", "duplicate", "missing", "artifact_binding", "history_binding",
    "journal_binding", "scorer_binding", "envelope_metadata", "domain_confusion",
])
def test_dual_domain_mapping_fails_closed_on_custody_tampering(tmp_path, case):
    target, _state = _import_and_assemble(tmp_path)
    if case == "reordered":
        marker_path = target / "recovery_import_complete.json"
        marker = json.loads(marker_path.read_text())
        marker["records"][0], marker["records"][1] = marker["records"][1], marker["records"][0]
        _write_marker(marker_path, marker)
    elif case == "duplicate":
        marker_path = target / "recovery_import_complete.json"
        marker = json.loads(marker_path.read_text())
        marker["records"][1] = dict(marker["records"][0])
        _write_marker(marker_path, marker)
    elif case == "missing":
        (target / "import-envelopes" / "0001.json").unlink()
    elif case in {"artifact_binding", "history_binding", "journal_binding", "scorer_binding", "envelope_metadata"}:
        path = target / "import-envelopes" / "0001.json"
        envelope = json.loads(path.read_text())
        field = {
            "artifact_binding": "artifact_sha256",
            "history_binding": "history_sha256",
            "journal_binding": "journal_sha256",
            "scorer_binding": "normalized_scorer_sha256",
            "envelope_metadata": "source_runtime_sha256",
        }[case]
        # The atomic import marker is rebuilt consistently here.  The only
        # remaining mismatch is between the altered successor envelope and
        # immutable source inventory, which must fail closed.
        envelope["source"][field] = "0" * 64
        envelope["envelope_sha256"] = canonical_sha256({key: value for key, value in envelope.items() if key != "envelope_sha256"})
        path.write_text(json.dumps(envelope, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        marker_path = target / "recovery_import_complete.json"
        marker = json.loads(marker_path.read_text())
        marker["records"][0]["envelope_sha256"] = envelope["envelope_sha256"]
        _write_marker(marker_path, marker)
    else:
        with pytest.raises(RecoveryImportError, match="declared domain"):
            build_mapping(source_run=SOURCE, expected_manifest_sha256=MANIFEST, imported_root=target,
                          expected_source_inventory_sha256="d1b26a6e0e497deaf9660d000e737893f6a666b60fe68d38db7375b6542d32be",
                          expected_envelope_inventory_sha256="c40daeba9baf334f073125a52f4aec5ff59bd86181e346983bd0f8250f33b122")
        return
    with pytest.raises(RecoveryImportError):
        build_mapping(source_run=SOURCE, expected_manifest_sha256=MANIFEST, imported_root=target,
                      expected_source_inventory_sha256="c40daeba9baf334f073125a52f4aec5ff59bd86181e346983bd0f8250f33b122",
                      expected_envelope_inventory_sha256="d1b26a6e0e497deaf9660d000e737893f6a666b60fe68d38db7375b6542d32be")
