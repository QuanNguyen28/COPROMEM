#!/usr/bin/env python3
"""Conservative durable recovery record for the power-outage interruption."""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import time

ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
RUN = ROOT / "artifacts/research/official_reme_copromem_pilot/reduced_v2"
PROGRESS = ROOT / "artifacts/research/official_reme_copromem_pilot/progress.jsonl"


def append(path: pathlib.Path, data: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n")
        f.flush(); os.fsync(f.fileno())


def main() -> None:
    pid = int((RUN / "runner.pid").read_text().strip())
    alive = subprocess.run(["/bin/kill", "-0", str(pid)], capture_output=True).returncode == 0
    if alive:
        raise RuntimeError("recorded runner PID is still alive; refusing recovery")
    ledger = (RUN / "successor-ledger.jsonl").read_text(encoding="utf-8")
    if ledger.count('"event":"settle"') != 3:  # carry-forward plus two dispatched calls
        raise RuntimeError("unexpected ledger state; refusing recovery")
    key = "acquisition:07b42fd_1:7101"
    completed = RUN / "completed.jsonl"
    old = completed.read_text(encoding="utf-8") if completed.exists() else ""
    if key not in old:
        append(completed, {"key": key, "time_ns": time.time_ns(),
            "state": "interrupted_unresumable_no_replay", "reason": "settled_calls_without_replayable_action_text",
            "journal": "journals/acquisition_07b42fd_1_seed_7101.jsonl"})
    append(PROGRESS, {"event": "recovery_reconciled", "trajectory_id": key,
        "state": "interrupted_unresumable_no_replay", "settled_model_calls": 2,
        "ledger_replayed": False, "time_ns": time.time_ns()})
    lock = RUN / "runner.lock"
    if lock.exists(): lock.unlink()
    print("reduced_v2_recovery=completed")


if __name__ == "__main__": main()
