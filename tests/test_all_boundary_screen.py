import runpy
from pathlib import Path

import pytest

from copromem.checkpoints import IntegrityError

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/screen_all_boundaries.py")
)


def target(**changes):
    return {
        "task_id": "fixture",
        "boundary_status": "valid_fixed_team_target",
        "code": "items = fetch(1)\nconsume(items)",
        "action_error": True,
        **changes,
    }


def donor(**changes):
    return {
        "task_id": "fixture",
        "code": "items = fetch(2)\nconsume(items)",
        "action_error": False,
        **changes,
    }


def test_failed_target_action_can_propose_but_failed_donor_cannot():
    assert (
        MODULE["screen_action_pair"](target(), donor())["status"]
        == "proposals_available"
    )
    assert (
        MODULE["screen_action_pair"](target(), donor(action_error=True))["status"]
        == "donor_action_error"
    )


@pytest.mark.parametrize(
    "status",
    [
        "archive_not_fixed_team_target",
        "already_completed_target",
        "unsupported_target_namespace",
    ],
)
def test_target_boundary_exclusions_remain_visible(status):
    row = MODULE["screen_action_pair"](target(boundary_status=status), donor())
    assert row["status"] == status
    assert row["proposals"] == []


def test_cross_task_pair_is_not_silently_used():
    with pytest.raises(IntegrityError):
        MODULE["screen_action_pair"](target(), donor(task_id="other"))


def test_unsupported_donor_syntax_is_not_rewritten():
    assert (
        MODULE["screen_action_pair"](
            target(), donor(code="items = [x for x in stream]")
        )["status"]
        == "unsupported_source_syntax"
    )
