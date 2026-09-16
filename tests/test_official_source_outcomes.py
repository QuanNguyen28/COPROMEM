import runpy
from pathlib import Path

import pytest

from copromem.checkpoints import IntegrityError

FN = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/run_official_source_replay.py")
)["new_mixed_tasks"]


def row(task, success, eligible=True):
    return {
        "task_id": task,
        "eligible_for_local_source": eligible,
        "native_evaluation": {"native_success": success},
    }


def test_official_new_support_excludes_old_mixed_and_ineligible():
    prior = {
        "old": [False, True, True],
        "failure": [False] * 3,
        "success": [True] * 3,
        "unsupported": [False] * 2,
    }
    assert FN(
        prior,
        [
            row("old", True),
            row("failure", True),
            row("success", False),
            row("unsupported", True, False),
        ],
    ) == ["failure", "success"]


def test_official_outcomes_reject_duplicate_foreign_and_nonbinary():
    with pytest.raises(IntegrityError, match="duplicate"):
        FN({"a": [False]}, [row("a", True), row("a", True)])
    with pytest.raises(IntegrityError, match="unregistered"):
        FN({"a": [False]}, [row("b", True)])
    with pytest.raises(IntegrityError, match="binary"):
        FN({"a": [0]}, [row("a", True)])
    with pytest.raises(IntegrityError, match="binary"):
        FN({"a": [False]}, [row("a", 1)])
