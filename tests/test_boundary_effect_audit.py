import json
import runpy
from pathlib import Path

import pytest

from copromem.checkpoints import IntegrityError, RunStore, digest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/audit_boundary_effects.py")
)


def test_native_process_binding_and_tampered_scorer_mount_rejection(tmp_path):
    bundle = tmp_path / "bundle"
    data = tmp_path / "native/data"
    (bundle / "data").mkdir(parents=True)
    data.mkdir(parents=True)
    store = RunStore(tmp_path / "evidence")
    protocol = {
        "image_id": "sha256:" + "a" * 64,
        "public_bundle": str(bundle),
        "native_data": str(data),
    }
    key = "fixture"
    request = {
        "task_id": "fixture_1",
        "seed": 1,
        "actions": ["old_prefix", "replacement", "saved_suffix"],
    }
    index = 1
    frames = []
    for length in range(index, len(request["actions"]) + 1):
        prefix = {**request, "actions": request["actions"][:length]}
        state = {"database_files": {}, "namespace": {"unsupported": []}}
        frames.append(
            {
                "request_id": digest(prefix),
                "action_limit": 50,
                "task_id": "fixture_1",
                "results": [
                    {"program": code, "output": "ok"} for code in prefix["actions"]
                ],
                "harness_only_state": state,
                "state_digest": digest(state),
            }
        )
    final = frames[-1]
    score = {"task_id": "fixture_1", "agent_visible": False}
    for live, run in ((True, key + "-live"), (False, key + "-replay")):
        output = store.root / "native" / run
        (output / "outputs/canonical/tasks/fixture_1/dbs").mkdir(parents=True)
        command = MODULE["container_command"](
            protocol["image_id"], bundle, output, "copromem-c05-" + run
        ) + (["--stream"] if live else [])
        store.write("worker_commands", run, {"command": command})
        store.write("worker_results", run, final)
        store.write("worker_requests", run, request)
        stdout = "\n".join(
            "COPROMEM_WORKER_RESULT=" + json.dumps(frame)
            for frame in (frames if live else [final])
        )
        if live:
            stdout += "\nCOPROMEM_WORKER_DONE=" + json.dumps(final)
            store.write(
                "stream_initial_requests",
                run,
                {**request, "actions": request["actions"][:index]},
            )
            for offset, frame in enumerate(frames + [final]):
                store.write("stream_frames", f"{run}-{offset:03d}", frame)
            for length in range(index + 1, len(request["actions"]) + 1):
                store.write(
                    "stream_inputs",
                    f"{run}-{length:03d}",
                    {
                        "program": request["actions"][length - 1],
                        "prefix_id": digest(
                            {**request, "actions": request["actions"][:length]}
                        ),
                    },
                )
        store.write("worker_processes", run, {"exit_code": 0, "stdout": stdout})
        store.write("native_evaluation", run, score)
        store.write(
            "evaluator_processes",
            run,
            {
                "exit_code": 0,
                "stdout": "COPROMEM_EVALUATOR_RESULT=" + json.dumps(score),
            },
        )
        store.write(
            "evaluator_commands",
            run,
            {
                "command": MODULE["expected_scorer_command"](
                    protocol["image_id"], data, output, run
                ),
                "agent_actions_accepted": False,
            },
        )
    frames_checked, inputs = MODULE["check_processes"](
        store, protocol, key, request, index
    )
    assert len(frames_checked) == 4
    assert len(inputs) == 2
    original_read = store.read

    def changed(kind, name):
        value = original_read(kind, name)
        if kind == "evaluator_commands" and name.endswith("-live"):
            value["command"] = [
                part.replace(",readonly", "") for part in value["command"]
            ]
        return value

    store.read = changed
    with pytest.raises(
        IntegrityError, match="scorer code/isolation/read-only mounts changed"
    ):
        MODULE["check_processes"](store, protocol, key, request, index)
