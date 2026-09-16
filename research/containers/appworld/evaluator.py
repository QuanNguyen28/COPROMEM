"""Privileged native train evaluator: never accepts or executes an agent action."""

import json
import os
import re
import sys


def main():
    value = json.loads(sys.stdin.read(2000))
    if set(value) != {"task_id"} or not re.fullmatch(
        r"[a-f0-9]{7}_[1-9][0-9]*", value["task_id"]
    ):
        raise ValueError("only a task ID is accepted by the evaluator")
    if os.getuid() == 0:
        raise RuntimeError("native evaluator must run as non-root")
    from appworld import load_task_ids
    from appworld.evaluator import evaluate_task

    if value["task_id"] not in load_task_ids("train"):
        raise ValueError("this diagnostic evaluator accepts train tasks only")
    tracker = evaluate_task(
        value["task_id"], experiment_name="canonical", save_report=False
    )
    result = {
        "task_id": value["task_id"],
        "native_success": tracker.success,
        "pass_count": tracker.pass_count,
        "fail_count": tracker.fail_count,
        "num_tests": tracker.num_tests,
        "agent_visible": False,
        "evaluator": "unmodified AppWorld evaluate_task, save_report=False",
    }
    print("COPROMEM_EVALUATOR_RESULT=" + json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
