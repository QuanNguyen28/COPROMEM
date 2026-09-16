import pytest

from copromem.checkpoints import IntegrityError
from copromem.intervention_audit import audit_report, summarize_intervention
from copromem.paired_gsm8k import PairedConfig


def row(task, correct, recovered=False):
    return {
        "id": task,
        "replicate": 0,
        "checkpoint_id": task,
        "correct": correct,
        "recovered": recovered,
        "initial_plan_valid": False,
        "solver_request_id": task + str(recovered),
        "failure": None,
        "calls": 2 if recovered else 1,
        "logical_usage": [{"usd": 0.02 if recovered else 0.01}],
    }


def test_violation_and_failure_prediction_are_not_repair_benefit():
    original = [row(str(i), True) for i in range(4)]
    revised = [row(str(i), i != 0, True) for i in range(4)]
    report = summarize_intervention(original, revised, PairedConfig())
    assert report["schema_failure_prediction_precision"] == 0
    assert report["observed_repair_harm_rate_when_activated"] == 0.25
    assert not report["meets_minimal_descriptive_benefit_gate"]


def test_true_observed_benefit_is_reported_without_claiming_generalization():
    original = [row(str(i), i != 0) for i in range(4)]
    revised = [row(str(i), True, True) for i in range(4)]
    report = summarize_intervention(original, revised, PairedConfig())
    assert report["paired"]["beneficial_flips"] == 1
    assert report["meets_minimal_descriptive_benefit_gate"]
    assert "No learned policy" in report["limitations"]


def test_same_solver_must_have_same_score_and_failures_cannot_be_hidden():
    with pytest.raises(IntegrityError):
        summarize_intervention([row("a", True)], [row("a", False)], PairedConfig())
    failed = row("a", False, True) | {"failure": "provider failure"}
    with pytest.raises(ValueError):
        summarize_intervention([row("a", True)], [failed], PairedConfig())


def test_formulation_audit_rejects_final_or_unpaired_data():
    with pytest.raises(ValueError):
        audit_report(
            {
                "protocol": {
                    "config": {"evaluation_role": "final"},
                    "shared_upstream_checkpoint": True,
                }
            }
        )
    with pytest.raises(ValueError):
        audit_report({"protocol": {"config": {}, "shared_upstream_checkpoint": False}})
