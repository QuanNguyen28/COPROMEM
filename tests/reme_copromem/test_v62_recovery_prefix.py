from __future__ import annotations

import pathlib

import pytest

from copromem.experiments.reme_copromem.evidence_contract import validate
from copromem.experiments.reme_copromem.recovery_import import RecoveryImportError, import_scored_artifact
from copromem.experiments.reme_copromem.v62_recovery_prefix import import_real_prefix, validate_real_prefix


ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT / "artifacts/research/official_reme_copromem_pilot/v6_2_task_conditioned_evaluation_004_recovery"
MANIFEST = "f93bbed7f2811fd736866d3d6ace3212e719007923e7cd5e672060aed24a803f"


@pytest.mark.skipif(not SOURCE.is_dir(), reason="immutable local recovery evidence is not available")
def test_real_twenty_artifact_prefix_is_ordered_normalized_and_idempotently_imported(tmp_path):
    rows = validate_real_prefix(source_run=SOURCE, expected_manifest_sha256=MANIFEST)
    assert len(rows) == len({row["trajectory_id"] for row in rows}) == 20
    assert sum("zero_action" in pathlib.Path(row["artifact_path"]).read_text(encoding="utf-8") for row in rows) == 1
    marker = import_real_prefix(target_run=tmp_path / "target", source_run=SOURCE,
                                expected_manifest_sha256=MANIFEST, successor_identity={"protocol": "shadow"},
                                recovery_bindings={"next_task": "09b0ee6_1"})
    assert marker["imported_count"] == 20
    assert import_real_prefix(target_run=tmp_path / "target", source_run=SOURCE,
                              expected_manifest_sha256=MANIFEST, successor_identity={"protocol": "shadow"},
                              recovery_bindings={"next_task": "09b0ee6_1"}) == marker


@pytest.mark.skipif(not SOURCE.is_dir(), reason="immutable local recovery evidence is not available")
def test_real_import_rejects_wrong_source_manifest(tmp_path):
    with pytest.raises(RecoveryImportError, match="manifest"):
        validate_real_prefix(source_run=SOURCE, expected_manifest_sha256="0" * 64)


@pytest.mark.skipif(not SOURCE.is_dir(), reason="immutable local recovery evidence is not available")
def test_real_zero_action_artifact_import_keeps_its_original_settlement_attestation(tmp_path):
    zero = next(row for row in validate_real_prefix(source_run=SOURCE, expected_manifest_sha256=MANIFEST)
                if "zero_action" in pathlib.Path(row["artifact_path"]).read_text(encoding="utf-8"))
    raw = __import__("json").loads(pathlib.Path(zero["artifact_path"]).read_text(encoding="utf-8"))
    if not pathlib.Path(raw["execution_evidence_path"]).is_file():
        pytest.skip("the immutable zero-action evidence uses its configured WSL path")
    target = tmp_path / "target" / "artifacts" / "zero.json"
    import_scored_artifact(source_artifact=pathlib.Path(zero["artifact_path"]), source_run=SOURCE,
                           target_artifact=target, target_run=tmp_path / "target",
                           source_manifest_sha256=str(zero["source_manifest_sha256"]))
    imported = __import__("json").loads(target.read_text(encoding="utf-8"))
    carried = imported["carried_completed_from"]
    assert carried["source_artifact_sha256"] == zero["artifact_sha256"]
    assert pathlib.Path(carried["source_artifact_path"]).is_file()
    validate(imported, run_root=tmp_path / "target")
