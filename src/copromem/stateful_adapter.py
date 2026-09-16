"""Bounded Docker runner and train-only public AppWorld data export.

This adapter is under validation. Harness state/digests and native evaluator
outputs are not public observations and must never be included in agent prompts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .checkpoints import IntegrityError, RunStore, canonical, digest


def public_observation(result: dict) -> dict:
    """An explicit allowlist; never expose harness state or evaluation labels."""
    return {
        "task_id": result["task_id"],
        "instruction": result["public_instruction"],
        "history": [
            {"program": item["program"], "output": item["output"]}
            for item in result["results"]
        ],
        "completion_flag": result["completion_flag"],
    }


def verify_prefix_pair(
    first: dict, second: dict, *, expected_error_indices: tuple[int, ...] = ()
) -> dict:
    """Reject a comparison unless the tested prefix matches, including failures."""
    if any(
        type(index) is not int or index < 0 for index in expected_error_indices
    ) or len(set(expected_error_indices)) != len(expected_error_indices):
        raise ValueError(
            "expected action-error positions must be distinct nonnegative integers"
        )
    for result in (first, second):
        if result.get("status") != "completed" or not result.get("guards_enabled"):
            raise IntegrityError("worker did not complete under the shared guards")
        if digest(result["harness_only_state"]) != result["state_digest"]:
            raise IntegrityError("worker state digest mismatch")
        if result["harness_only_state"]["namespace"]["unsupported"]:
            raise IntegrityError(
                "unsupported namespace state; checkpoint is unverified"
            )
        observed_errors = {
            index
            for index, item in enumerate(result["results"])
            if item["output"].startswith("Execution failed.")
        }
        if observed_errors != set(expected_error_indices):
            raise IntegrityError(
                "unexpected prefix execution failure or missing recorded action error"
            )
    for key in (
        "task_id",
        "request_id",
        "native_version",
        "state_digest",
        "initial_database_files",
    ):
        if first[key] != second[key]:
            raise IntegrityError("paired prefix mismatch: " + key)
    if public_observation(first) != public_observation(second):
        raise IntegrityError("paired prefix public-observation mismatch")
    return {
        "verified": True,
        "request_id": first["request_id"],
        "state_digest": first["state_digest"],
        "task_id": first["task_id"],
        "scope": "saved diagnostic prefix, not a proof for arbitrary Python state",
        "expected_action_error_indices": list(expected_error_indices),
    }


def prepare_bundle(source: Path, destination: Path, task_ids: list[str]) -> dict:
    source, destination = source.resolve(), destination.resolve()
    if destination.exists():
        raise FileExistsError(
            "public bundle export never overwrites an existing target"
        )
    train_ids = {
        line.strip().split(":")[0]
        for line in (source / "datasets/train.txt").read_text().splitlines()
        if line.strip()
    }
    if (
        not task_ids
        or len(set(task_ids)) != len(task_ids)
        or not set(task_ids) <= train_ids
    ):
        raise ValueError(
            "only distinct explicitly selected train tasks may be exported"
        )
    sources = [source / "api_docs", source / "base_dbs"]
    for task_id in task_ids:
        sources.extend(
            (
                source / "tasks" / task_id / "specs.json",
                source / "tasks" / task_id / "dbs",
            )
        )
    for item in sources:
        if not item.exists() or not item.resolve().is_relative_to(source):
            raise ValueError("missing or out-of-scope native data input")
        if item.is_dir() and any(path.is_symlink() for path in item.rglob("*")):
            raise ValueError("symlinks are not accepted in a public data bundle")
    destination.mkdir(parents=True)
    for item in sources:
        target = destination / "data" / item.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
    files = {
        path.relative_to(destination).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted((destination / "data").rglob("*"))
        if path.is_file()
    }
    manifest = {
        "source": str(source),
        "task_ids": task_ids,
        "split": "train",
        "files": files,
        "ground_truth_exported": False,
        "warning": "Contains native simulator databases for the worker, not extra agent tools. Runtime syntax/guards prohibit implementation access.",
    }
    RunStore(destination).write("manifest", "public_bundle", manifest)
    return manifest


def container_command(
    image_id: str, bundle: Path, output: Path, name: str
) -> list[str]:
    RunStore._validate_components("container", name)
    if not image_id.startswith("sha256:") or len(image_id) != 71:
        raise ValueError("use a locally resolved immutable Docker image ID")
    bundle, output = bundle.resolve(), output.resolve()
    if (
        not (bundle / "data").is_dir()
        or output == bundle
        or output.is_relative_to(bundle)
    ):
        raise ValueError("separate public-data and writable-output roots required")
    return [
        "docker",
        "run",
        "-i",
        "--name",
        name,
        "--label",
        "io.copromem.research=cycle05",
        "--label",
        "io.copromem.output=" + digest(str(output)),
        "--network",
        "none",
        "--read-only",
        "--cpus",
        "2",
        "--memory",
        "2g",
        "--pids-limit",
        "128",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        "10001:10001",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=256m,mode=1777",
        "--tmpfs",
        "/sandbox:rw,noexec,nosuid,size=32m,uid=10001,gid=10001,mode=700",
        "--mount",
        f"type=bind,source={bundle / 'data'},target=/sandbox/data,readonly",
        "--mount",
        f"type=bind,source={output},target=/sandbox/experiments",
        image_id,
    ]


def stop_owned_container(name: str, output: Path) -> dict:
    """Never stop an unrelated container merely because its name collides."""
    inspected = subprocess.run(
        ["docker", "inspect", "--format", "{{json .Config.Labels}}", name],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if inspected.returncode != 0:
        return {"stopped": False, "reason": "container not found"}
    labels = json.loads(inspected.stdout) or {}
    if labels.get("io.copromem.research") != "cycle05" or labels.get(
        "io.copromem.output"
    ) != digest(str(output.resolve())):
        return {"stopped": False, "reason": "ownership mismatch; container untouched"}
    stopped = subprocess.run(
        ["docker", "kill", name],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    return {"stopped": stopped.returncode == 0, "kill_exit_code": stopped.returncode}


def audit_prefix_runs(
    store: RunStore,
    pairs: list[list[str]],
    *,
    expected_error_indices: tuple[int, ...] = (),
) -> dict:
    if store.root is None:
        raise ValueError("persistent run store required")
    checked = []
    for first_id, second_id in pairs:
        first, second = (
            store.read("worker_results", item) for item in (first_id, second_id)
        )
        if first is None or second is None:
            raise IntegrityError("missing paired worker result")
        item = verify_prefix_pair(
            first, second, expected_error_indices=expected_error_indices
        )
        evaluations = [
            store.read("native_evaluation", name) for name in (first_id, second_id)
        ]
        if None in evaluations or evaluations[0] != evaluations[1]:
            raise IntegrityError(
                "native evaluator mismatch or missing independent evaluation"
            )
        for name, result in ((first_id, first), (second_id, second)):
            dbs = (
                store.root
                / "native"
                / name
                / "outputs/canonical/tasks"
                / result["task_id"]
                / "dbs"
            )
            hashes = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(dbs.iterdir())
                if path.is_file()
            }
            if hashes != result["harness_only_state"]["database_files"]:
                raise IntegrityError(
                    "native state changed after worker/evaluator execution"
                )
        commands = [
            store.read("worker_commands", name)["command"]
            for name in (first_id, second_id)
        ]
        images = [
            next(value for value in command if value.startswith("sha256:"))
            for command in commands
        ]
        if images[0] != images[1]:
            raise IntegrityError("paired workers used different immutable images")
        checked.append(
            {
                **item,
                "runs": [first_id, second_id],
                "native_evaluation": evaluations[0],
                "image_id": images[0],
            }
        )
    report = {
        "audit": "stateful-prefix-diagnostic-v1",
        "pairs": checked,
        "model_calls": 0,
        "claim": "bounded adapter evidence, not learned-method efficacy",
    }
    store.write("prefix_audits", digest(report), report)
    return report


def run_worker(
    image_id: str, bundle: Path, store: RunStore, run_id: str, request: dict
) -> dict:
    RunStore._validate_components("runs", run_id)
    if store.root is None:
        raise ValueError("persistent worker evidence required")
    name = "copromem-c05-" + run_id
    output = (store.root.resolve() / "native" / run_id).resolve()
    if not output.is_relative_to(store.root.resolve()) or output.exists():
        raise ValueError("worker output must be a new in-scope directory")
    manifest = RunStore(bundle).read("manifest", "public_bundle")
    if manifest is None or request.get("task_id") not in manifest["task_ids"]:
        raise ValueError("task not in the declared train-only public bundle")
    store.write("worker_requests", run_id, request)
    output.mkdir(parents=True)
    command = container_command(image_id, bundle, output, name)
    store.write(
        "worker_commands", run_id, {"command": command, "request_id": digest(request)}
    )
    try:
        completed = subprocess.run(
            command,
            input=canonical(request),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=90,
            check=False,
        )
        record: dict[str, Any] = {
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        # Docker CLI termination does not necessarily stop its container.
        record = {
            "exit_code": None,
            "timed_out": True,
            "stop_result": stop_owned_container(name, output),
        }
    inspected = subprocess.run(
        ["docker", "inspect", "--format", "{{json .State}}", name],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    record["container_state"] = (
        json.loads(inspected.stdout) if inspected.returncode == 0 else None
    )
    store.write("worker_processes", run_id, record)
    if record["exit_code"] == 0:
        prefix = "COPROMEM_WORKER_RESULT="
        lines = [
            line[len(prefix) :]
            for line in record["stdout"].splitlines()
            if line.startswith(prefix)
        ]
        if len(lines) != 1:
            raise IntegrityError("worker did not produce exactly one result")
        result = json.loads(lines[0])
        if result["request_id"] != digest(request):
            raise IntegrityError("worker request/result mismatch")
        store.write("worker_results", run_id, result)
        return result
    return {"status": "worker_failed", "run_id": run_id, "process": record}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    bundle = commands.add_parser("export")
    bundle.add_argument("--source", type=Path, required=True)
    bundle.add_argument("--destination", type=Path, required=True)
    bundle.add_argument("--task-id", action="append", required=True)
    run = commands.add_parser("run")
    run.add_argument("--image-id", required=True)
    run.add_argument("--bundle", type=Path, required=True)
    run.add_argument("--store", type=Path, required=True)
    run.add_argument("--run-id", required=True)
    run.add_argument("--request", type=Path, required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--image-id", required=True)
    evaluate.add_argument("--native-data", type=Path, required=True)
    evaluate.add_argument("--store", type=Path, required=True)
    evaluate.add_argument("--run-id", required=True)
    evaluate.add_argument("--task-id", required=True)
    audit = commands.add_parser("audit")
    audit.add_argument("--store", type=Path, required=True)
    audit.add_argument("--pair", nargs=2, action="append", required=True)
    audit.add_argument("--expected-error-index", action="append", type=int, default=[])
    args = parser.parse_args()
    if args.command == "export":
        manifest = prepare_bundle(args.source, args.destination, args.task_id)
        print(
            json.dumps(
                {
                    "files": len(manifest["files"]),
                    "tasks": manifest["task_ids"],
                    "ground_truth_exported": False,
                }
            )
        )
    elif args.command == "run":
        result = run_worker(
            args.image_id,
            args.bundle,
            RunStore(args.store),
            args.run_id,
            json.loads(args.request.read_text(encoding="utf-8")),
        )
        print(json.dumps(result, indent=2))
        if result["status"] != "completed":
            raise SystemExit(1)
    elif args.command == "evaluate":
        result = evaluate_worker_output(
            args.image_id,
            args.native_data,
            RunStore(args.store),
            args.run_id,
            args.task_id,
        )
        print(json.dumps(result, indent=2))
    else:
        print(
            json.dumps(
                audit_prefix_runs(
                    RunStore(args.store),
                    args.pair,
                    expected_error_indices=tuple(args.expected_error_index),
                ),
                indent=2,
            )
        )


def evaluate_worker_output(
    image_id: str, native_data: Path, store: RunStore, run_id: str, task_id: str
) -> dict:
    RunStore._validate_components("runs", run_id)
    request = store.read("worker_requests", run_id)
    result = store.read("worker_results", run_id)
    if (
        store.root is None
        or request is None
        or result is None
        or request["task_id"] != task_id
    ):
        raise ValueError("evaluator requires a completed matching worker run")
    name = "copromem-c05-eval-" + run_id
    output = store.root.resolve() / "native" / run_id
    if not output.is_dir() or not (native_data / "datasets/train.txt").is_file():
        raise ValueError("missing native output or dataset")
    # Reuse the same containment profile but mount evaluator inputs read-only.
    command = container_command(image_id, native_data.parent, output, name)
    data_index = next(
        i for i, value in enumerate(command) if "target=/sandbox/data," in value
    )
    command[data_index] = (
        f"type=bind,source={native_data.resolve()},target=/sandbox/data,readonly"
    )
    output_index = next(
        i for i, value in enumerate(command) if "target=/sandbox/experiments" in value
    )
    command[output_index] += ",readonly"
    command[-1:-1] = ["--entrypoint", "python"]
    command.append("/opt/copromem-evaluator.py")
    store.write(
        "evaluator_commands",
        run_id,
        {"command": command, "agent_actions_accepted": False},
    )
    try:
        completed = subprocess.run(
            command,
            input=canonical({"task_id": task_id}),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=90,
            check=False,
        )
        record = {
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except subprocess.TimeoutExpired:
        record = {
            "exit_code": None,
            "timeout": True,
            "stop_result": stop_owned_container(name, output),
        }
    store.write("evaluator_processes", run_id, record)
    if record["exit_code"] != 0:
        raise RuntimeError("native evaluator failed; saved process record retained")
    prefix = "COPROMEM_EVALUATOR_RESULT="
    lines = [
        line[len(prefix) :]
        for line in record["stdout"].splitlines()
        if line.startswith(prefix)
    ]
    if len(lines) != 1:
        raise IntegrityError("missing or ambiguous native evaluator result")
    summary = json.loads(lines[0])
    if summary["task_id"] != task_id or summary["agent_visible"]:
        raise IntegrityError("native evaluator result/task mismatch")
    store.write("native_evaluation", run_id, summary)
    return summary


if __name__ == "__main__":
    main()
