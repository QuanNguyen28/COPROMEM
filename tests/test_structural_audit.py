from dataclasses import replace

import pytest

from copromem.checkpoints import canonical
from copromem.induction import HandoffEvidence
from copromem.structural_audit import audit_observability


def example(success, artifact):
    return HandoffEvidence(
        "task",
        str(success),
        "handoff",
        "{}",
        canonical(artifact),
        success,
        "build",
        "model",
    )


def test_semantic_differences_are_invisible_to_structural_features():
    report = audit_observability(
        [
            example(True, {"steps": [{"expr": "3+4"}]}),
            example(False, {"steps": [{"expr": "3*4"}, {"expr": "wrong"}]}),
        ]
    )
    assert report["identical_signature_pairs"] == 1
    assert report["potentially_separable_pairs"] == 0


def test_structural_difference_is_only_potential_separability():
    report = audit_observability(
        [
            example(True, {"steps": ["do"]}),
            example(False, {"steps": []}),
        ]
    )
    assert report["identical_signature_pairs"] == 0
    assert report["potentially_separable_pairs"] == 1
    assert "admitted" not in report


def test_audit_deduplicates_and_cannot_mix_models_or_read_heldout():
    positive, negative = example(True, {"steps": ["do"]}), example(False, {"steps": []})
    assert audit_observability([positive, positive, negative])["matched_pairs"] == 1
    assert (
        audit_observability([positive, replace(negative, execution_context="other")])[
            "matched_pairs"
        ]
        == 0
    )
    with pytest.raises(ValueError):
        audit_observability([replace(positive, partition="audit")])


def test_identical_artifact_with_opposite_outcome_is_explicit():
    report = audit_observability(
        [
            example(True, {"steps": ["do"]}),
            example(False, {"steps": ["do"]}),
        ]
    )
    assert report["identical_artifact_pairs"] == 1
