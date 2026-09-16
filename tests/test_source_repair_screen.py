import runpy
from pathlib import Path

import pytest

from copromem.checkpoints import IntegrityError, RunStore

SCREEN = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/screen_source_repairs.py")
)


def test_screen_distinguishes_no_proposal_unsupported_and_candidate():
    screen = SCREEN["screen_programs"]
    assert screen("print(1)", "print(2)")["status"] == "no_proposal"
    assert (
        screen("values = [x for x in data]", "values = []")["status"]
        == "unsupported_source_syntax"
    )
    value = screen(
        "items = fetch()\nconsume(items)", "items = fetch_all()\nconsume(items)"
    )
    assert value["status"] == "proposals_available"
    assert value["proposals"][0]["anchor"] == "items"


def corpus():
    store = RunStore()
    store.write("protocol", "preregistration", {"cycle_id": "fixture", "replicates": 2})
    store.write("dataset", "selection", {"build": ["alpha", "beta", "gamma"]})
    episodes = []
    for task, outcomes in [
        ("alpha", (False, False)),
        ("beta", (False, True)),
        ("gamma", (False, True)),
    ]:
        for replicate, success in enumerate(outcomes):
            episode_id = f"{task}-r{replicate}"
            row = {
                "task_id": task,
                "episode_id": episode_id,
                "eligible_for_induction": True,
                "native_evaluation": {"native_success": success},
                "steps": 1,
                "completion_flag": task != "gamma",
            }
            episodes.append(row)
            store.write("source_episodes", episode_id, row)
            store.write(
                "source_steps", f"{episode_id}-00", {"code": f"print({replicate})"}
            )
    return store, {
        "cycle_id": "fixture",
        "complete_registered_sample": True,
        "episodes": episodes,
    }


def test_screen_retains_no_contrast_and_unfinished_cases():
    store, audit = corpus()
    result = SCREEN["screen"](store, audit)
    assert len(result["tasks"]) == 3
    assert result["tasks"][0]["outcome_pairs"] == 0
    assert [pair["status"] for pair in result["pairs"]] == [
        "no_proposal",
        "not_completed_final_action_pair",
    ]
    assert result["outcome_pairs"] == 2
    assert (
        result["proposals"]
        == result["native_executions"]
        == result["admitted_contracts"]
        == 0
    )


def test_screen_refuses_partial_or_unbound_audit():
    store, audit = corpus()
    with pytest.raises(IntegrityError, match="complete"):
        SCREEN["screen"](store, {**audit, "complete_registered_sample": False})
    with pytest.raises(IntegrityError, match="another cycle"):
        SCREEN["screen"](store, {**audit, "cycle_id": "other"})
    with pytest.raises(IntegrityError, match="replicate count"):
        SCREEN["screen"](store, {**audit, "episodes": audit["episodes"][:-1]})
