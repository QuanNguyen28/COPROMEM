#!/usr/bin/env python3
"""Verify the pinned AppWorld ReMe HTTP route set without model dispatch."""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import time
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parents[2]
RUN = pathlib.Path(os.environ.get(
    "OFFICIAL_REME_CONTRACT_RUN",
    ROOT / "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v1/pinned_service_contract",
))
PYTHON = os.environ.get(
    "OFFICIAL_REME_PYTHON",
    "/mnt/e/Project/AAMAS/reme-upstream-fixed-dynamic/bin/python",
)
PORT = 18113


def main() -> None:
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "resolved-python").write_text(PYTHON + "\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(ROOT), "OFFICIAL_REME_PORT": str(PORT),
           "OFFICIAL_REME_RUN_DIR": str(RUN / "runtime"),
           "OFFICIAL_REME_PROGRESS": str(RUN / "progress.jsonl"),
           "OFFICIAL_REME_LEDGER": str(RUN / "ledger.jsonl"),
           "OFFICIAL_PILOT_HARD_CAP": "140"}
    with (RUN / "service.log").open("a", encoding="utf-8") as log:
        proc = subprocess.Popen([PYTHON, "-m", "research.official_pilot.corrected_reme_service"],
                                cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError(f"pinned service exited: {proc.returncode}")
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(1)
            else:
                raise RuntimeError("pinned service health timeout")
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/openapi.json", timeout=5) as response:
                paths = set(json.loads(response.read().decode("utf-8")).get("paths", {}))
            expected = {"/summary_task_memory", "/retrieve_task_memory", "/add_task_memory",
                        "/record_task_memory", "/delete_task_memory", "/load_memory", "/dump_memory"}
            missing = expected - paths
            if missing:
                raise RuntimeError(f"pinned AppWorld ReMe routes missing: {sorted(missing)}")
            if (RUN / "ledger.jsonl").exists() and (RUN / "ledger.jsonl").read_text(encoding="utf-8").strip():
                raise RuntimeError("zero-model contract test unexpectedly spent provider calls")
            print("pinned_reme_appworld_contract=passed", flush=True)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill(); proc.wait(timeout=5)


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        RUN.mkdir(parents=True, exist_ok=True)
        (RUN / "exit-status").write_text(
            f"failed: {type(exc).__name__}: {exc}\n", encoding="utf-8"
        )
        raise
    else:
        (RUN / "exit-status").write_text("passed\n", encoding="utf-8")
