import runpy
from pathlib import Path

import pytest

from copromem.checkpoints import IntegrityError

SUMMARY = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/audit_reflection_source.py")
)["outcome_summary"]


def test_only_new_eligible_contrasts_count_and_harm_is_not_hidden():
    cases = [
        ("old_mixed", [False, True], False, True, True),
        ("rescued", [False, False], False, True, True),
        ("harmed", [True, True], True, False, True),
        ("unsupported", [False], False, True, False),
        ("unchanged", [False, False], False, False, True),
    ]
    sources = {
        task: {
            "prior_eligible_outcomes": prior,
            "reflection_input": {"previous_native_success": before},
        }
        for task, prior, before, _, _ in cases
    }
    episodes = [
        {
            "task_id": task,
            "native_evaluation": {"native_success": after},
            "eligible_for_induction": eligible,
        }
        for task, _, _, after, eligible in cases
    ]
    result = SUMMARY(sources, episodes)
    assert result["new_mixed_tasks"] == ["rescued", "harmed"]
    assert result["primary_metric"] == 2
    assert [
        row["change"] for row in result["descriptive_outcome_changes_not_causal_flips"]
    ] == ["bad_to_good", "bad_to_good", "good_to_bad", "bad_to_good", "same"]


def test_nonbinary_or_empty_outcome_history_is_rejected():
    for prior in ([], [1], ["success"]):
        with pytest.raises(IntegrityError):
            SUMMARY({"task": {"prior_eligible_outcomes": prior}}, [{"task_id": "task"}])
