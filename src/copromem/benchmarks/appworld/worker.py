#!/usr/bin/env python3
"""JSON-lines boundary for one native AppWorld task process.

Only public AppWorld information crosses this boundary: task instruction and
application descriptions, submitted actions, their observations, completion,
and official scorer summaries.  The worker deliberately never exports checker
state or task databases.
"""
from __future__ import annotations

import json
import os
import sys


def emit(value: dict) -> None:
    print(json.dumps(value, sort_keys=True), flush=True)


def main() -> None:
    from appworld import AppWorld

    allowed = {item for item in os.environ.get("APPWORLD_ALLOWED_TASKS", "").split(",") if item}
    world: AppWorld | None = None
    task_id: str | None = None
    for raw in sys.stdin:
        try:
            request = json.loads(raw)
            operation = request.get("op")
            if operation == "start":
                requested = request.get("task_id")
                if world is not None or requested not in allowed:
                    raise ValueError("one registered allowed task is required")
                task_id = requested
                fixture = request.get("fixture") is True
                world = AppWorld(
                    task_id=task_id,
                    experiment_name=request["experiment_name"],
                    raise_on_failure=False,
                    timeout_seconds=30,
                    raise_on_unsafe_syntax=True,
                    null_patch_unsafe_execution=True,
                    **({"ground_truth_mode": "full", "load_ground_truth": True} if fixture else {}),
                )
                emit({"ok": True, "task_id": task_id, "instruction": world.task.instruction,
                      "supervisor": world.task.supervisor, "app_descriptions": world.task.app_descriptions})
            elif operation == "action":
                if world is None:
                    raise RuntimeError("start required")
                output = world.execute(request["code"])
                emit({"ok": True, "output": output, "completed": world.task_completed()})
            elif operation == "score":
                if world is None:
                    raise RuntimeError("start required")
                score = world.evaluate()
                emit({"ok": True, "success": score.success, "pass_count": score.pass_count,
                      "fail_count": score.fail_count, "num_tests": score.num_tests})
            elif operation == "finish":
                if world is None:
                    raise RuntimeError("start required")
                score = world.evaluate()
                world.close()
                emit({"ok": True, "task_id": task_id, "success": score.success,
                      "pass_count": score.pass_count, "fail_count": score.fail_count,
                      "num_tests": score.num_tests})
                return
            else:
                raise ValueError("unknown op")
        except Exception as exc:
            # Preserve enough context to diagnose a boundary failure without
            # exposing private task data.
            emit({"ok": False, "error_type": type(exc).__name__, "error": str(exc)[:256]})
            return


if __name__ == "__main__":
    main()
