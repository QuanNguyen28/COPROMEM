#!/usr/bin/env python3
"""Autonomous, fail-closed launcher for the official-ReMe scaled pilot.

This process owns durable logging and must be started outside Codex. It never
dispatches a paid request unless every static/source/runtime gate passes. The
current pinned-source compatibility gate is deliberately strict: a native-tool
executor and a DeepSeek-only route cannot be silently substituted for the
official AppWorld code-completion protocol or ReMe's required embedding model.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import traceback

ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
ARTIFACTS = ROOT / "artifacts/research/official_reme_copromem_pilot"
RUN_DIR = ARTIFACTS / "reduced_v1"
MANIFEST = RUN_DIR / "manifest.json"
PROGRESS = ARTIFACTS / "progress.jsonl"
STATUS = RUN_DIR / "runner-status.json"
REPORT = RUN_DIR / "FINAL_REPORT.md"
SERVICE_PYTHON = pathlib.Path("/mnt/e/Project/AAMAS/reme-official-service-v3/bin/python")


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def append(record: dict) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"timestamp": now(), **record}, sort_keys=True, separators=(",", ":")) + "\n"
    with PROGRESS.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def write_status(state: str, **extra: object) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATUS.with_suffix(".json.tmp")
    temporary.write_text(json.dumps({"state": state, "pid": os.getpid(), "updated_at": now(),
                                     "progress": str(PROGRESS), "final_report": str(REPORT), **extra},
                                    sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, STATUS)


def c_free_gb() -> float:
    value = subprocess.check_output(["df", "-Pk", "/mnt/c"], text=True).splitlines()[-1].split()[3]
    return int(value) / 1024 / 1024


def conservative_bound(manifest: dict) -> dict:
    executor_calls = (
        len(manifest["acquisition"]["task_ids"]) * manifest["max_actions"]
        + len(manifest["evaluation"]["task_ids"]) * manifest["evaluation"]["trials_per_task"]
        * len(manifest["arms"]) * manifest["max_actions"]
    )
    # Registered upper allowance: all official-ReMe distillation/retrieval/
    # update/pruning and CoProMem decomposition calls. It is intentionally
    # separate from executor calls and cannot be repurposed as retries.
    lifecycle_calls = 400
    per_call = (manifest["route"]["max_input_tokens"] * manifest["budget"]["input_usd_per_million"]
                + manifest["route"]["max_completion_tokens"] * manifest["budget"]["completion_usd_per_million"]) / 1_000_000
    dispatchable = (executor_calls + lifecycle_calls) * per_call
    contingency = dispatchable * manifest["budget"]["contingency_fraction"]
    historical = 0.03131748
    return {"executor_calls": executor_calls, "lifecycle_calls": lifecycle_calls,
            "per_call_usd": per_call, "dispatchable_usd": dispatchable,
            "contingency_usd": contingency, "historical_usd": historical,
            "total_usd": dispatchable + contingency + historical}


def run_gate(name: str, command: list[str]) -> str:
    completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               cwd=ROOT, env={**os.environ, "PYTHONUNBUFFERED": "1"})
    output = completed.stdout[-8000:]
    append({"stage": "preflight", "gate": name, "exit_code": completed.returncode,
            "c_free_gb": round(c_free_gb(), 3), "next_scheduled_work": "next preflight gate"})
    if completed.returncode:
        raise RuntimeError(f"{name} failed (exit {completed.returncode}): {output[-1200:]}")
    return output


def fail(reason: str) -> int:
    # Sanitized: neither command output nor exception trace is persisted if it
    # could contain a route credential. Static gates below have no credentials.
    append({"stage": "preflight", "state": "failed", "error_type": "CompatibilityGateError",
            "error": reason[:1000], "c_free_gb": round(c_free_gb(), 3),
            "next_scheduled_work": "none; explicit protocol revision required"})
    write_status("failed", reason=reason[:1000])
    REPORT.write_text(
        "# Official ReMe–CoProMem scaled pilot — preflight result\n\n"
        "**Status: FAILED before paid dispatch.**\n\n"
        f"Reason: {reason}\n\n"
        "No AppWorld task payload was opened by this launcher and no model request was dispatched. "
        "The pinned official source must not be replaced by the local ReMe adaptation.\n",
        encoding="utf-8",
    )
    return 2


def main() -> int:
    if not MANIFEST.exists():
        return fail("reduced manifest is missing")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    bound = conservative_bound(manifest)
    if bound["total_usd"] >= manifest["budget"]["absolute_usd"]:
        return fail("reduced worst-case budget exceeds USD 35")
    append({"stage": "setup", "state": "started", "completed_trajectories": 0,
            "total_trajectories": 0, "c_free_gb": round(c_free_gb(), 3),
            "budget_bound_usd": round(bound["total_usd"], 8),
            "next_scheduled_work": "deterministic source/runtime preflight"})
    write_status("running", manifest_sha256=__import__("hashlib").sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), budget_bound=bound)
    try:
        if c_free_gb() < 10:
            return fail("C-drive/WSL-root storage floor is below 10 GB")
        route = run_gate("locked-route-compatibility", [str(SERVICE_PYTHON), str(ROOT / "research/scripts/audit_official_reme_route_compatibility.py")])
        if "result=FAIL_CLOSED_ROUTE_ADAPTER_REQUIRED" in route:
            return fail(
                "Official ReMe source uses code-fence AppWorld completion calls with no native tools and requires "
                "an OpenAI-compatible text-embedding-v4 vector-store interface; the locked DeepSeek V4.1 Flash "
                "route is chat/text-only. Continuing would require an unauthorized executor/lifecycle adaptation "
                "or a second model route."
            )
        # Intentionally unreachable unless a future source-compatible route is
        # frozen. A paid run implementation must only be added alongside that
        # revised immutable protocol; this launcher never improvises one.
        return fail("No source-compatible paid route is frozen")
    except Exception as exc:
        return fail(f"deterministic preflight exception: {type(exc).__name__}: {str(exc)[:600]}")


if __name__ == "__main__":
    raise SystemExit(main())
