import copy
import runpy
from pathlib import Path

import pytest

from copromem.checkpoints import IntegrityError, digest

SOURCE = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/code_predicate_sources.py")
)
SCREEN = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/screen_code_predicates.py")
)


def fixture():
    request = {"task_id": "fixture", "actions": ["x=1", "print(x)"], "seed": 3}
    worker = {
        "request_id": digest(request),
        "task_id": "fixture",
        "results": [
            {"program": p, "output": "not a feature"} for p in request["actions"]
        ],
        "harness_only_state": {"namespace": "MUST NOT ENTER MINER"},
    }
    native = {"task_id": "fixture", "native_success": True, "pass_count": 999}
    return request, worker, native


def test_public_action_strips_state_scores_task_ids_and_outputs():
    request, worker, native = fixture()
    saved = copy.deepcopy((request, worker, native))
    assert SOURCE["public_action"](request, worker, native, 1, "print(x)") == {
        "program": "print(x)",
        "label": True,
    }
    assert saved == (request, worker, native)


@pytest.mark.parametrize(
    "changed", ["request", "task", "program", "label", "hash", "index"]
)
def test_mismatched_action_native_or_request_is_integrity_failure(changed):
    request, worker, native = fixture()
    index = 1
    if changed == "request":
        request["actions"][0] = "changed"
    elif changed == "task":
        native["task_id"] = "different"
    elif changed == "program":
        worker["results"][1]["program"] = "changed"
    elif changed == "label":
        native["native_success"] = 1
    elif changed == "hash":
        worker["request_id"] = "changed"
    else:
        index = True
    with pytest.raises(IntegrityError):
        SOURCE["public_action"](request, worker, native, index, "print(x)")


def test_overlaps_include_origin_boundary_and_program_not_just_task_label():
    row = {
        "origin_episode": "one",
        "action_index": 2,
        "public": {"program": "x=1", "label": True},
    }
    key = SCREEN["overlap_key"](row)
    assert SCREEN["overlap_key"]({**row, "origin_episode": "two"}) != key
    assert SCREEN["overlap_key"]({**row, "action_index": 3}) != key
    assert (
        SCREEN["overlap_key"]({**row, "public": {**row["public"], "label": False}})
        == key
    )


def test_conflicting_representation_labels_are_retained_with_all_indices():
    rows = [
        {"eligible": True, "public": {"label": label}} for label in [True, False, False]
    ]
    vectors = [{"error": None, "features": {"node:Name": 1}} for _ in rows]
    groups = SCREEN["conflicts"](rows, vectors, "features")
    assert len(groups) == 1 and groups[0]["indices"] == [0, 1, 2]
    assert groups[0]["labels"] == [True, False, False]
    rows[0]["eligible"] = False
    assert SCREEN["conflicts"](rows, vectors, "features") == []
