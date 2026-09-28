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
import hashlib
from pathlib import Path


def emit(value: dict) -> None:
    print(json.dumps(value, sort_keys=True), flush=True)


def native_state_sha256(world) -> str:
    """Hash the worker-owned final database state without exporting its data."""
    root = Path(world.output_db_home_path_on_disk)
    hasher = hashlib.sha256()
    for item in sorted(path for path in root.rglob("*") if path.is_file()):
        hasher.update(str(item.relative_to(root)).encode("utf-8"))
        with item.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(block)
    return hasher.hexdigest()


def main() -> None:
    from appworld import AppWorld
    try:  # executed as a package in tests, as a script by the native worker
        from .execution_evidence import DispatcherEvidenceRecorder, ExecutionEvidenceJournal, load_registry, prepare_evidence_journal
    except ImportError:  # pragma: no cover - exercised by the native subprocess
        from execution_evidence import DispatcherEvidenceRecorder, ExecutionEvidenceJournal, load_registry, prepare_evidence_journal

    allowed = {item for item in os.environ.get("APPWORLD_ALLOWED_TASKS", "").split(",") if item}
    world: AppWorld | None = None
    task_id: str | None = None
    evidence_journal: ExecutionEvidenceJournal | None = None
    evidence_config: dict | None = None
    original_request_dispatch = None
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
                telemetry = request.get("execution_evidence")
                startup_evidence = None
                if telemetry is not None:
                    if not isinstance(telemetry, dict):
                        raise ValueError("execution evidence configuration must be an object")
                    registry = load_registry(telemetry["registry_path"], telemetry["registry_sha256"])
                    evidence_journal, startup_evidence = prepare_evidence_journal(telemetry["journal_path"])
                    evidence_config = {"registry": registry, "registry_sha256": telemetry["registry_sha256"]}
                world = AppWorld(
                    task_id=task_id,
                    experiment_name=request["experiment_name"],
                    raise_on_failure=False,
                    timeout_seconds=30,
                    raise_on_unsafe_syntax=True,
                    null_patch_unsafe_execution=True,
                    **({"ground_truth_mode": "full", "load_ground_truth": True} if fixture else {}),
                )
                if evidence_config is not None:
                    original_request_dispatch = world.requester._request
                emit({"ok": True, "task_id": task_id, "instruction": world.task.instruction,
                      "supervisor": world.task.supervisor, "app_descriptions": world.task.app_descriptions,
                      "execution_evidence_startup": startup_evidence})
            elif operation == "action":
                if world is None:
                    raise RuntimeError("start required")
                recorder = None
                if evidence_config is not None and evidence_journal is not None:
                    program_id = request.get("program_id")
                    if not isinstance(program_id, str) or not program_id:
                        raise ValueError("execution evidence requires a parent program id")
                    if original_request_dispatch is None:
                        raise RuntimeError("native request dispatcher was not captured")
                    # Each submitted program receives a fresh monotonic event
                    # stream; never wrap a wrapper from an earlier action.
                    world.requester._request = original_request_dispatch
                    recorder = DispatcherEvidenceRecorder(evidence_config["registry"], evidence_journal,
                                                          program_id, evidence_config["registry_sha256"])
                    recorder.install(world.requester)
                try:
                    output = world.execute(request["code"])
                finally:
                    # Worker bookkeeping (including task_completed) is not
                    # agent-program execution evidence.
                    if recorder is not None:
                        world.requester._request = original_request_dispatch
                        # AppWorld's safety guard has now restored native
                        # file functions.  Flush the action's already
                        # response-attested, value-redacted events before the
                        # worker acknowledges the action to its parent.
                        recorder.flush()
                emit({"ok": True, "output": output, "completed": world.task_completed(),
                      "execution_evidence_path": str(evidence_journal.path) if evidence_journal else None})
            elif operation == "score":
                if world is None:
                    raise RuntimeError("start required")
                score = world.evaluate()
                emit({"ok": True, "success": score.success, "pass_count": score.pass_count,
                      "fail_count": score.fail_count, "num_tests": score.num_tests,
                      "native_state_sha256": native_state_sha256(world)})
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
