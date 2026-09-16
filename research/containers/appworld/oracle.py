"""Privileged train-only reference-solution scorer check, never a research arm."""

import json
import os
import re
import sys
from pathlib import Path


def main():
    request = json.loads(sys.stdin.read(2000))
    if set(request) != {"task_id"} or not re.fullmatch(
        r"[a-f0-9]{7}_[1-9][0-9]*", request["task_id"]
    ):
        raise ValueError("only an explicit train task ID may enter the oracle")
    if os.getuid() == 0:
        raise RuntimeError("oracle process must not run as root")
    from appworld import AppWorld, load_task_ids

    if request["task_id"] not in load_task_ids("train"):
        raise ValueError("oracle restricted to train")
    destination = Path("/sandbox/experiments/oracle_result.json")
    if destination.exists() or Path("/sandbox/experiments/outputs/reference").exists():
        raise FileExistsError("oracle outputs must be fresh")
    with AppWorld(
        task_id=request["task_id"],
        experiment_name="reference",
        ground_truth_mode="full",
        load_ground_truth=True,
        raise_on_failure=False,
        timeout_seconds=15,
        raise_on_unsafe_syntax=True,
        null_patch_unsafe_execution=True,
    ) as world:
        # Exactly the reference invocation used by official appworld.verify,
        # restricted here to this one already-used train diagnostic task.
        output = world.execute(
            world.task.ground_truth.compiled_solution_code
            + "\nsolution(apis, requester)"
        )
        tracker = world.evaluate()
        result = {
            "task_id": request["task_id"],
            "reference_output": output,
            "native_success": tracker.success,
            "pass_count": tracker.pass_count,
            "fail_count": tracker.fail_count,
            "num_tests": tracker.num_tests,
            "privileged_oracle": True,
            "model_calls": 0,
            "eligible_for_induction": False,
            "eligible_for_method_comparison": False,
            "guards_enabled": True,
        }
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
