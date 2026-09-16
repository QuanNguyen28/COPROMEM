"""Policy-label separation and paired-outcome arithmetic on constructed fixtures."""

import copy
import runpy
from pathlib import Path

import pytest

M = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/saved_branch_selection.py")
)


def public(before, after, unknown=False):
    return {
        "original": {"risks": sorted(before), "unknown": False},
        "edited": {"risks": sorted(after), "unknown": unknown},
    }


def test_partial_risk_repair_does_not_require_all_clear():
    r = M["selections"](public(["pagination", "consumer"], ["consumer"]))
    assert r == {
        "no_op": False,
        "always_edit": True,
        "manual_all_clear": False,
        "manual_risk_reduction": True,
    }


@pytest.mark.parametrize(
    "before,after,unknown",
    [
        ([], [], False),
        (["old"], ["new"], False),
        (["old"], ["old"], False),
        (["old"], [], True),
        ([], ["new"], False),
    ],
)
def test_nonimprovement_new_risk_and_unknown_do_not_activate(before, after, unknown):
    assert not M["selections"](public(before, after, unknown))["manual_risk_reduction"]


def test_policy_is_input_immutable_and_rejects_labels_or_ids():
    p = public(["old"], [])
    old = copy.deepcopy(p)
    assert M["selections"](p)["manual_risk_reduction"]
    assert p == old
    with pytest.raises(ValueError):
        M["selections"]({**p, "native_success": True})
    p["edited"]["record_id"] = 13
    with pytest.raises(ValueError):
        M["selections"](p)


def test_paired_metrics_include_harm_and_oracle_uses_labels_only_in_evaluation():
    rows = []
    for before, after, selected in [
        (False, True, True),
        (True, False, False),
        (False, False, False),
        (True, True, False),
    ]:
        rows.append(
            {
                "original_success": before,
                "edited_success": after,
                "selections": {
                    "no_op": False,
                    "always_edit": True,
                    "manual_all_clear": selected,
                    "manual_risk_reduction": selected,
                },
                "original_api_entries": 10,
                "edited_api_entries": 15,
            }
        )
    r = M["evaluate"](rows)
    assert r["no_op"]["successes"] == 2
    assert r["always_edit"]["beneficial_vs_no_op"] == 1
    assert r["always_edit"]["harmful_vs_no_op"] == 1
    assert r["manual_risk_reduction"]["successes"] == 3
    assert r["manual_risk_reduction"]["oracle_quality_headroom"] == 0
    assert r["quality_oracle"]["selected_native_api_entries"] == 45
    rows[0]["edited_api_entries"] = None
    assert M["evaluate"](rows)["quality_oracle"]["selected_native_api_entries"] is None


def test_risk_summary_ignores_nonproof_assumptions_but_retains_unknown():
    manual = {
        "version": "fixture",
        "scope": "fixture",
        "pagination": {"status": "pattern_observed", "reasons": ["not a proof"]},
        "consumer_risks": ["first artist"],
        "decision": "warn",
    }
    assert M["public_findings"](manual, ["missing"]) == {
        "risks": ["consumer:first artist", "name:missing"],
        "unknown": False,
    }
    manual["pagination"]["status"] = "unknown"
    assert M["public_findings"](manual, [])["unknown"]
