import runpy
from pathlib import Path

import pytest

from copromem.checkpoints import IntegrityError

MODULE = runpy.run_path(
    str(
        Path(__file__).parents[1] / "research/scripts/screen_archived_source_repairs.py"
    )
)


def source(key, success, code="apis.supervisor.complete_task()", **changes):
    return {
        "task_id": "fixture_1",
        "source_store": "fixture",
        "source_kind": "source_episodes",
        "source_id": key,
        "eligible": True,
        "success": success,
        "completion_flag": True,
        "actions": 1,
        "final_action": code,
        **changes,
    }


def test_all_pairs_and_archived_schema_remain_distinct():
    rows = [
        source("f0", False),
        source("f1", False),
        source("s0", True),
        source("archive", True, source_kind="replayed_sources"),
    ]
    result = MODULE["screen_task"]("fixture_1", rows)
    assert result["outcome_pairs"] == 4
    assert sum(pair["includes_archived_source"] for pair in result["pairs"]) == 2
    assert all(pair["status"] == "no_proposal" for pair in result["pairs"])


def test_noncompletion_is_retained_and_ineligible_is_not_paired():
    rows = [
        source("f", False, completion_flag=False),
        source("s", True),
        source("excluded", True, eligible=False),
    ]
    result = MODULE["screen_task"]("fixture_1", rows)
    assert result["outcome_pairs"] == result["ineligible_sources"] == 1
    assert result["pairs"][0]["status"] == "not_completed_final_action_pair"


@pytest.mark.parametrize(
    "rows",
    [[source("f", False)] * 2, [source("f", False, task_id="other")], [source("f", 0)]],
)
def test_invalid_source_identity_or_nonbinary_outcome_rejected(rows):
    with pytest.raises(IntegrityError):
        MODULE["screen_task"]("fixture_1", rows)


def test_generic_proposal_coverage_is_preserved():
    rows = [
        source("f", False, "items = fetch(1)\nconsume(items)"),
        source(
            "s",
            True,
            "items = fetch(2)\nconsume(items)",
            source_kind="replayed_sources",
        ),
    ]
    pair = MODULE["screen_task"]("fixture_1", rows)["pairs"][0]
    assert pair["status"] == "proposals_available"
    assert len(pair["proposals"]) == 1
    assert pair["proposals"][0]["anchor"] == "items"


def test_unsuccessful_process_output_cannot_be_audited():
    auditor = runpy.run_path(
        str(
            Path(__file__).parents[1]
            / "research/scripts/audit_official_source_replay.py"
        )
    )
    with pytest.raises(IntegrityError):
        auditor["process_frames"]({"exit_code": 1, "stdout": "FRAME={}"}, "FRAME=")
    with pytest.raises(IntegrityError):
        auditor["process_frames"](
            {"exit_code": 0, "closure_error_type": "timeout", "stdout": "FRAME={}"},
            "FRAME=",
        )
    assert auditor["process_frames"](
        {"exit_code": 0, "stdout": 'other\nFRAME={"ok": true}'}, "FRAME="
    ) == [{"ok": True}]
