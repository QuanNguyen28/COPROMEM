#!/usr/bin/env python3
"""Interleaved COPROMEM vs ReasoningBank WebArena Shopping Admin benchmark.

Both arms use the same patched BrowserGym harness; model and task suite are
selected at runtime. Prompt-contract guidance is disabled by default.
"""

from __future__ import annotations

import argparse
import datetime
import gzip
import json
import logging
import os
import pickle
import re
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Setup paths
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
WEBARENA_DIR = REPO_ROOT / "external" / "reasoning-bank" / "WebArena"
CONFIG_DIR = WEBARENA_DIR / "config_files"

sys.path.insert(0, str(SCRIPT_DIR))
from live_monitor import ADMIN100_TASKS, EASY_MEDIUM30_TASKS, MINI30_TASKS

QA86_MANIFEST = REPO_ROOT / "benchmark_tasks_pure_qa_86.json"
REPORT_NOTES_MARKER = "<!-- MANUAL_REPORT_NOTES -->"


def load_qa86_continuation_tasks() -> list[int]:
    """Keep the completed 30-task order, then run the remaining manifest tasks."""
    tasks = json.loads(QA86_MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(tasks, list) or not tasks:
        raise ValueError(f"Expected a non-empty task list in {QA86_MANIFEST}")
    task_ids = [task["task_id"] for task in tasks]
    if any(not isinstance(task_id, int) for task_id in task_ids):
        raise ValueError(f"Task IDs in {QA86_MANIFEST} must be integers")
    if len(task_ids) != len(set(task_ids)):
        raise ValueError(f"Duplicate task IDs in {QA86_MANIFEST}")
    if not set(EASY_MEDIUM30_TASKS).issubset(task_ids):
        raise ValueError("The QA manifest must contain every completed easy_medium30 task")
    completed = set(EASY_MEDIUM30_TASKS)
    return EASY_MEDIUM30_TASKS + [task_id for task_id in task_ids if task_id not in completed]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("HeadToHeadNemotron")


def ensure_env():
    """Ensure all required WebArena environment variables are configured."""
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
                    key = line.split("=", 1)[1].strip("\"'")
                    os.environ["OPENROUTER_API_KEY"] = key
                    logger.info("Loaded OPENROUTER_API_KEY from .env")
                    break


def get_task_intent(task_id: int) -> str:
    """Retrieve task intent text from config file."""
    config_file = CONFIG_DIR / f"{task_id}.json"
    if config_file.exists():
        try:
            data = json.loads(config_file.read_text(encoding="utf-8"))
            return data.get("intent", f"Task {task_id}")
        except Exception:
            pass
    return f"Task {task_id}"


def load_recorded_actions(results_dir: Path, task_id: int) -> list[str]:
    """Read actions from this run's own BrowserGym step artifacts."""
    task_dir = results_dir / f"webarena.{task_id}"
    actions: list[str] = []
    for path in sorted(task_dir.glob("step_*.pkl.gz"),
                       key=lambda item: int(re.search(r"step_(\d+)", item.name).group(1))):
        with gzip.open(path, "rb") as handle:
            step = pickle.load(handle)
        action = getattr(step, "agent_info", {}).get("action", "")
        if action:
            actions.append(str(action))
    return actions


def run_single_task(
    task_id: int,
    model_name: str,
    memory_mode: str,
    results_dir: Path,
    memory_path: Path,
    max_steps: int = 25,
    headless: bool = True,
    timeout_seconds: int = 300,
    contract_guidance: bool = False,
) -> dict[str, Any]:
    """Execute a single task with the given memory architecture and record stats."""
    task_name = f"webarena.{task_id}"
    run_script = WEBARENA_DIR / "run.py"

    cmd = [
        sys.executable,
        str(run_script),
        "--task_name", task_name,
        "--action_space", "bid",
        "--model_name", model_name,
        "--memory_mode", memory_mode,
        "--max_steps", str(max_steps),
        "--slow_mo", "0",
        "--headless", str(headless),
        "--results_path", str(results_dir),
        "--memory_path", str(memory_path),
        "--multi_actions", "True",
        "--use_thinking", "True",
        "--use_past_thought_history", "False",
    ]

    logger.info(f"[{memory_mode.upper()}] Starting {task_name}...")
    start_time = time.time()
    task_env = os.environ.copy()
    task_env["COPROMEM_CONTRACT_GUIDANCE"] = str(
        bool(contract_guidance) if memory_mode == "copromem" else False
    ).lower()
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(WEBARENA_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=task_env,
            start_new_session=True,
        )
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        logger.error(f"[{memory_mode.upper()}] Task {task_name} timed out after {timeout_seconds}s. Terminating process...")
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.communicate(timeout=10)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
        # Find and rename lingering timestamped directory to webarena.{task_id}
        task_result_dir = results_dir / task_name
        if not task_result_dir.exists():
            for child in results_dir.iterdir():
                if child.is_dir() and f"_on_{task_name}_" in child.name:
                    try:
                        child.rename(task_result_dir)
                        break
                    except Exception:
                        pass
        task_result_dir.mkdir(parents=True, exist_ok=True)
        summary_file = task_result_dir / "summary_info.json"
        actual_steps = len(list(task_result_dir.glob("step_*.pkl.gz")))
        recorded_steps = max(actual_steps, 1)
        if not summary_file.exists():
            summary_file.write_text(json.dumps({
                "cum_reward": 0.0,
                "n_steps": recorded_steps,
                "err_msg": f"Task timed out after {timeout_seconds}s",
            }, indent=2), encoding="utf-8")

        return {
            "task_id": task_id,
            "reward": 0.0,
            "success": False,
            "steps": recorded_steps,
            "elapsed": float(timeout_seconds),
            "err_msg": f"Task timed out after {timeout_seconds}s",
        }

    elapsed = time.time() - start_time

    summary_file = results_dir / task_name / "summary_info.json"
    reward = 0.0
    steps = 0
    err_msg = None

    if summary_file.exists():
        try:
            data = json.loads(summary_file.read_text(encoding="utf-8"))
            reward = float(data.get("cum_reward", 0.0))
            steps = int(data.get("n_steps", 0))
            err_msg = data.get("err_msg")
        except Exception as e:
            err_msg = f"Error reading summary: {e}"
    else:
        err_msg = stderr[-300:] if stderr else "Process exited without summary"

    return {
        "task_id": task_id,
        "reward": reward,
        "success": (reward == 1.0),
        "steps": steps,
        "elapsed": elapsed,
        "err_msg": err_msg,
    }


def induce_memory(
    task_id: int,
    model_name: str,
    memory_mode: str,
    results_dir: Path,
    memory_jsonl: Path,
) -> bool:
    """Induce memory item upon task success."""
    induce_script = WEBARENA_DIR / "induce_memory.py"
    cmd = [
        sys.executable,
        str(induce_script),
        "--result_dir", str(results_dir),
        "--task", f"webarena.{task_id}",
        "--model", model_name,
        "--output_path", str(memory_jsonl),
        "--criteria", "gt",
        "--memory_mode", memory_mode,
    ]
    try:
        res = subprocess.run(
            cmd,
            cwd=str(WEBARENA_DIR),
            capture_output=True,
            text=True,
            timeout=120,
            env=os.environ.copy(),
        )
        if res.returncode == 0:
            logger.info(f"[{memory_mode.upper()}] Memory successfully induced for Task {task_id}")
            return True
        else:
            logger.warning(f"[{memory_mode.upper()}] Induce memory non-zero exit for Task {task_id}: {res.stderr[:200]}")
            return False
    except Exception as e:
        logger.warning(f"[{memory_mode.upper()}] Failed to induce memory for Task {task_id}: {e}")
        return False


def load_task_stats(results_dir: Path, task_id: int) -> dict[str, Any] | None:
    """Load evaluation outcome from results directory if already evaluated."""
    task_dir = results_dir / f"webarena.{task_id}"
    summary_file = task_dir / "summary_info.json"
    if not summary_file.exists():
        return None
    try:
        data = json.loads(summary_file.read_text(encoding="utf-8"))
        reward = float(data.get("cum_reward", 0.0))
        steps = int(data.get("n_steps", 0))
        # Ensure actual step files are counted if task timed out or was assigned 25
        step_files = list(task_dir.glob("step_*.pkl.gz"))
        if step_files and ("timed out" in str(data.get("err_msg", "")).lower() or steps >= 25):
            steps = max(len(step_files), 1)
        elapsed = float(data.get("stats.cum_agent_elapsed", 0.0) or data.get("stats.cum_step_elapsed", 0.0))
        return {
            "task_id": task_id,
            "reward": reward,
            "success": (reward == 1.0),
            "steps": steps,
            "elapsed": elapsed,
            "err_msg": data.get("err_msg"),
        }
    except Exception:
        return None


_COST_CACHE = {"time": 0.0, "data": None}


def get_openrouter_cost_stats() -> dict[str, Any]:
    now = time.time()
    if now - _COST_CACHE["time"] < 20.0 and _COST_CACHE["data"] is not None:
        return _COST_CACHE["data"]

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        env_file = REPO_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("OPENROUTER_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break
    if not api_key:
        return {}

    try:
        import requests
        res = requests.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5,
        )
        if res.status_code == 200:
            d = res.json().get("data", {})
            stats = {
                "limit_remaining": float(d.get("limit_remaining", 0.0)),
                "usage": float(d.get("usage", 0.0)),
            }
            _COST_CACHE["time"] = now
            _COST_CACHE["data"] = stats
            return stats
    except Exception:
        pass
    return _COST_CACHE["data"] or {}


def generate_head_to_head_report(
    report_file: Path,
    task_order: list[int],
    copromem_dir: Path,
    rb_dir: Path,
    model_name: str,
    max_steps: int,
    current_eval_info: str | None = None,
    contract_guidance: bool = False,
    task_source: str | None = None,
):
    """Generate professional side-by-side Head-to-Head markdown report."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    c_pass = 0
    c_total = 0
    c_steps = []

    r_pass = 0
    r_total = 0
    r_steps = []

    c_wins = 0
    r_wins = 0
    ties_both_pass = 0
    ties_both_fail = 0
    estimated_cost = 0.0

    rows = []

    for tid in task_order:
        intent = get_task_intent(tid)
        c_res = load_task_stats(copromem_dir, tid)
        r_res = load_task_stats(rb_dir, tid)

        # Row columns
        # Task ID | Goal | COPROMEM | Steps | ReasoningBank | Steps | Winner | Est. Cost |
        c_badge = "⏳ Pending"
        c_step_str = "-"
        r_badge = "⏳ Pending"
        r_step_str = "-"
        winner_badge = "-"
        cost_str = "-"

        task_steps = 0
        if c_res:
            c_total += 1
            c_steps.append(c_res["steps"])
            task_steps += c_res["steps"]
            if c_res["success"]:
                c_pass += 1
                c_badge = "🟩 **PASS**"
                c_step_str = str(c_res["steps"])
            else:
                c_badge = "🟥 **FAIL**"
                is_timeout = "timed out" in str(c_res.get("err_msg", "")).lower()
                c_step_str = f"{c_res['steps']} ⏱️" if is_timeout else str(c_res["steps"])

        if r_res:
            r_total += 1
            r_steps.append(r_res["steps"])
            task_steps += r_res["steps"]
            if r_res["success"]:
                r_pass += 1
                r_badge = "🟩 **PASS**"
                r_step_str = str(r_res["steps"])
            else:
                r_badge = "🟥 **FAIL**"
                is_timeout = "timed out" in str(r_res.get("err_msg", "")).lower()
                r_step_str = f"{r_res['steps']} ⏱️" if is_timeout else str(r_res["steps"])

        if c_res and r_res:
            est_cost = (task_steps * 0.00045) + 0.0008
            estimated_cost += est_cost
            cost_str = f"${est_cost:.4f}"
            if c_res["success"] and not r_res["success"]:
                winner_badge = "🏆 **COPROMEM Win**"
                c_wins += 1
            elif not c_res["success"] and r_res["success"]:
                winner_badge = "🥈 **ReasoningBank Win**"
                r_wins += 1
            elif c_res["success"] and r_res["success"]:
                # Both passed: tie or step efficiency
                if c_res["steps"] < r_res["steps"]:
                    winner_badge = "🤝 **Tie** (COPROMEM Faster)"
                elif r_res["steps"] < c_res["steps"]:
                    winner_badge = "🤝 **Tie** (RB Faster)"
                else:
                    winner_badge = "🤝 **Tie** (Identical)"
                ties_both_pass += 1
            else:
                winner_badge = "❌ **Tie** (Both Fail)"
                ties_both_fail += 1
        elif c_res and not r_res:
            est_cost = (c_res["steps"] * 0.00045) + 0.0004
            estimated_cost += est_cost
            cost_str = f"~${est_cost:.4f}"
            winner_badge = "🔄 *Evaluating RB...*"
        elif not c_res and r_res:
            est_cost = (r_res["steps"] * 0.00045) + 0.0004
            estimated_cost += est_cost
            cost_str = f"~${est_cost:.4f}"
            winner_badge = "🔄 *Evaluating COPROMEM...*"

        # Shorten intent if long
        short_intent = intent if len(intent) <= 65 else intent[:62] + "..."

        rows.append(
            f"| `{tid}` | {short_intent} | {c_badge} | {c_step_str} | {r_badge} | {r_step_str} | {winner_badge} | {cost_str} |"
        )

    c_sr = (c_pass / c_total * 100) if c_total > 0 else 0.0
    r_sr = (r_pass / r_total * 100) if r_total > 0 else 0.0
    c_avg_steps = (sum(c_steps) / len(c_steps)) if c_steps else 0.0
    r_avg_steps = (sum(r_steps) / len(r_steps)) if r_steps else 0.0

    cost_info = get_openrouter_cost_stats()
    balance_str = f"${cost_info['limit_remaining']:.4f}" if "limit_remaining" in cost_info else "N/A"
    total_eval_runs = c_total + r_total
    avg_estimated_cost = estimated_cost / total_eval_runs if total_eval_runs else 0.0
    projected_total = avg_estimated_cost * (len(task_order) * 2)

    lines = [
        f"# ⚔️ COPROMEM 2.0 vs ReasoningBank: Direct Head-to-Head Benchmark",
        f"",
        f"> **Model:** `{model_name}`  ",
        f"> **COPROMEM Prompt Contracts:** {'Enabled' if contract_guidance else 'Disabled (decomposition and memory retained)'}  ",
        f"> **Environment:** WebArena Shopping Admin (`http://localhost:7780/admin`)  ",
        f"> **Status:** {'🟢 Completed' if (c_total == len(task_order) and r_total == len(task_order)) else '🟡 Running'} | **Last Updated:** `{now_str}`  ",
    ]

    if current_eval_info:
        lines.append(f"> **Active Progress:** {current_eval_info}  ")

    lines.extend([
        f"",
        f"---",
        f"",
        f"## 1. Executive Scoreboard",
        f"",
        f"| Metric | COPROMEM 2.0 ({'Decomposition + Memory + Contracts' if contract_guidance else 'Decomposition + Memory, Contracts Off'}) | ReasoningBank (shared patched harness) | Delta / Winner |",
        f"| :--- | :--- | :--- | :--- |",
        f"| **Tasks Evaluated** | `{c_total} / {len(task_order)}` | `{r_total} / {len(task_order)}` | - |",
        f"| **Success Count (Pass@1)** | **`{c_pass} / {c_total}`** | **`{r_pass} / {r_total}`** | `{c_pass - r_pass:+d}` |",
        f"| **Success Rate (SR)** | **`{c_sr:.1f}%`** | **`{r_sr:.1f}%`** | **`{c_sr - r_sr:+.1f}%`** |",
        f"| **Direct Matchup Wins** | **`{c_wins}` Wins** | **`{r_wins}` Wins** | **COPROMEM Net: `{c_wins - r_wins:+d}`** |",
        f"| **Mutual Ties** | `{ties_both_pass}` Both Pass / `{ties_both_fail}` Both Fail | - | - |",
        f"| **Average Steps / Task** | `{c_avg_steps:.2f}` steps | `{r_avg_steps:.2f}` steps | `{c_avg_steps - r_avg_steps:+.2f}` |",
        f"| **Live OpenRouter Balance** | **`{balance_str}`** | Actual session spend not measured | - |",
        f"| **Estimated Cost (step heuristic)** | **`~${estimated_cost:.4f}`** so far | **`~${avg_estimated_cost:.4f}`** / agent run | Projected {len(task_order)} pairs: `~${projected_total:.2f}` |",
        f"",
        f"---",
        f"",
        f"## 2. Task-by-Task Head-to-Head Outcome Matrix",
        f"",
        f"| Task ID | Goal / Intent | COPROMEM | Steps | ReasoningBank | Steps | Head-to-Head Matchup | Est. Cost |",
        f"| :---: | :--- | :---: | :---: | :---: | :---: | :--- | :---: |",
    ])

    lines.extend(rows)
    lines.append("")

    if task_source:
        lines.insert(4, f"> **Task Set:** {task_source}  ")

    report_file.parent.mkdir(parents=True, exist_ok=True)
    notes = ""
    if report_file.exists():
        previous_report = report_file.read_text(encoding="utf-8")
        if REPORT_NOTES_MARKER in previous_report:
            notes = previous_report.split(REPORT_NOTES_MARKER, 1)[1].strip()
    report_text = "\n".join(lines)
    if notes:
        report_text += f"\n\n{REPORT_NOTES_MARKER}\n\n{notes}\n"
    report_file.write_text(report_text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Run direct Head-to-Head Benchmark between COPROMEM and ReasoningBank.")
    parser.add_argument("--model_name", type=str, default="deepseek/deepseek-v4.1-flash")
    parser.add_argument("--tasks", type=str, default="qa86", choices=["qa86", "qa86_continue", "admin100", "mini30", "easy_medium30"])
    parser.add_argument("--base_results_dir", type=str, default="results_head_to_head_deepseek_v4_1")
    parser.add_argument("--report_file", type=str, default="results_head_to_head_deepseek_v4_1/report_head_to_head.md")
    parser.add_argument("--max_steps", type=int, default=25)
    parser.add_argument("--timeout", type=int, default=360)
    parser.add_argument("--headless", type=bool, default=True)
    parser.add_argument("--induce_memory", action="store_true", default=True)
    parser.add_argument("--skip_completed", action="store_true", default=True)
    contract_group = parser.add_mutually_exclusive_group()
    contract_group.add_argument("--contract_guidance", dest="contract_guidance", action="store_true",
                                help="Opt in to COPROMEM prompt contracts (off by default).")
    contract_group.add_argument("--no_contract_guidance", dest="contract_guidance", action="store_false",
                                help="Keep COPROMEM prompt contracts disabled (the default).")
    parser.set_defaults(contract_guidance=False)

    args = parser.parse_args()
    ensure_env()

    task_order = (
        load_qa86_continuation_tasks() if args.tasks == "qa86_continue"
        else EASY_MEDIUM30_TASKS if args.tasks == "easy_medium30"
        else MINI30_TASKS if args.tasks == "mini30"
        else ADMIN100_TASKS
    )
    continues_easy_medium30 = args.tasks in {"easy_medium30", "qa86_continue"}
    task_source = (
        "`benchmark_tasks_pure_qa_86.json` (30 completed tasks followed by remaining manifest tasks)"
        if args.tasks == "qa86_continue" else None
    )
    contract_guidance = args.contract_guidance
    base_dir = REPO_ROOT / args.base_results_dir
    report_path = REPO_ROOT / args.report_file

    copromem_results = base_dir / "copromem"
    rb_results = base_dir / "reasoningbank"
    copromem_results.mkdir(parents=True, exist_ok=True)
    rb_results.mkdir(parents=True, exist_ok=True)

    mem_suffix = base_dir.name.replace("results_head_to_head_", "")
    c_mem_txt = WEBARENA_DIR / f"memories_h2h_{mem_suffix}_copromem" / "shopping_admin.txt"
    c_mem_jsonl = WEBARENA_DIR / f"memories_h2h_{mem_suffix}_copromem" / "shopping_admin.jsonl"
    r_mem_txt = WEBARENA_DIR / f"memories_h2h_{mem_suffix}_rb" / "shopping_admin.txt"
    r_mem_jsonl = WEBARENA_DIR / f"memories_h2h_{mem_suffix}_rb" / "shopping_admin.jsonl"
    r_mem_emb = WEBARENA_DIR / f"memories_h2h_{mem_suffix}_rb" / "shopping_admin_embeddings.jsonl"

    c_mem_txt.parent.mkdir(parents=True, exist_ok=True)
    r_mem_txt.parent.mkdir(parents=True, exist_ok=True)

    # Seed memories from reasoningbank base if not present
    seed_jsonl = WEBARENA_DIR / "memories_reasoningbank" / "shopping_admin.jsonl"
    seed_emb = WEBARENA_DIR / "memories_reasoningbank" / "shopping_admin_embeddings.jsonl"
    if not continues_easy_medium30 and seed_jsonl.exists():
        if not c_mem_jsonl.exists():
            shutil.copyfile(seed_jsonl, c_mem_jsonl)
        if not r_mem_jsonl.exists():
            shutil.copyfile(seed_jsonl, r_mem_jsonl)
    if not continues_easy_medium30 and seed_emb.exists() and not r_mem_emb.exists():
        shutil.copyfile(seed_emb, r_mem_emb)

    logger.info("=" * 70)
    logger.info(f"STARTING DIRECT HEAD-TO-HEAD BENCHMARK: COPROMEM vs REASONINGBANK")
    logger.info(f"Model: {args.model_name}")
    logger.info(f"Suite: {args.tasks} ({len(task_order)} tasks)")
    logger.info(f"COPROMEM Results: {copromem_results}")
    logger.info(f"ReasoningBank Results: {rb_results}")
    logger.info(f"Live Markdown Report: {report_path}")
    logger.info("=" * 70)

    # Initial flush of report
    generate_head_to_head_report(
        report_file=report_path,
        task_order=task_order,
        copromem_dir=copromem_results,
        rb_dir=rb_results,
        model_name=args.model_name,
        max_steps=args.max_steps,
        contract_guidance=contract_guidance,
        task_source=task_source,
    )

    for idx, tid in enumerate(task_order, 1):
        task_label = f"[{idx}/{len(task_order)}] Task {tid}"

        # ----------------------------------------------------
        # 1. EVALUATE COPROMEM
        # ----------------------------------------------------
        c_done = (copromem_results / f"webarena.{tid}" / "summary_info.json").exists()
        if args.skip_completed and c_done:
            logger.info(f"{task_label} (COPROMEM): Already evaluated. Skipping.")
        else:
            generate_head_to_head_report(
                report_file=report_path,
                task_order=task_order,
                copromem_dir=copromem_results,
                rb_dir=rb_results,
                model_name=args.model_name,
                max_steps=args.max_steps,
                current_eval_info=f"Task {tid} on **COPROMEM**...",
                contract_guidance=contract_guidance,
                task_source=task_source,
            )
            c_res = run_single_task(
                task_id=tid,
                model_name=args.model_name,
                memory_mode="copromem",
                results_dir=copromem_results,
                memory_path=c_mem_txt,
                max_steps=args.max_steps,
                headless=args.headless,
                timeout_seconds=args.timeout,
                contract_guidance=contract_guidance,
            )
            if c_res["success"]:
                logger.info(f"✓ {task_label} (COPROMEM) SUCCEEDED (Steps: {c_res['steps']}, Time: {c_res['elapsed']:.1f}s)")
                if args.induce_memory and not continues_easy_medium30:
                    induce_memory(tid, args.model_name, "copromem", copromem_results, c_mem_jsonl)
            else:
                logger.info(f"✗ {task_label} (COPROMEM) FAILED (Steps: {c_res['steps']})")
            if continues_easy_medium30:
                sys.path.insert(0, str(WEBARENA_DIR))
                from copromem_adapter import COPROMEMReasoningBankAdapter

                COPROMEMReasoningBankAdapter(api_key="", model=args.model_name).complete_episode(
                    task_id=tid,
                    intent=get_task_intent(tid),
                    success=c_res["success"],
                    actions=load_recorded_actions(copromem_results, tid),
                    memories_jsonl_path=c_mem_jsonl,
                    consolidate=(idx % 5 == 0),
                )

        # ----------------------------------------------------
        # 2. EVALUATE REASONINGBANK
        # ----------------------------------------------------
        r_done = (rb_results / f"webarena.{tid}" / "summary_info.json").exists()
        if args.skip_completed and r_done:
            logger.info(f"{task_label} (ReasoningBank): Already evaluated. Skipping.")
        else:
            generate_head_to_head_report(
                report_file=report_path,
                task_order=task_order,
                copromem_dir=copromem_results,
                rb_dir=rb_results,
                model_name=args.model_name,
                max_steps=args.max_steps,
                current_eval_info=f"Task {tid} on **ReasoningBank**...",
                contract_guidance=contract_guidance,
                task_source=task_source,
            )
            r_res = run_single_task(
                task_id=tid,
                model_name=args.model_name,
                memory_mode="reasoningbank",
                results_dir=rb_results,
                memory_path=r_mem_txt,
                max_steps=args.max_steps,
                headless=args.headless,
                timeout_seconds=args.timeout,
                contract_guidance=contract_guidance,
            )
            if r_res["success"]:
                logger.info(f"✓ {task_label} (ReasoningBank) SUCCEEDED (Steps: {r_res['steps']}, Time: {r_res['elapsed']:.1f}s)")
                if args.induce_memory:
                    induce_memory(tid, args.model_name, "reasoningbank", rb_results, r_mem_jsonl)
            else:
                logger.info(f"✗ {task_label} (ReasoningBank) FAILED (Steps: {r_res['steps']})")

        # Sync live report after both complete for this task
        generate_head_to_head_report(
            report_file=report_path,
            task_order=task_order,
            copromem_dir=copromem_results,
            rb_dir=rb_results,
            model_name=args.model_name,
            max_steps=args.max_steps,
            contract_guidance=contract_guidance,
            task_source=task_source,
        )

    logger.info("=" * 70)
    logger.info(f"DIRECT HEAD-TO-HEAD BENCHMARK COMPLETED!")
    logger.info(f"Final Report: {report_path}")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
