import json
import runpy
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from copromem.checkpoints import IntegrityError, digest
from copromem.stateful_adapter import (
    container_command,
    prepare_bundle,
    public_observation,
    stop_owned_container,
    verify_prefix_pair,
)

WORKER = runpy.run_path(
    str(Path(__file__).parents[1] / "research/containers/appworld/worker.py")
)


@pytest.mark.parametrize(
    "program",
    [
        "open('/sandbox/data/base_dbs/admin.db')",
        "import os",
        "from appworld.collections.models import ModelCollection",
        "x = ().__class__",
        "getattr(apis, 'supervisor')",
        "import json as __private",
    ],
)
def test_worker_rejects_extra_tools_and_introspection(program):
    with pytest.raises(ValueError):
        WORKER["validate_program"](program)


def test_worker_accepts_shared_public_api_and_json_workflow():
    WORKER["validate_program"](
        "accounts = apis.supervisor.show_account_passwords()\n"
        "print([item for item in accounts])\n"
        "import random\nprobe = random.random()"
    )


def test_worker_hashes_match_host_for_unicode_payloads():
    request = {"task_id": "07b42fd_1", "seed": 100, "actions": ["print('£ café')"]}
    assert WORKER["sha"](request) == digest(request)


def test_worker_bounds_request_and_disallows_harness_privileges():
    request = {"task_id": "07b42fd_1", "seed": 100, "actions": []}
    assert WORKER["checked_request"](request) == request
    with pytest.raises(ValueError):
        WORKER["checked_request"]({**request, "ground_truth": True})
    with pytest.raises(ValueError):
        WORKER["checked_request"]({**request, "actions": ["pass"] * 51})
    assert (
        WORKER["checked_request"]({**request, "actions": ["pass"] * 50})["actions"]
        == ["pass"] * 50
    )
    with pytest.raises(ValueError):
        WORKER["checked_request"]({**request, "task_id": "../../outside"})


def test_export_is_train_only_and_excludes_ground_truth(tmp_path):
    source, target = tmp_path / "source", tmp_path / "bundle"
    for directory in (
        "api_docs",
        "base_dbs",
        "datasets",
        "tasks/07b42fd_1/dbs",
        "tasks/07b42fd_1/ground_truth",
    ):
        (source / directory).mkdir(parents=True, exist_ok=True)
    (source / "datasets/train.txt").write_text("07b42fd_1\n")
    (source / "tasks/07b42fd_1/specs.json").write_text("{}")
    (source / "tasks/07b42fd_1/ground_truth/secret.json").write_text("hidden evaluator")
    report = prepare_bundle(source, target, ["07b42fd_1"])
    assert report["ground_truth_exported"] is False
    assert not (target / "data/tasks/07b42fd_1/ground_truth").exists()
    assert (target / "data/tasks/07b42fd_1/specs.json").exists()
    before = json.dumps(report, sort_keys=True)
    with pytest.raises(FileExistsError):
        prepare_bundle(source, target, ["07b42fd_1"])
    assert json.dumps(report, sort_keys=True) == before
    with pytest.raises(ValueError):
        prepare_bundle(source, tmp_path / "forbidden", ["fffffff_1"])


def test_container_has_no_network_secrets_or_workspace_mount(tmp_path):
    bundle, output = tmp_path / "bundle", tmp_path / "output"
    (bundle / "data").mkdir(parents=True)
    command = container_command("sha256:" + "a" * 64, bundle, output, "fixture")
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command
    assert command[command.index("--user") + 1] == "10001:10001"
    assert "--privileged" not in command and "--env-file" not in command
    mounts = [command[i + 1] for i, word in enumerate(command) if word == "--mount"]
    assert len(mounts) == 2
    assert mounts[0].endswith("target=/sandbox/data,readonly")
    assert ".env" not in " ".join(command) and "docker.sock" not in " ".join(command)


@pytest.mark.parametrize("owned", [False, True])
def test_timeout_cleanup_requires_matching_owner(monkeypatch, tmp_path, owned):
    calls = []
    labels = (
        {
            "io.copromem.research": "cycle05",
            "io.copromem.output": digest(str(tmp_path.resolve())),
        }
        if owned
        else {}
    )

    def invoke(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps(labels))

    monkeypatch.setattr(subprocess, "run", invoke)
    result = stop_owned_container("fixture", tmp_path)
    assert result["stopped"] == owned
    assert any(command[1] == "kill" for command in calls) == owned


def diagnostic_result():
    state = {
        "namespace": {"serializable": {"x": 1}, "unsupported": {}},
        "clock": "2023-01-01",
    }
    return {
        "status": "completed",
        "guards_enabled": True,
        "harness_only_state": state,
        "state_digest": digest(state),
        "results": [{"program": "print(1)", "output": "1\n"}],
        "task_id": "07b42fd_1",
        "request_id": "request",
        "native_version": "fixture",
        "initial_database_files": {},
        "public_instruction": "public task",
        "completion_flag": False,
        "native_success": True,
    }


