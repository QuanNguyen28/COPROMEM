import copy
import runpy
from pathlib import Path

import pytest

from copromem.checkpoints import IntegrityError, digest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/run_bound_effects.py")
)


def fixture():
    original = {
        "task_id": "fixture",
        "target_action_index": 2,
        "origin_source": {"source_id": "episode"},
        "origin": {
            "step": {"plan": "fixed planner", "code": "old"},
            "prefix_request": {"actions": ["a", "b"]},
        },
    }
    bound = {
        "source_candidate_id": digest(original),
        "task_id": "fixture",
        "target_action_index": 2,
        "origin_episode": "episode",
        "public_input_digest": "public",
        "construction": {
            "status": "accepted_changed",
            "changed_from_original_proposal": True,
            "missing_inputs": [],
            "missing_outputs": [],
            "rejections": [],
            "program": "new",
            "program_ast_digest": "ast",
            "operator": "fixture",
        },
    }
    return bound, original


def test_new_effect_schema_preserves_original_checkpoint_without_aliasing():
    bound, original = fixture()
    saved = copy.deepcopy(original)
    candidate = MODULE["effect_candidate"](bound, original)
    assert candidate["origin"] == original["origin"]
    assert candidate["proposal"]["program"] == "new"
    candidate["origin"]["prefix_request"]["actions"].append("mutation")
    assert original == saved
    assert candidate["source_candidate_id"] == digest(saved)


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "rejected"),
        ("changed_from_original_proposal", False),
        ("missing_inputs", ["x"]),
        ("missing_outputs", ["y"]),
    ],
)
def test_rejected_or_unchanged_construction_cannot_enter_new_effects(field, value):
    bound, original = fixture()
    bound["construction"][field] = value
    with pytest.raises(IntegrityError):
        MODULE["effect_candidate"](bound, original)


def test_changed_source_identity_is_rejected():
    bound, original = fixture()
    original["origin"]["step"]["plan"] = "different"
    with pytest.raises(IntegrityError):
        MODULE["effect_candidate"](bound, original)
