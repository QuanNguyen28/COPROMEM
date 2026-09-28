#!/usr/bin/env python3
"""Zero-model native AppWorld equivalence check for execution-evidence v1.

The script uses only the previously exposed fixture supplied on the command
line.  It emits a sanitized report: no task instruction, API response, code,
or scorer detail is persisted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
from typing import Any


def _send(process: subprocess.Popen[str], row: dict[str, Any]) -> dict[str, Any]:
    assert process.stdin and process.stdout
    process.stdin.write(json.dumps(row, separators=(",", ":")) + "\n"); process.stdin.flush()
    result = json.loads(process.stdout.readline())
    if not result.get("ok"):
        raise RuntimeError(f"worker failure: {result.get('error_type', 'unknown')}")
    return result


def _output_class(value: str) -> str:
    if value.startswith("Execution successful"):
        return "execution_success"
    if value.startswith("Execution failed"):
        return "execution_failed"
    return "other"


def _error_type(value: str) -> str | None:
    match = re.search(r"(?:^|\n)([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))(?::|$)", value)
    return match.group(1) if match else None


def _error_modules(value: str) -> list[str]:
    return sorted(set(pathlib.Path(item).name for item in re.findall(r'File "([^"]+)"', value)))


def _error_code(value: str) -> int | None:
    match = re.search(r"errno=(-?\d+)", value)
    return int(match.group(1)) if match else None


def _error_storage_flags(value: str) -> dict[str, bool | None]:
    result: dict[str, bool | None] = {}
    for name in ("parent_exists", "absolute"):
        match = re.search(rf"{name}=(True|False)", value)
        result[name] = None if match is None else match.group(1) == "True"
    return result


def _journal_failure(value: str) -> dict[str, Any] | None:
    """Extract only the journal stage/errno/path digest from a traceback."""
    match = re.search(
        r"execution evidence journal ([a-z_]+) failed error_type=([^ ]+) errno=([^ ]+) path_id=([0-9a-f]{64})",
        value,
    )
    if match is None:
        return None
    errno = None if match.group(3) == "None" else int(match.group(3))
    return {"stage": match.group(1), "error_type": match.group(2), "errno": errno, "path_id": match.group(4)}


def _run(*, worker: pathlib.Path, native_python: str, native_root: str, task_id: str,
         enabled: bool, registry: pathlib.Path, registry_sha256: str, journal: pathlib.Path) -> dict[str, Any]:
    env = dict(os.environ); env["APPWORLD_ALLOWED_TASKS"] = task_id
    process = subprocess.Popen([native_python, str(worker)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, cwd=native_root, env=env)
    try:
        start: dict[str, Any] = {"op": "start", "task_id": task_id, "experiment_name": "execution-evidence-fixture"}
        if enabled:
            start["execution_evidence"] = {"registry_path": str(registry), "registry_sha256": registry_sha256,
                                           "journal_path": str(journal)}
        started = _send(process, start)
        public_interface = {
            key: started.get(key)
            for key in ("instruction", "supervisor", "app_descriptions")
        }
        # Public read-only calls exercise direct, loop, conditional, and
        # helper dispatch.  Their response values are never persisted here.
        code = (
            "profile = apis.supervisor.show_profile()\n"
            "for _ in range(2):\n"
            "    apis.supervisor.show_profile()\n"
            "if True:\n"
            "    apis.supervisor.show_profile()\n"
            "def helper():\n"
            "    return apis.supervisor.show_profile()\n"
            "helper()\n"
            "print(profile)"
        )
        action = _send(process, {"op": "action", "program_id": "fixture:action=0",
                                 "code": code})
        score = _send(process, {"op": "score"})
        _send(process, {"op": "finish"})
        process.wait(timeout=30)
        if process.returncode != 0:
            raise RuntimeError("worker exited nonzero")
        return {"score": [int(score["pass_count"]), int(score["fail_count"]), int(score["num_tests"])],
                "native_state_sha256": score["native_state_sha256"],
                "public_interface_sha256": hashlib.sha256(
                    json.dumps(public_interface, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest(),
                "output_sha256": hashlib.sha256(str(action["output"]).encode("utf-8")).hexdigest(),
                "output_class": _output_class(str(action["output"])), "error_type": _error_type(str(action["output"])),
                "error_modules": _error_modules(str(action["output"])), "error_code": _error_code(str(action["output"])),
                "error_storage_flags": _error_storage_flags(str(action["output"])),
                "journal_failure": _journal_failure(str(action["output"])),
                "startup_evidence": started.get("execution_evidence_startup")}
    finally:
        if process.poll() is None:
            process.kill(); process.wait(timeout=10)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", default="82e2fac_1")
    parser.add_argument("--worker", required=True, type=pathlib.Path)
    parser.add_argument("--native-python", default="/home/xiqhq/copromem-appworld/venv/bin/python")
    parser.add_argument("--native-root", default="/home/xiqhq/copromem-appworld")
    parser.add_argument("--registry", required=True, type=pathlib.Path)
    parser.add_argument("--registry-sha256", required=True)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    disabled = _run(worker=args.worker, native_python=args.native_python, native_root=args.native_root,
                    task_id=args.task_id, enabled=False, registry=args.registry,
                    registry_sha256=args.registry_sha256, journal=args.output.with_suffix(".disabled.jsonl"))
    enabled = _run(worker=args.worker, native_python=args.native_python, native_root=args.native_root,
                   task_id=args.task_id, enabled=True, registry=args.registry,
                   registry_sha256=args.registry_sha256, journal=args.output.with_suffix(".events.jsonl"))
    events_path = args.output.with_suffix(".events.jsonl")
    rows = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()] if events_path.exists() else []
    expected_operations = ["apis.supervisor.show_profile"] * 5
    result = {"fixture_task_id": args.task_id, "telemetry_version": "public-execution-evidence-v1",
              "same_public_output": disabled["output_sha256"] == enabled["output_sha256"],
              "output_classes": [disabled["output_class"], enabled["output_class"]],
              "output_error_types": [disabled["error_type"], enabled["error_type"]],
              "output_error_modules": [disabled["error_modules"], enabled["error_modules"]],
              "output_error_codes": [disabled["error_code"], enabled["error_code"]],
              "output_error_storage_flags": [disabled["error_storage_flags"], enabled["error_storage_flags"]],
              "journal_failures": [disabled["journal_failure"], enabled["journal_failure"]],
              "startup_evidence": enabled["startup_evidence"],
              "same_official_score": disabled["score"] == enabled["score"],
              "same_native_state": disabled["native_state_sha256"] == enabled["native_state_sha256"],
              "same_public_interface": disabled["public_interface_sha256"] == enabled["public_interface_sha256"],
              "event_count": len(rows), "operations": [row["operation_signature"]["operation"] for row in rows],
              "expected_operations": expected_operations,
              "exact_nested_call_order": [row["operation_signature"]["operation"] for row in rows] == expected_operations
              and [row["monotonic_index"] for row in rows] == list(range(len(expected_operations))),
              "all_response_attested": all(row["response_success"] and row["schema_accepted"] for row in rows)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if not all(result[key] for key in ("same_public_output", "same_native_state", "same_public_interface",
                                       "same_official_score", "exact_nested_call_order", "all_response_attested")):
        raise RuntimeError("native execution-evidence equivalence failed")


if __name__ == "__main__":
    main()