def test_public_view_excludes_evaluator_and_private_state():
    public = public_observation(diagnostic_result())
    assert set(public) == {"task_id", "instruction", "history", "completion_flag"}
    assert "native_success" not in public and "harness_only_state" not in public


def test_verified_pair_requires_state_and_observation_identity():
    first, second = diagnostic_result(), diagnostic_result()
    assert verify_prefix_pair(first, second)["verified"]
    second["results"][0]["output"] = "2\n"
    with pytest.raises(IntegrityError):
        verify_prefix_pair(first, second)


def test_equal_errors_or_unserializable_state_cannot_pass_checkpoint():
    first, second = diagnostic_result(), diagnostic_result()
    first["results"][0]["output"] = second["results"][0]["output"] = (
        "Execution failed. timeout"
    )
    with pytest.raises(IntegrityError):
        verify_prefix_pair(first, second)
    first, second = diagnostic_result(), diagnostic_result()
    first["harness_only_state"]["namespace"]["unsupported"] = {"f": "function"}
    first["state_digest"] = digest(first["harness_only_state"])
    with pytest.raises(IntegrityError):
        verify_prefix_pair(first, second)


def test_recorded_action_errors_may_resume_only_with_matching_full_state():
    first, second = diagnostic_result(), diagnostic_result()
    first["results"][0]["output"] = second["results"][0]["output"] = (
        "Execution failed. API rejected request"
    )
    assert verify_prefix_pair(first, second, expected_error_indices=(0,))["verified"]
    second["harness_only_state"]["namespace"]["serializable"]["x"] = 2
    second["state_digest"] = digest(second["harness_only_state"])
    with pytest.raises(IntegrityError):
        verify_prefix_pair(first, second, expected_error_indices=(0,))


def test_expected_error_cannot_be_fabricated_when_action_succeeded():
    with pytest.raises(IntegrityError):
        verify_prefix_pair(
            diagnostic_result(), diagnostic_result(), expected_error_indices=(0,)
        )


def test_typed_state_preserves_types_dictionary_order_and_aliases():
    encode = WORKER["encode_state"]
    assert encode([1, 2]) != encode((1, 2))
    assert encode({"a": 1, "b": 2}) != encode({"b": 2, "a": 1})
    shared = {"value": 1}
    aliased = WORKER["namespace_state"]({"a": shared, "b": shared}, set())
    separate = WORKER["namespace_state"]({"a": {"value": 1}, "b": {"value": 1}}, set())
    assert aliased != separate
    cycle = []
    cycle.append(cycle)
    assert "reference" in json.dumps(encode(cycle))


def test_public_module_alias_and_function_are_explicit_state():
    import math

    def sample(value=1):
        return value + 1

    state = WORKER["namespace_state"]({"module": math, "function": sample}, set())
    assert not state["unsupported"]


def test_infinity_is_typed_signed_and_nan_still_fails_closed():
    encode = WORKER["encode_state"]
    assert encode(float("inf")) == ["float_infinity", "+"]
    assert encode(float("-inf")) == ["float_infinity", "-"]
    assert encode(float("inf")) != encode("inf")
    assert encode(float("inf")) != encode(1e300)
    state = WORKER["namespace_state"](
        {"positive": float("inf"), "negative": float("-inf"), "unknown": float("nan")},
        set(),
    )
    assert state["unsupported"] == {"unknown": "float"}
    json.dumps(state, allow_nan=False)


def test_live_controller_respects_advertised_and_legacy_horizon():
    from copromem.checkpoints import RunStore
    from copromem.stateful_stream import StreamWorker

    worker = StreamWorker.__new__(StreamWorker)
    worker.closed = False
    worker.request = {"task_id": "07b42fd_1", "seed": 100, "actions": ["pass"] * 20}
    worker.store, worker.run_id = RunStore(), "fixture"
    worker.last = {}
    with pytest.raises(ValueError, match="action cap"):
        worker.act("pass")
    worker.last = {"action_limit": 50}
    worker._send = lambda value: None
    worker._receive = lambda: {"action_limit": 50}
    worker.act("pass")
    assert len(worker.request["actions"]) == 21
    worker.request["actions"] = ["pass"] * 50
    with pytest.raises(ValueError, match="action cap"):
        worker.act("pass")


@pytest.mark.parametrize("program", ["apis = {}", "random.fake = 1", "r = requester"])
def test_preamble_and_api_implementation_cannot_be_mutated(program):
    with pytest.raises(ValueError):
        WORKER["validate_program"](program, {"apis", "random"})
