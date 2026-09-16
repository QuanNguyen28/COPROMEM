"""Bounded offline native-component probes, not published baseline reproduction."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from .checkpoints import RunStore, digest


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    store = RunStore(root / "artifacts/research/reproduction_probe_20260916")
    env = {
        key: value
        for key, value in os.environ.items()
        if not any(
            word in key.upper() for word in ("API_KEY", "TOKEN", "SECRET", "PASSWORD")
        )
    }
    env["MPLBACKEND"] = "Agg"
    commands = [
        (
            "expel_native_help",
            root / "vendor/ExpeL",
            [sys.executable, "train.py", "--help"],
        ),
        (
            "awm_native_scorer",
            root / "vendor/agent-workflow-memory/mind2web",
            [
                sys.executable,
                "results/calc_score.py",
                "--results_dir",
                str(root / "research/fixtures/awm_scores"),
            ],
        ),
    ]
    records = []
    for name, cwd, command in commands:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=cwd, text=True
        ).strip()
        record = {
            "name": name,
            "revision": revision,
            "python": platform.python_version(),
            "command": command,
            "cwd": str(cwd),
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "interpretation": "Native CLI or evaluator component only; no benchmark rollout, baseline induction, paid request or published score reproduction.",
        }
        store.write("probes", digest(record), record)
        records.append(record)
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
