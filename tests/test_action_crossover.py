import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

from copromem.checkpoints import IntegrityError, RunStore, canonical, digest

spec = importlib.util.spec_from_file_location(
    "crossover",
    Path(__file__).parents[1] / "research/scripts/run_action_crossover.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture_store():
    store = RunStore()
    request = {"task_id": "fixture", "seed": 100, "actions": ["print(1)", "print(2)"]}
    prefix = {**request, "actions": request["actions"][:-1]}
    public = {"public_context": {"instruction": "Authored fixture"}}
    planner_request = {"user": canonical(public["public_context"])}
    response = {"text": '{"intent":"finish"}'}
    planner = {
        "request": planner_request,
        "response": response,
        "response_sha256": digest(response),
    }
    episode = {
        "episode_id": "fixture-r0",
        "task_id": "fixture",
        "steps": 2,
        "completion_flag": True,
        "eligible_for_induction": True,
    }
    step = {
        "planner_generation_id": digest(planner_request),
        "public_checkpoint_id": digest(public),
        "environment_prefix_id": digest(prefix),
        "code": "print(2)",
        "plan": {"intent": "finish"},
    }
    store.write("source_steps", "fixture-r0-01", step)
    store.write(
        "stream_frames",
        "fixture-r0-001",
        {"completion_flag": False, "request_id": digest(prefix)},
    )
    store.write("worker_requests", "fixture-r0", request)
    store.write("calls", digest(planner_request), planner)
    store.write("public_handoffs", digest(public), public)
    return store, episode


def test_endpoint_binds_exact_plan_and_program_without_regeneration():
    source, episode = fixture_store()
    endpoint = module.source_endpoint(source, episode)
    assert endpoint["prefix_request"]["actions"] == ["print(1)"]
    assert endpoint["step"]["plan"] == {"intent": "finish"}
    assert endpoint["step"]["code"] == "print(2)"


@pytest.mark.parametrize("field", ["completion_flag", "eligible_for_induction"])
def test_endpoint_rejects_ineligible_or_unfinished_sources(field):
    source, episode = fixture_store()
    episode[field] = False
    with pytest.raises(IntegrityError, match="supported completed"):
        module.source_endpoint(source, episode)


@pytest.mark.parametrize("kind", ["planner", "program", "prefix", "context"])
def test_endpoint_rejects_mixed_or_tampered_artifacts(kind):
    source, episode = fixture_store()
    original_read = source.read

    def tampered_read(namespace, key):
        value = deepcopy(original_read(namespace, key))
        if kind == "planner" and namespace == "calls":
            value["response"]["text"] = '{"intent":"different"}'
        elif kind == "program" and namespace == "worker_requests":
            value["actions"][-1] = "print(3)"
        elif kind == "prefix" and namespace == "stream_frames":
            value["request_id"] = "wrong"
        elif kind == "context" and namespace == "public_handoffs":
            value["public_context"]["instruction"] = "different"
        return value

    source.read = tampered_read
    with pytest.raises(IntegrityError, match="identity mismatch"):
        module.source_endpoint(source, episode)
