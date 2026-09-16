import copy
import runpy
from pathlib import Path

import pytest

from copromem.checkpoints import IntegrityError, digest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/run_public_presence.py")
)


def boundary():
    request = {"task_id": "fixture", "seed": 7, "actions": ["first", "target", "last"]}
    return {
        "original_request": request,
        "index": 1,
        "origin": {
            "prefix_request": {**request, "actions": ["first"]},
            "step": {"code": "target"},
        },
        "construction": {"query": "probe"},
    }


def test_insertion_keeps_all_source_actions_and_never_mutates_origin():
    b = boundary()
    original = copy.deepcopy(b)
    assert MODULE["insertion_request"](b, True)["actions"] == [
        "first",
        "probe",
        "target",
        "last",
    ]
    assert MODULE["insertion_request"](b, False) == b["original_request"]
    assert b == original


@pytest.mark.parametrize("field", ["prefix", "seed", "target"])
def test_different_origin_source_or_boundary_cannot_enter_probe_request(field):
    b = boundary()
    if field == "prefix":
        b["origin"]["prefix_request"]["actions"] = ["other"]
    elif field == "seed":
        b["origin"]["prefix_request"]["seed"] = 9
    else:
        b["origin"]["step"]["code"] = "other"
    with pytest.raises(IntegrityError):
        MODULE["insertion_request"](b, True)


def test_normalization_removes_only_registered_probe_and_preserves_raw_frame():
    b = boundary()
    request = MODULE["insertion_request"](b, True)
    frame = {
        "request_id": digest(request),
        "results": [{"program": p, "output": p} for p in request["actions"]],
        "state_digest": "unchanged",
    }
    original = copy.deepcopy(frame)
    normalized = MODULE["normalized_final"](frame, b["original_request"], 1, "probe")
    assert normalized["request_id"] == digest(b["original_request"])
    assert [r["program"] for r in normalized["results"]] == ["first", "target", "last"]
    assert frame == original
    with pytest.raises(IntegrityError):
        MODULE["normalized_final"](frame, b["original_request"], 1, "different")


def test_probe_state_output_and_tool_mutations_are_separate_failed_gates():
    state = {
        "namespace": {"unsupported": {}, "serializable": {}},
        "database_files": {},
        "random_state": "same",
    }
    before = {
        "state_digest": digest(state),
        "harness_only_state": state,
        "completion_flag": False,
        "results": [{"program": "old", "output": "same"}],
    }
    after = {
        **copy.deepcopy(before),
        "results": [
            *copy.deepcopy(before["results"]),
            {"program": "probe", "output": "presence"},
        ],
    }
    assert all(
        MODULE["compare_probe"](
            before, after, "probe", {"bytes": 7}, {"bytes": 7}
        ).values()
    )
    after["harness_only_state"]["random_state"] = "changed"
    after["state_digest"] = digest(after["harness_only_state"])
    checks = MODULE["compare_probe"](before, after, "probe", {"bytes": 7}, {"bytes": 8})
    assert not checks["state_unchanged"] and not checks["api_log_unchanged"]
    after["state_digest"] = "corrupt"
    with pytest.raises(IntegrityError):
        MODULE["compare_probe"](before, after, "probe", {}, {})
