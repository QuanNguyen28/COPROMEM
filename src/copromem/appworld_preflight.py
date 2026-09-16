"""Native train-only AppWorld state probe with reviewed actions and no LLM calls.

This is not a benchmark agent or an AppWorld score. No arbitrary generated code
is executed. Native database checkpoints are deliberately tested separately from
Python interpreter state and simulated time.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .checkpoints import RunStore, digest


def read_clock(world) -> str:
    """Reject execution-error strings instead of mistaking equal errors for time."""
    value = world.execute("print(datetime.datetime.now().isoformat())").strip()
    datetime.fromisoformat(value)
    return value


def run_probe(root: Path, run_id: str, mode: str = "restore") -> dict:
    root = root.resolve()
    RunStore._validate_components("runs", run_id)
    os.environ["APPWORLD_ROOT"] = str(root)
    os.environ["APPWORLD_CACHE"] = str(
        root / ("cache-linux" if sys.platform == "linux" else "cache")
    )
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    from appworld import AppWorld, load_task_ids

    task_id = min(load_task_ids("train"))
    store = RunStore(root / "preflight_records")
    policy = {
        "run_id": run_id,
        "task_id": task_id,
        "split": "train",
        "package_version": importlib.metadata.version("appworld"),
        "selection": "lexicographically first train task ID, no outcome selection",
        "model_calls": 0,
        "arbitrary_generated_code": False,
        "scope": "native reset, database restore, interpreter and clock state only",
        "mode": mode,
    }
    store.write("protocol", run_id, policy)

    def new_world(suffix):
        name = f"{run_id}-{suffix}"
        target = (root / "experiments" / "outputs" / name / "tasks" / task_id).resolve()
        if (
            not target.is_relative_to(root / "experiments" / "outputs")
            or target.exists()
        ):
            raise ValueError(
                "native initialization must not clear an existing or out-of-scope run"
            )
        return AppWorld(
            task_id=task_id,
            experiment_name=name,
            load_ground_truth=False,
            random_seed=100,
            max_interactions=20,
            timeout_seconds=15,
            raise_on_unsafe_syntax=True,
            null_patch_unsafe_execution=True,
        )

    phase = "initialize-first"
    try:
        with new_world("first") as world:
            initial = world.execute("print(apis.supervisor.show_active_task())")
            if mode == "fresh":
                namespace_before = world.execute("print(probe_counter)")
                world.execute("probe_counter = 1")
                observations = {
                    "initial_public_state": initial,
                    "namespace_before_prefix": namespace_before,
                    "counter_after_prefix": world.execute("print(probe_counter)"),
                    "clock_after_prefix": read_clock(world),
                    "completion_after_prefix": world.task_completed(),
                }
                # Preserve diagnostics outside process-global AppWorld guards.
                print("COPRO_PREFLIGHT_PARTIAL=" + json.dumps(observations), flush=True)
                phase = "close-fresh-world"
                report = {
                    **policy,
                    "status": "fresh_prefix_probe_completed",
                    "observations": observations,
                    "fingerprint": digest(observations),
                    "safety_guards_enabled": True,
                    "interpretation": "Compare across separate process runs; prefix replay feasibility only, not a complete checkpoint or quality claim.",
                }
            else:
                phase = "save-state"
                world.execute("probe_counter = 1")
                time_before = read_clock(world)
                saved = world.save_state("before_completion")
                world.execute(
                    "probe_counter = 2\nprint(apis.supervisor.complete_task())"
                )
                completed_after_mutation = world.task_completed()
                phase = "restore-state"
                world.load_state(saved)
                completed_after_restore = world.task_completed()
                counter_after_restore = world.execute("print(probe_counter)")
                time_after = read_clock(world)
                print(
                    "COPRO_PREFLIGHT_PARTIAL="
                    + json.dumps(
                        {
                            "initial_public_state": initial,
                            "completion_after_mutation": completed_after_mutation,
                            "completion_after_restore": completed_after_restore,
                            "counter_after_restore": counter_after_restore,
                            "time_before": time_before,
                            "time_after": time_after,
                        }
                    ),
                    flush=True,
                )
                phase = "close-restored-world"
        if mode == "fresh":
            if (
                "instruction" not in json.loads(initial)
                or "NameError" not in namespace_before
                or observations["counter_after_prefix"].strip() != "1"
                or observations["completion_after_prefix"]
            ):
                raise ValueError("fresh prefix invariants did not pass")
            store.write("reports", digest(report), report)
            return report
        phase = "initialize-independent-world"
        with new_world("second") as world:
            independently_reset = world.execute(
                "print(apis.supervisor.show_active_task())"
            )
            fresh_namespace = world.execute("print(probe_counter)")
        report = {
            **policy,
            "status": "probe_completed",
            "initial_public_state": initial,
            "fresh_world_reproduces_public_state": initial == independently_reset,
            "completion_after_mutation": completed_after_mutation,
            "completion_after_restore": completed_after_restore,
            "database_restore_pass": completed_after_mutation
            and not completed_after_restore,
            "counter_after_restore": counter_after_restore,
            "interpreter_restore_pass": counter_after_restore.strip() == "1",
            "fresh_world_namespace": fresh_namespace,
            "time_before": time_before,
            "time_after": time_after,
            "clock_restore_pass": time_before == time_after,
            "safety_guards_enabled": True,
            "interpretation": "A database-only checkpoint is not a full agent-state checkpoint unless interpreter, clock and other mutable state also restore. No quality claim.",
        }
    except Exception as exc:
        # The environment can leave process-global file guards active on failure.
        # An unmodified parent process must persist this evidence.
        print(f"COPRO_PREFLIGHT_FAILURE phase={phase} type={type(exc).__name__}")
        raise
    store.write("reports", digest(report), report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mode", choices=("restore", "fresh"), default="restore")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        print(
            "COPRO_PREFLIGHT_RESULT="
            + json.dumps(run_probe(args.root, args.run_id, args.mode))
        )
        return
    RunStore._validate_components("runs", args.run_id)
    env = {
        key: value
        for key, value in os.environ.items()
        if not any(
            word in key.upper() for word in ("API_KEY", "TOKEN", "SECRET", "PASSWORD")
        )
    }
    # AppWorld imports python-dotenv; otherwise it can reload the repo's .env
    # after the parent removes credentials. This diagnostic needs no secrets.
    env["PYTHON_DOTENV_DISABLED"] = "1"
    command = [
        sys.executable,
        "-m",
        "copromem.appworld_preflight",
        "--root",
        str(args.root),
        "--run-id",
        args.run_id,
        "--mode",
        args.mode,
        "--child",
    ]
    try:
        completed = subprocess.run(
            command,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=55,
            check=False,
        )
        record = {
            "command": command,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except subprocess.TimeoutExpired:
        record = {"command": command, "exit_code": None, "error_type": "TimeoutExpired"}
    RunStore(args.root / "preflight_records").write("supervisor", args.run_id, record)
    print(json.dumps(record, indent=2))
    if record["exit_code"] != 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
