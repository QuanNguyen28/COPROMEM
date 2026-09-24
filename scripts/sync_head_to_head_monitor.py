#!/usr/bin/env python3
"""Auto-sync daemon for Head-to-Head Nemotron 550B Benchmark.

Continuously monitors results_head_to_head_nemotron for timed-out / unrenamed
directories, renames them, writes minimal summary_info.json, and regenerates
report_head_to_head.md in real time.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from live_monitor import ADMIN100_TASKS, QA86_TASKS
import run_head_to_head_nemotron_100
import importlib


def get_active_running_tids() -> set[str]:
    """Check running python run.py processes to avoid touching actively running tasks."""
    try:
        res = subprocess.run(["ps", "aux"], capture_output=True, text=True)
        running = set()
        for line in res.stdout.splitlines():
            if "run.py" in line and "webarena." in line:
                m = re.search(r"webarena\.(\d+)", line)
                if m:
                    running.add(m.group(1))
        return running
    except Exception:
        return set()


def auto_correct_timeout_summaries(base_dir: Path):
    """Ensure any directory with a timeout has n_steps equal to actual step files."""
    if not base_dir.exists():
        return
    for target_dir in base_dir.iterdir():
        if not target_dir.is_dir() or not target_dir.name.startswith("webarena."):
            continue
        summary = target_dir / "summary_info.json"
        if summary.exists():
            try:
                s_data = json.loads(summary.read_text(encoding="utf-8"))
                if "timed out" in str(s_data.get("err_msg", "")).lower() or s_data.get("n_steps", 0) >= 25:
                    step_files = list(target_dir.glob("step_*.pkl.gz"))
                    if step_files:
                        real_steps = max(len(step_files), 1)
                        if s_data.get("n_steps") != real_steps:
                            s_data["n_steps"] = real_steps
                            summary.write_text(json.dumps(s_data, indent=2), encoding="utf-8")
            except Exception:
                pass


def sync_directory(base_dir: Path, active_tids: set[str]) -> bool:
    """Scan and rename finished timestamped folders."""
    changed = False
    if not base_dir.exists():
        return False

    for child in list(base_dir.iterdir()):
        if child.is_dir() and "_GenericAgentArgs_on_webarena." in child.name:
            m = re.search(r"_on_webarena\.(\d+)_", child.name)
            if m:
                tid = m.group(1)
                # Only touch if this task is NOT actively executing in run.py
                if tid not in active_tids:
                    target_dir = base_dir / f"webarena.{tid}"
                    if not target_dir.exists():
                        try:
                            child.rename(target_dir)
                            summary = target_dir / "summary_info.json"
                            if not summary.exists():
                                steps = len(list(target_dir.glob("step_*.pkl.gz")))
                                summary.write_text(json.dumps({
                                    "cum_reward": 0.0,
                                    "n_steps": max(steps, 1),
                                    "err_msg": "Task timed out after 360s",
                                }, indent=2), encoding="utf-8")
                            changed = True
                        except Exception:
                            pass
    return changed


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--base_results_dir", type=str, default="results_head_to_head_deepseek_v4_1")
    parser.add_argument("--model_name", type=str, default="deepseek/deepseek-v4.1-flash")
    parser.add_argument("--tasks", type=str, default="qa86", choices=["qa86", "admin100"])
    args = parser.parse_args()

    task_order = QA86_TASKS if args.tasks == "qa86" else ADMIN100_TASKS
    base_dir = REPO_ROOT / args.base_results_dir
    copromem_dir = base_dir / "copromem"
    rb_dir = base_dir / "reasoningbank"
    report_file = base_dir / "report_head_to_head.md"

    while True:
        try:
            active_tids = get_active_running_tids()
            sync_directory(copromem_dir, active_tids)
            sync_directory(rb_dir, active_tids)
            auto_correct_timeout_summaries(copromem_dir)
            auto_correct_timeout_summaries(rb_dir)

            # Check active task ID for progress display
            active_info = f"Task {next(iter(active_tids))}..." if active_tids else None

            importlib.reload(run_head_to_head_nemotron_100)
            run_head_to_head_nemotron_100.generate_head_to_head_report(
                report_file=report_file,
                task_order=task_order,
                copromem_dir=copromem_dir,
                rb_dir=rb_dir,
                model_name=args.model_name,
                max_steps=25,
                current_eval_info=active_info,
            )
        except Exception:
            pass
        time.sleep(10)


if __name__ == "__main__":
    main()
