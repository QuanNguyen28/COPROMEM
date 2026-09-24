#!/usr/bin/env python3
"""ReasoningBank & COPROMEM Benchmark Evaluation Harness.

Orchestrates official ReasoningBank agent execution across WebArena tasks,
integrating COPROMEM 2.0 cognitive memory, negative transfer veto,
and task milestone decomposition with automated memory induction.
Continuously syncs live evaluation progress to the benchmark markdown report.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

# Setup paths
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
WEBARENA_DIR = REPO_ROOT / "external" / "reasoning-bank" / "WebArena"
CONFIG_DIR = WEBARENA_DIR / "config_files"

sys.path.insert(0, str(SCRIPT_DIR))
from live_monitor import ADMIN100_TASKS, MINI30_TASKS, update_markdown_report_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("BenchmarkRunner")


def ensure_env():
    """Ensure all required WebArena and OpenRouter environment variables are configured."""
    os.environ.setdefault("WA_SHOPPING_ADMIN", "http://localhost:7780/admin")
    os.environ.setdefault("WA_SHOPPING", "http://localhost:7780")
    os.environ.setdefault("WA_REDDIT", "http://localhost:9999")
    os.environ.setdefault("WA_GITLAB", "http://localhost:8023")
    os.environ.setdefault("WA_WIKIPEDIA", "http://localhost:8060")
    os.environ.setdefault("WA_MAP", "http://localhost:8086")
    os.environ.setdefault("WA_HOMEPAGE", "http://localhost:80")

    os.environ.setdefault("SHOPPING_ADMIN", "http://localhost:7780/admin")
    os.environ.setdefault("SHOPPING", "http://localhost:7780")
    os.environ.setdefault("REDDIT", "http://localhost:9999")
    os.environ.setdefault("GITLAB", "http://localhost:8023")
    os.environ.setdefault("WIKIPEDIA", "http://localhost:8060")
    os.environ.setdefault("MAP", "http://localhost:8086")
    os.environ.setdefault("HOMEPAGE", "http://localhost:80")

    if not os.getenv("OPENROUTER_API_KEY"):
        env_file = REPO_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("OPENROUTER_API_KEY="):
                    os.environ["OPENROUTER_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

    if os.getenv("OPENROUTER_API_KEY"):
        os.environ.setdefault("OPENAI_API_KEY", os.environ["OPENROUTER_API_KEY"])
    os.environ.setdefault("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    os.environ.setdefault("OPENAI_JUDGE_MODEL", "openai/gpt-4o-mini")


def get_available_tasks(site: str | None = None) -> list[int]:
    """Retrieve list of valid task IDs, optionally filtered by site."""
    tasks = []
    for cfg_file in sorted(CONFIG_DIR.glob("*.json"), key=lambda p: int(p.stem)):
        try:
            cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
            if site is None or site in cfg.get("sites", []):
                tasks.append(int(cfg_file.stem))
        except Exception:
            continue
    return tasks


def run_task(
    task_id: int,
    model_name: str,
    memory_mode: str,
    results_dir: Path,
    max_steps: int = 25,
    headless: bool = True,
    memory_path: str | None = None,
) -> dict:
    """Run a single WebArena task through the official ReasoningBank runner."""
    ensure_env()
    task_name = f"webarena.{task_id}"
    cmd = [
        sys.executable,
        str(WEBARENA_DIR / "run.py"),
        "--task_name", task_name,
        "--model_name", model_name,
        "--memory_mode", memory_mode,
        "--max_steps", str(max_steps),
        "--headless", str(headless),
        "--results_path", str(results_dir),
    ]
    if memory_path:
        cmd.extend(["--memory_path", str(memory_path)])

    logger.info(f"==> Launching Task {task_name} (memory_mode={memory_mode})...")
    start_time = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(WEBARENA_DIR),
            capture_output=True,
            text=True,
            env=os.environ.copy(),
            timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error(f"Task {task_name} timed out after 300 seconds. Killing process...")
        try:
            subprocess.run(["pkill", "-f", f"webarena.{task_id}"], stderr=subprocess.DEVNULL)
            subprocess.run(["pkill", "-f", "chromium.*--headless"], stderr=subprocess.DEVNULL)
        except Exception:
            pass
        return {
            "task_id": task_id,
            "task_name": task_name,
            "reward": 0.0,
            "success": False,
            "steps": max_steps,
            "elapsed_seconds": 300.0,
            "err_msg": "Task timed out after 300s",
            "stdout": (exc.stdout[-1000:] if exc.stdout else "") if hasattr(exc, "stdout") else "",
        }
    elapsed = time.time() - start_time

    # Clean up lingering headless browser processes to prevent memory leak and Target Crashed
    try:
        subprocess.run(["pkill", "-f", "chromium.*--headless"], stderr=subprocess.DEVNULL)
    except Exception:
        pass

    # Inspect summary_info.json
    task_result_dir = results_dir / task_name
    summary_file = task_result_dir / "summary_info.json"
    reward = 0.0
    steps = 0
    err_msg = None

    if summary_file.exists():
        try:
            summary_data = json.loads(summary_file.read_text(encoding="utf-8"))
            reward = float(summary_data.get("cum_reward", 0.0))
            steps = int(summary_data.get("n_steps", 0))
            err_msg = summary_data.get("err_msg")
        except Exception as e:
            logger.warning(f"Error reading summary for {task_name}: {e}")
    else:
        logger.warning(f"No summary_info.json found for {task_name}")
        err_msg = proc.stderr[-500:] if proc.stderr else "Process terminated without summary"

    return {
        "task_id": task_id,
        "task_name": task_name,
        "reward": reward,
        "success": (reward == 1.0),
        "steps": steps,
        "elapsed_seconds": elapsed,
        "err_msg": err_msg,
        "stdout": proc.stdout[-1000:] if proc.stdout else "",
    }


def induce_memory_for_task(
    task_id: int,
    model_name: str,
    memory_mode: str,
    results_dir: Path,
    output_jsonl: Path,
) -> bool:
    """Induce memory item from task trajectory and append to output JSONL."""
    induce_script = WEBARENA_DIR / "induce_memory.py"
    cmd = [
        sys.executable,
        str(induce_script),
        "--result_dir", str(results_dir),
        "--task", f"webarena.{task_id}",
        "--criteria", "gt",
        "--model", model_name,
        "--memory_mode", memory_mode,
        "--output_path", str(output_jsonl),
    ]
    logger.info(f"Inducing memory for webarena.{task_id} into {output_jsonl}...")
    proc = subprocess.run(cmd, cwd=str(WEBARENA_DIR), capture_output=True, text=True, env=os.environ.copy())
    if proc.returncode == 0:
        logger.info(f"Successfully induced memory for webarena.{task_id}")
        return True
    else:
        logger.warning(f"Failed to induce memory: {proc.stderr[:300]}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Run ReasoningBank & COPROMEM Benchmark")
    parser.add_argument(
        "--memory_mode",
        type=str,
        default="copromem",
        choices=["copromem", "reasoningbank", "no_memory"],
        help="Memory architecture to evaluate.",
    )
    parser.add_argument(
        "--model_name",
        type=str,
        default="google/gemini-2.5-flash",
        help="Model name to run.",
    )
    parser.add_argument(
        "--judge_model",
        type=str,
        default="openai/gpt-4o-mini",
        help="Judge model for LLM fuzzy match.",
    )
    parser.add_argument(
        "--tasks",
        type=str,
        default="mini30",
        help="'mini30', 'shopping_admin', range '41-45', or comma-separated task IDs.",
    )
    parser.add_argument(
        "--results_dir",
        type=str,
        default="results_test_benchmark",
        help="Directory to store evaluation results.",
    )
    parser.add_argument(
        "--report_file",
        type=str,
        default="results_test_benchmark/report_copromem.md",
        help="Markdown report path to overwrite live.",
    )
    parser.add_argument(
        "--memories_dir",
        type=str,
        default=None,
        help="Directory where induced memories are stored.",
    )
    parser.add_argument(
        "--max_steps",
        type=int,
        default=25,
        help="Max steps per task.",
    )
    parser.add_argument(
        "--induce_memory",
        action="store_true",
        default=True,
        help="Whether to automatically induce memory on task success.",
    )
    parser.add_argument(
        "--skip_completed",
        action="store_true",
        default=True,
        help="Skip tasks that have already been evaluated in results_dir.",
    )
    parser.add_argument(
        "--rerun",
        action="store_true",
        default=False,
        help="Force re-run of already completed tasks.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run browser in headless mode.",
    )
    args = parser.parse_args()

    ensure_env()

    # Determine tasks to run
    suite_name = "custom"
    if args.tasks == "mini30":
        task_ids = list(MINI30_TASKS)
        report_task_order = list(MINI30_TASKS)
        suite_name = "mini30"
    elif args.tasks in ("admin100", "test100", "100"):
        task_ids = list(ADMIN100_TASKS)
        report_task_order = list(ADMIN100_TASKS)
        suite_name = "admin100"
    elif args.tasks == "shopping_admin":
        task_ids = get_available_tasks("shopping_admin")
        report_task_order = task_ids
        suite_name = "shopping_admin"
    elif "-" in args.tasks:
        start_id, end_id = map(int, args.tasks.split("-"))
        task_ids = list(range(start_id, end_id + 1))
        if set(task_ids).issubset(set(ADMIN100_TASKS)):
            report_task_order = list(ADMIN100_TASKS)
            suite_name = "admin100"
        elif set(task_ids).issubset(set(MINI30_TASKS)):
            report_task_order = list(MINI30_TASKS)
            suite_name = "mini30"
        else:
            report_task_order = task_ids
    else:
        task_ids = [int(t.strip()) for t in args.tasks.split(",") if t.strip()]
        if set(task_ids).issubset(set(ADMIN100_TASKS)):
            report_task_order = list(ADMIN100_TASKS)
            suite_name = "admin100"
        elif set(task_ids).issubset(set(MINI30_TASKS)):
            report_task_order = list(MINI30_TASKS)
            suite_name = "mini30"
        else:
            report_task_order = task_ids

    results_dir = REPO_ROOT / args.results_dir
    results_dir.mkdir(parents=True, exist_ok=True)

    report_file = REPO_ROOT / args.report_file
    report_file.parent.mkdir(parents=True, exist_ok=True)

    mem_dir = Path(args.memories_dir) if args.memories_dir else WEBARENA_DIR / f"memories_{args.memory_mode}"
    mem_dir.mkdir(parents=True, exist_ok=True)
    mem_jsonl = mem_dir / "shopping_admin.jsonl"

    logger.info(f"Starting Benchmark: {len(task_ids)} tasks | Mode: {args.memory_mode} | Model: {args.model_name}")
    logger.info(f"Results Dir: {results_dir}")
    logger.info(f"Report File: {report_file}")
    logger.info(f"Memories JSONL: {mem_jsonl}")

    # Initial flush to report file
    update_markdown_report_file(
        report_file=report_file,
        task_order=report_task_order,
        results_dir=results_dir,
        suite_name=suite_name,
        model_name=args.model_name,
        judge_model=args.judge_model,
        memory_mode=args.memory_mode,
        max_steps=args.max_steps,
    )

    skip = args.skip_completed and not args.rerun

    for idx, tid in enumerate(task_ids, 1):
        task_done_file = results_dir / f"webarena.{tid}" / "summary_info.json"
        if skip and task_done_file.exists():
            logger.info(f"[{idx}/{len(task_ids)}] Task {tid} already evaluated. Skipping execution.")
            continue

        logger.info(f"[{idx}/{len(task_ids)}] Executing Task {tid}...")
        # Update live monitor report to show task is evaluating
        update_markdown_report_file(
            report_file=report_file,
            task_order=report_task_order,
            results_dir=results_dir,
            current_task_id=tid,
            current_status="evaluating...",
            suite_name=suite_name,
            model_name=args.model_name,
            judge_model=args.judge_model,
            memory_mode=args.memory_mode,
            max_steps=args.max_steps,
        )

        res = run_task(
            task_id=tid,
            model_name=args.model_name,
            memory_mode=args.memory_mode,
            results_dir=results_dir,
            max_steps=args.max_steps,
            headless=args.headless,
        )

        if res["success"]:
            logger.info(f"✓ Task {tid} SUCCEEDED (Steps: {res['steps']}, Time: {res['elapsed_seconds']:.1f}s)")
        else:
            logger.info(f"✗ Task {tid} FAILED (Reward: {res['reward']}, Steps: {res['steps']})")

        # Update live monitor report with finished task (and persist judge assessment)
        update_markdown_report_file(
            report_file=report_file,
            task_order=report_task_order,
            results_dir=results_dir,
            current_task_id=None,
            suite_name=suite_name,
            model_name=args.model_name,
            judge_model=args.judge_model,
            memory_mode=args.memory_mode,
            max_steps=args.max_steps,
        )

        if args.induce_memory and args.memory_mode in ("copromem", "reasoningbank"):
            induce_memory_for_task(
                task_id=tid,
                model_name=args.model_name,
                memory_mode=args.memory_mode,
                results_dir=results_dir,
                output_jsonl=mem_jsonl,
            )

    logger.info(f"Benchmark finished! Final report available at {report_file}")


if __name__ == "__main__":
    main()
