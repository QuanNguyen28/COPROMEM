import runpy
from pathlib import Path

import pytest

from copromem.checkpoints import IntegrityError, RunStore

SCREEN = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/screen_reflection_repairs.py")
)["screen_task"]


def members(outcomes, complete=True, eligible_retry=True):
    source = RunStore()
    rows = []
    for index, success in enumerate(outcomes):
        episode = {
            "episode_id": f"toy-r{index}",
            "task_id": "toy",
            "eligible_for_induction": eligible_retry if index == 2 else True,
            "native_evaluation": {"native_success": success},
            "completion_flag": complete,
            "steps": 1,
        }
        source.write("source_episodes", episode["episode_id"], episode)
        source.write(
            "source_steps",
            f"toy-r{index}-00",
            {
                "code": ("items = fetch_all()" if success else "items = fetch()")
                + "\nconsume(items)",
            },
        )
        rows.append((source, episode))
    return rows


def test_combined_screen_does_not_count_old_task_as_new_support():
    result = SCREEN("toy", members([False, True, True]), "toy-r2")
    assert result["previously_mixed"] and not result["newly_mixed"]
    assert result["outcome_pairs"] == 2
    assert sum(pair["includes_new_retry"] for pair in result["pairs"]) == 1
    assert all(pair["proposals"] for pair in result["pairs"])


def test_combined_screen_retains_all_new_pairs_and_unfinished_cases():
    result = SCREEN("toy", members([False, False, True], complete=False), "toy-r2")
    assert result["newly_mixed"] and result["outcome_pairs"] == 2
    assert all(
        pair["status"] == "not_completed_final_action_pair" for pair in result["pairs"]
    )
    assert all(not pair["proposals"] for pair in result["pairs"])


def test_combined_screen_does_not_promote_ineligible_opposite_outcome():
    result = SCREEN(
        "toy", members([False, False, True], eligible_retry=False), "toy-r2"
    )
    assert result["ineligible_episodes"] == 1
    assert not result["newly_mixed"] and result["outcome_pairs"] == 0


def test_combined_screen_refuses_duplicates_or_unbound_source():
    rows = members([False, False, True])
    with pytest.raises(IntegrityError, match="duplicate"):
        SCREEN("toy", rows + [rows[0]], "toy-r2")
    with pytest.raises(IntegrityError, match="one registered"):
        SCREEN("toy", rows[:-1], "toy-r2")
    with pytest.raises(IntegrityError, match="identity"):
        SCREEN("another", rows, "toy-r2")
