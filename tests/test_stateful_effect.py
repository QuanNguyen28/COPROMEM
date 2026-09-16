from copy import deepcopy

import pytest

from copromem.checkpoints import IntegrityError, canonical, digest
from copromem.stateful_effect import effect_passes, origin_checkpoint


def authored_origin():
    prefix = {"task_id": "fixture", "seed": 100, "actions": []}
    public = {"public_context": {"instruction": "Authored fixture"}}
    request = {"user": canonical(public["public_context"])}
    response = {"text": '{"intent":"next"}'}
    state = {"namespace": {"unsupported": {}, "serializable": {}}}
    return {
        "episode": {"episode_id": "fixture-r0"},
        "prefix_request": prefix,
        "frame": {
            "task_id": "fixture",
            "request_id": digest(prefix),
            "completion_flag": False,
            "public_instruction": "Authored fixture",
            "native_version": "authored",
            "status": "completed",
            "guards_enabled": True,
            "results": [],
            "harness_only_state": state,
            "state_digest": digest(state),
            "initial_database_files": {},
        },
        "step": {
            "environment_prefix_id": digest(prefix),
            "public_checkpoint_id": digest(public),
            "planner_generation_id": digest(request),
            "plan": {"intent": "next"},
        },
        "public_checkpoint": public,
        "planner_call": {
            "request": request,
            "response": response,
            "response_sha256": digest(response),
        },
    }


def test_origin_binds_environment_and_exact_planner_without_mutation():
    origin = authored_origin()
    before = deepcopy(origin)
    checkpoint = origin_checkpoint(origin)
    assert checkpoint["environment_request_id"] == digest(origin["prefix_request"])
    assert (
        checkpoint["planner_generation_id"] == origin["step"]["planner_generation_id"]
    )
    assert checkpoint["planner_artifact"] == {"intent": "next"}
    assert origin == before


@pytest.mark.parametrize("change", ["plan", "state", "public", "prefix"])
def test_corrupted_origin_cannot_be_used_for_an_effect_claim(change):
    origin = authored_origin()
    if change == "plan":
        origin["step"]["plan"]["intent"] = "changed"
    elif change == "state":
        origin["frame"]["harness_only_state"]["namespace"]["serializable"]["new"] = 1
    elif change == "public":
        origin["public_checkpoint"]["public_context"]["instruction"] = "changed"
    elif change == "prefix":
        origin["prefix_request"]["actions"] = ["print('changed')"]
    with pytest.raises(IntegrityError):
        origin_checkpoint(origin)


@pytest.mark.parametrize(
    "failure", [None, "native", "completion", "unsupported", "action_error"]
)
def test_effect_gate_needs_clean_supported_completion_and_native_success(failure):
    frame = authored_origin()["frame"]
    frame["completion_flag"] = failure != "completion"
    frame["results"] = [
        {
            "program": "fixture",
            "output": "Execution failed. Authored error"
            if failure == "action_error"
            else "ok",
        }
    ]
    if failure == "unsupported":
        frame["harness_only_state"]["namespace"]["unsupported"] = {"opaque": "fixture"}
    assert effect_passes(frame, {"native_success": failure != "native"}) is (
        failure is None
    )
