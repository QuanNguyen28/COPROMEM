import runpy
from pathlib import Path

import pytest

from copromem.checkpoints import IntegrityError, digest
from copromem.procedural_diff import BlockTransplant

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/screen_public_bindings.py")
)


def fixture():
    target, donor = (
        "key = 'fixture'\nrows = apis.demo.get(arg=key)\nprint(rows)",
        "rows = apis.demo.get(arg=other)",
    )
    proposal = BlockTransplant(target, donor, "rows", (0, 2), (0, 1), (0,)).record()
    pair = {
        "target": {"task_id": "fixture_1", "action_index": 0, "code": target},
        "donor": {"task_id": "fixture_1", "action_index": 4, "code": donor},
    }
    candidate = {
        "action_pair_id": digest(pair),
        "task_id": "fixture_1",
        "target_action_index": 0,
        "donor_action_index": 4,
        "proposal": proposal,
        "origin": {
            "step": {"code": target},
            "prefix_request": {"task_id": "fixture_1", "actions": []},
            "frame": {"harness_only_state": "must-not-enter-constructor"},
            "episode": {"native_evaluation": {"native_success": False}},
        },
    }
    return candidate, pair


def test_public_input_allowlist_excludes_task_scores_planner_and_hidden_state():
    candidate, pair = fixture()
    public = MODULE["public_inputs"](candidate, pair)
    assert not set(public) & {
        "task_id",
        "origin",
        "frame",
        "native_evaluation",
        "episode",
        "planner",
    }
    assert MODULE["construct"](public)["status"] == "accepted_changed"
    with pytest.raises(IntegrityError):
        MODULE["construct"]({**public, "native_success": True})


@pytest.mark.parametrize("where", ["pair", "proposal", "prefix"])
def test_source_corruption_is_integrity_failure_not_scientific_rejection(where):
    candidate, pair = fixture()
    if where == "pair":
        pair["target"]["code"] = "changed"
    elif where == "proposal":
        candidate["proposal"]["program"] = "changed"
    else:
        candidate["origin"]["prefix_request"]["actions"] = ["extra"]
    with pytest.raises(IntegrityError):
        MODULE["public_inputs"](candidate, pair)
