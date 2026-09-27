#!/usr/bin/env python3
"""Live Monitor & WebArena Benchmark Reporter (COPROMEM 2.0 & ReasoningBank Native).

Matches the canonical design of `artifacts/live_browser_benchmark_report.md`:
- Header with progress, live status, model, judge, and environment details.
- 1. Summary Comparison (Native SR, Fuzzy SR, Overall SR, Steps, Duration, Costs).
- 2. Outcome Matrix (Chronological Execution Order with badges).
- 3. Task Details & Extracted Answers (Expected vs Extracted, Judge Explanations).
- 4. Negative Transfer & Memory Separation Audit (Injected Memory, Veto/Decomposition Mode).
"""

from __future__ import annotations

import argparse
import ast
import datetime
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.table import Table

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
WEBARENA_DIR = REPO_ROOT / "external" / "reasoning-bank" / "WebArena"
CONFIG_DIR = WEBARENA_DIR / "config_files"

# Default Curated 30-task Suite (Ordered easy-to-hard)
MINI30_TASKS = [
    94, 95, 41, 42, 43, 185, 201, 198, 202, 203,
    200, 184, 186, 199, 193, 194, 197, 6, 204, 127,
    0, 119, 1, 3, 116, 62, 63, 107, 196, 288,
]

# Read-only Shopping Admin QA from the benchmark's tier-1/2 taxonomy.
# Keep this distinct from MINI30_TASKS, which also includes harder tiers.
EASY_MEDIUM30_TASKS = [
    41, 42, 43, 94, 95, 112, 113, 114, 115, 198,
    199, 200, 201, 202, 203, 208, 209, 210, 211, 212,
    11, 12, 13, 14, 15, 77, 78, 79, 183, 185,
]

# Canonical 86 Pure QA Shopping Admin Suite (Excludes all DOM / form-filling tasks)
QA86_TASKS = [
    # Evaluated baseline tasks (First 34 Tasks)
    94, 95, 41, 42, 43, 185, 201, 198, 202, 203,
    200, 184, 186, 199, 193, 194, 197, 6, 204, 127,
    0, 119, 1, 3, 116, 62, 63, 107, 196, 288,
    112, 113, 114, 115,
    # Customer Phone Lookups (Tier 1 - Pure Lookup)
    208, 209, 210, 211, 212,
    # Review Keyword Counts (Tier 2 - Filtering & Counting)
    11, 12, 13, 14, 15,
    # Review Status Counts (Tier 3 - Filtering & Counting)
    77, 78, 79,
    # Product Dislike / Feedback Analysis (Tier 4 - Review Semantic Extraction)
    213, 214, 215, 216, 217,
    # Customer Unhappy Lookups (Tier 5 - Review Negative Rating Lookup)
    243, 244, 245, 246, 247,
    # Product Positive Feedback (Tier 6 - Semantic QA)
    120, 121, 122, 123,
    # Review Counts by Date (Tier 7 - Date Scoping)
    344, 345, 346, 347, 348,
    # Items Sold & Cancellation Details (Tier 8 - Recent Orders QA)
    128, 129, 130, 131, 289, 290, 291, 292,
    # Inventory & Payments (Tier 9 - Catalog Lookup)
    183, 187, 195,
    # Bestsellers & Historical Ordering (Tier 10 - Sales Grid QA)
    2, 4, 5, 64, 65, 108, 109, 110, 111,
]

ADMIN100_TASKS = QA86_TASKS


console = Console()
logger = logging.getLogger("LiveMonitor")


def load_api_key() -> str:
    """Retrieve OPENROUTER_API_KEY from env or .env file."""
    if os.getenv("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"].strip()
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def call_openrouter(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 384,
    temperature: float = 0.0,
) -> tuple[str, float]:
    """Call OpenRouter API and return (content, cost_usd)."""
    if not api_key:
        return "", 0.0
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = json.dumps({
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/QuanNguyen28/COPROMEM",
            "X-Title": "COPROMEM-Live-Judge",
        },
        method="POST",
    )

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choice = data.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content", "")
                usage = data.get("usage", {})
                p_tokens = usage.get("prompt_tokens", 0)
                c_tokens = usage.get("completion_tokens", 0)
                # Pricing for gpt-4o-mini ($0.15/1M prompt, $0.60/1M completion)
                cost = (p_tokens * 0.00000015) + (c_tokens * 0.00000060)
                return content.strip(), round(cost, 6)
        except Exception as e:
            if attempt == 2:
                logger.warning(f"Judge OpenRouter call failed: {e}")
                return "", 0.0
            time.sleep(1.0)
    return "", 0.0


def webarena_llm_fuzzy_match(
    api_key: str,
    judge_model: str,
    question: str,
    reference: str,
    pred: str,
) -> tuple[bool, str, float]:
    """Official WebArena LLM Fuzzy Match evaluator."""
    system_msg = "You are a helpful assistant"
    user_prompt = (
        "Help a teacher to grade the answer of a student given a question. "
        "Keep in mind that the student may use different phrasing or wording to answer the question. "
        "The goal is to evaluate whether the answer is semantically equivalent to the reference answer.\n"
        f"question: {question}\n"
        f"reference answer: {reference}\n"
        "all the string 'N/A' that you see is a special sequence that means 'not achievable'\n"
        f"student answer: {pred}\n"
        "Conclude the judgement by correct/incorrect/partially correct."
    )

    resp, cost = call_openrouter(
        api_key=api_key,
        model=judge_model,
        system_prompt=system_msg,
        user_prompt=user_prompt,
    )
    resp_lower = resp.lower()
    if "partially correct" in resp_lower or "incorrect" in resp_lower:
        is_success = False
    elif "correct" in resp_lower:
        is_success = True
    else:
        is_success = False

    return is_success, resp, cost


def extract_prediction_from_log(log_path: Path) -> str:
    """Extract the last send_msg_to_user argument from experiment.log."""
    if not log_path.exists():
        return ""
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        last_call = None
        for line in lines:
            line_str = line.strip()
            if "send_msg_to_user(" in line_str:
                last_call = line_str

        if not last_call:
            return ""

        start = last_call.index("send_msg_to_user(") + len("send_msg_to_user(")
        raw = last_call[start:]
        end = raw.rfind(")")
        if end == -1:
            return raw.strip()
        raw_arg = raw[:end].strip()

        try:
            val = ast.literal_eval(raw_arg)
            return str(val).strip()
        except Exception:
            if (raw_arg.startswith('"') and raw_arg.endswith('"')) or (raw_arg.startswith("'") and raw_arg.endswith("'")):
                return raw_arg[1:-1].strip()
            return raw_arg
    except Exception:
        return ""


def extract_live_step_and_action(log_path: Path) -> tuple[int, str, str]:
    """Extract step count, latest thought, and action from an active experiment.log."""
    if not log_path.exists():
        return 0, "", ""
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()

        step_count = 0
        latest_thought = ""
        latest_action = ""

        i = 0
        while i < len(lines):
            line = lines[i]
            if "action:" in line.lower():
                step_count += 1
                if i + 1 < len(lines):
                    latest_action = lines[i + 1].strip()
            elif "browsergym.experiments.loop - INFO -" in line and "action:" not in line:
                part = line.split("browsergym.experiments.loop - INFO -")[-1].strip()
                if part and not part.startswith("Saving summary") and not part.startswith("Running experiment"):
                    latest_thought = part[:140] + ("..." if len(part) > 140 else "")
            i += 1

        return step_count, latest_thought, latest_action
    except Exception:
        return 0, "", ""


def get_task_config(task_id: str | int) -> dict[str, Any]:
    """Load intent and reference answers from config file."""
    cfg_path = CONFIG_DIR / f"{task_id}.json"
    if not cfg_path.exists():
        return {}
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def compute_token_cost(summary: dict) -> float:
    """Calculate approx API cost for Gemini 2.5 Flash from token stats."""
    in_tokens = float(summary.get("stats.cum_n_token_dom_txt", 0) + summary.get("stats.cum_n_token_goal", 0))
    out_tokens = float(summary.get("n_steps", 1) * 350)
    cost = (in_tokens * 0.000000075) + (out_tokens * 0.00000030)
    return round(cost, 5)


def load_judge_cache(cache_file: Path) -> dict[str, dict]:
    """Load cached judge results."""
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_judge_cache(cache_file: Path, cache: dict[str, dict]) -> None:
    """Persist judge cache to disk."""
    try:
        cache_file.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception:
        pass


def evaluate_task_result(
    task_id: int,
    results_dir: Path,
    api_key: str,
    judge_model: str,
    judge_cache: dict[str, dict],
) -> dict[str, Any] | None:
    """Parse and evaluate a completed task result."""
    task_dir = results_dir / f"webarena.{task_id}"
    if not task_dir.is_dir():
        return None

    summary_file = task_dir / "summary_info.json"
    log_file = task_dir / "experiment.log"
    mem_file = task_dir / "injected_memory.txt"

    cfg = get_task_config(task_id)
    intent = cfg.get("intent", f"Task {task_id}")
    gt = cfg.get("eval", {}).get("reference_answer_raw_annotation", "")
    if not gt:
        ref_dict = cfg.get("eval", {}).get("reference_answers") or {}
        gt = str(ref_dict.get("exact_match") or ref_dict.get("must_include") or ref_dict.get("fuzzy_match") or "")

    summary = {}
    if summary_file.exists():
        try:
            summary = json.loads(summary_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    pred = extract_prediction_from_log(log_file)
    reward = float(summary.get("cum_reward", 0.0))
    steps = int(summary.get("n_steps", 0))
    elapsed = float(summary.get("stats.cum_step_elapsed", 0.0) + summary.get("stats.cum_agent_elapsed", 0.0))
    agent_cost = compute_token_cost(summary)
    judge_cost = 0.0

    native_success = (reward == 1.0)
    judge_success = native_success
    judge_reason = ""

    if native_success:
        judge_success = True
        judge_reason = "*(Skipped — Native evaluation already passed)*"
        judge_label = "**PASS** *(Skipped)*"
    else:
        if pred and gt and gt.strip() != "N/A":
            cache_key = f"{task_id}::{pred}"
            if cache_key in judge_cache:
                cached = judge_cache[cache_key]
                judge_success = cached.get("is_match", False)
                judge_reason = cached.get("explanation", "")
                judge_cost = cached.get("cost", 0.0)
            else:
                is_match, explanation, j_cost = webarena_llm_fuzzy_match(
                    api_key=api_key,
                    judge_model=judge_model,
                    question=intent,
                    reference=gt,
                    pred=pred,
                )
                judge_success = is_match
                judge_reason = explanation
                judge_cost = j_cost
                judge_cache[cache_key] = {
                    "is_match": is_match,
                    "explanation": explanation,
                    "cost": j_cost,
                }
            judge_badge = "PASS" if judge_success else "FAIL"
            judge_label = f"**{judge_badge}**"
        else:
            judge_success = False
            judge_reason = "*(None / Aborted)*" if not pred else "*(None)*"
            judge_label = "**FAIL**"

    # Persist judge assessment for dual-signal memory induction
    try:
        judge_eval_file = task_dir / "judge_eval.json"
        judge_eval_file.write_text(
            json.dumps([{"thoughts": judge_reason, "rm": 1 if judge_success else 0}]),
            encoding="utf-8"
        )
    except Exception:
        pass

    overall_success = native_success or judge_success
    total_cost = agent_cost + judge_cost

    # Injected memory extraction
    injected_mem = ""
    if mem_file.exists():
        try:
            injected_mem = mem_file.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            pass

    return {
        "task_id": task_id,
        "intent": intent,
        "ground_truth": gt,
        "prediction": pred,
        "reward": reward,
        "native_success": native_success,
        "judge_success": judge_success,
        "overall_success": overall_success,
        "judge_label": judge_label,
        "judge_reason": judge_reason,
        "steps": steps,
        "elapsed": elapsed,
        "agent_cost": agent_cost,
        "judge_cost": judge_cost,
        "total_cost": total_cost,
        "injected_memory": injected_mem,
    }


def generate_benchmark_report_markdown(
    task_order: list[int],
    results_dir: Path,
    current_task_id: int | None = None,
    current_status: str | None = None,
    suite_name: str = "mini30",
    model_name: str = "google/gemini-2.5-flash",
    judge_model: str = "openai/gpt-4o-mini",
    memory_mode: str = "copromem",
    max_steps: int = 25,
) -> str:
    """Generate markdown strictly following artifacts/live_browser_benchmark_report.md."""
    api_key = load_api_key()
    cache_file = results_dir / "judge_cache.json"
    judge_cache = load_judge_cache(cache_file)

    evaluated_tasks: dict[int, dict[str, Any]] = {}
    for tid in task_order:
        res = evaluate_task_result(tid, results_dir, api_key, judge_model, judge_cache)
        if res is not None:
            evaluated_tasks[tid] = res

    save_judge_cache(cache_file, judge_cache)

    completed_count = len(evaluated_tasks)
    total_suite = len(task_order)
    progress_pct = (completed_count / total_suite * 100.0) if total_suite else 0.0

    # Summary Metrics
    native_succ = sum(1 for r in evaluated_tasks.values() if r["native_success"])
    judge_succ = sum(1 for r in evaluated_tasks.values() if r["judge_success"])
    overall_succ = sum(1 for r in evaluated_tasks.values() if r["overall_success"])

    native_sr = (native_succ / completed_count * 100.0) if completed_count else 0.0
    judge_sr = (judge_succ / completed_count * 100.0) if completed_count else 0.0
    overall_sr = (overall_succ / completed_count * 100.0) if completed_count else 0.0

    avg_steps = (sum(r["steps"] for r in evaluated_tasks.values()) / completed_count) if completed_count else 0.0
    avg_duration = (sum(r["elapsed"] for r in evaluated_tasks.values()) / completed_count) if completed_count else 0.0
    tot_agent_cost = sum(r["agent_cost"] for r in evaluated_tasks.values())
    tot_judge_cost = sum(r["judge_cost"] for r in evaluated_tasks.values())
    tot_task_cost = tot_agent_cost + tot_judge_cost
    avg_cost = (tot_task_cost / completed_count) if completed_count else 0.0

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Determine live status string
    if current_task_id is not None and current_task_id not in evaluated_tasks:
        live_status_str = f"Evaluating Task {current_task_id} (`{memory_mode} ({current_status or 'evaluating...'})`)"
    elif completed_count == total_suite:
        live_status_str = f"Completed ({total_suite}/{total_suite} tasks fully evaluated)"
    else:
        live_status_str = f"Idle / Waiting for next task ({completed_count}/{total_suite} done)"

    lines = [
        "# Live Browser WebArena Benchmark Report (Shopping Admin Suite)",
        "",
        f"- **Timestamp:** {now_str}",
        f"- **Suite & Curriculum Order:** `{suite_name}` ({total_suite} tasks) | `easy-to-hard`",
        f"- **Agent Model:** `{model_name}` (via OpenRouter API)",
        f"- **Judge Method:** Official WebArena `llm_fuzzy_match` (`{judge_model}` via OpenRouter)",
        f"- **Progress:** {completed_count}/{total_suite} tasks fully evaluated ({progress_pct:.1f}%)",
        f"- **Live Status:** {live_status_str}",
        f"- **Max Steps Safety Cap:** {max_steps} (ReasoningBank Native Harness)",
        "- **Local Server:** `http://localhost:7780/admin`",
        "",
        "## 1. Summary Comparison",
        "",
        "| Arm | Native SR % (Rigid) | WebArena Fuzzy SR % (LLM Judge) | Overall SR % | Avg Steps | Avg Duration (s) | Agent Cost ($) | Judge Cost ($) | Total Cost ($) | Avg Cost/Task ($) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        f"| `{memory_mode}` | {native_sr:.1f}% ({native_succ}/{completed_count}) | {judge_sr:.1f}% ({judge_succ}/{completed_count}) | **{overall_sr:.1f}%** | {avg_steps:.2f} | {avg_duration:.1f}s | ${tot_agent_cost:.4f} | ${tot_judge_cost:.4f} | ${tot_task_cost:.4f} | ${avg_cost:.5f} |" if completed_count else f"| `{memory_mode}` | 0.0% (0/0) | 0.0% (0/0) | **0.0%** | 0.00 | 0.0s | $0.0000 | $0.0000 | $0.0000 | $0.00000 |",
        "",
        "## 2. Outcome Matrix (Chronological Execution Order)",
        "",
        f"| # | Task ID | Intent | Ground Truth | `{memory_mode}` | Total Task Cost ($) |",
        "| :---: | :---: | :--- | :--- | :---: | :---: |",
    ]

    detailed_blocks = []
    audit_rows = []

    for idx, tid in enumerate(task_order, 1):
        cfg = get_task_config(tid)
        intent = cfg.get("intent", f"Task {tid}")
        gt = cfg.get("eval", {}).get("reference_answer_raw_annotation", "")
        if not gt:
            ref_dict = cfg.get("eval", {}).get("reference_answers") or {}
            gt = str(ref_dict.get("exact_match") or ref_dict.get("must_include") or ref_dict.get("fuzzy_match") or "")

        clean_intent = intent.replace("\n", " ").strip()
        clean_gt = gt.replace("\n", " ").strip()

        if tid in evaluated_tasks:
            res = evaluated_tasks[tid]
            nat_badge = "PASS" if res["native_success"] else "FAIL"
            jdg_badge = "PASS" if res["judge_success"] else "FAIL"
            compact_outcome = f"**Nat: {nat_badge} / Jdg: {jdg_badge}**<br>({res['steps']} steps, ${res['total_cost']:.4f})"
            task_cost_str = f"${res['total_cost']:.4f}"

            lines.append(f"| **{idx}** | **Task {tid}** | {clean_intent} | `{clean_gt}` | {compact_outcome} | {task_cost_str} |")

            # Section 3 block
            ext_str = f"`{res['prediction']}`" if res["prediction"] else "*(None / Aborted)*"
            j_reason = res["judge_reason"] if res["judge_reason"] else "*(None)*"
            detail_block = (
                f"### #{idx} — Task {tid}: {clean_intent}\n"
                f"- **Expected Ground Truth:** `{clean_gt}`\n"
                f"- **Total Task Cost:** {task_cost_str}\n"
                f"- **`{memory_mode}`:** Native: **{nat_badge}** | Judge: {res['judge_label']} ({res['steps']} steps, {res['elapsed']:.1f}s, ${res['total_cost']:.4f} [Agent: ${res['agent_cost']:.4f}, Judge: ${res['judge_cost']:.4f}])\n"
                f"  - **Extracted:** {ext_str}\n"
                f"  - **Judge Reason:** {j_reason}"
            )
            detailed_blocks.append(detail_block)

            # Section 4 audit row
            mem_text = res["injected_memory"]
            mem_snippet = "*(None)*"
            mode_str = "N/A"
            if mem_text:
                clean_mem = mem_text.replace("\n", " ")
                mem_snippet = (clean_mem[:100] + "...") if len(clean_mem) > 100 else clean_mem
                if "VETO" in mem_text:
                    mode_str = "YES (VETO)"
                elif "2-Step Macro Plan" in mem_text or "MACRO" in mem_text:
                    mode_str = "MACRO (2-Step)"
                elif "RECURSIVE" in mem_text or "Milestone" in mem_text:
                    mode_str = "RECURSIVE (Milestones)"
                elif "Verified Procedural Contract" in mem_text or "Contract" in mem_text:
                    mode_str = "CONTRACT (Verified)"
                else:
                    mode_str = "Active"
            audit_rows.append(f"| {idx} | Task {tid} | `{memory_mode}` | {mem_snippet} | {mode_str} |")

        elif current_task_id == tid:
            lines.append(f"| **{idx}** | **Task {tid}** | {clean_intent} | `{clean_gt}` | *(evaluating...)* | $0.0000 |")
            detailed_blocks.append(
                f"### #{idx} — Task {tid}: {clean_intent}\n"
                f"- **Expected Ground Truth:** `{clean_gt}`\n"
                f"- **Total Task Cost:** $0.0000\n"
                f"- **`{memory_mode}`:** *(evaluating...)*"
            )
            audit_rows.append(f"| {idx} | Task {tid} | `{memory_mode}` | *(evaluating...)* | In Progress |")
        else:
            lines.append(f"| **{idx}** | **Task {tid}** | {clean_intent} | `{clean_gt}` | *(In progress)* | $0.0000 |")

    lines.extend([
        "",
        "## 3. Task Details & Extracted Answers",
        "",
    ])
    if detailed_blocks:
        lines.append("\n\n".join(detailed_blocks))
    else:
        lines.append("*(No completed task details yet)*")

    lines.extend([
        "",
        "## 4. Negative Transfer & Memory Separation Audit",
        "",
        "| # | Task ID | Arm | Memory Guidance Injected | Veto / Decomposition Mode |",
        "| :---: | :---: | :---: | :--- | :---: |",
    ])
    if audit_rows:
        lines.extend(audit_rows)
    else:
        lines.append(f"| 1 | Task {task_order[0]} | `{memory_mode}` | *(None / Seed)* | N/A |")

    lines.append("")
    return "\n".join(lines)


def update_markdown_report_file(
    report_file: Path,
    task_order: list[int],
    results_dir: Path,
    current_task_id: int | None = None,
    current_status: str | None = None,
    suite_name: str = "mini30",
    model_name: str = "google/gemini-2.5-flash",
    judge_model: str = "openai/gpt-4o-mini",
    memory_mode: str = "copromem",
    max_steps: int = 25,
) -> None:
    """Render and write the canonical report directly to target file."""
    md_text = generate_benchmark_report_markdown(
        task_order=task_order,
        results_dir=results_dir,
        current_task_id=current_task_id,
        current_status=current_status,
        suite_name=suite_name,
        model_name=model_name,
        judge_model=judge_model,
        memory_mode=memory_mode,
        max_steps=max_steps,
    )
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(md_text, encoding="utf-8")


def render_terminal_table(
    task_order: list[int],
    results_dir: Path,
    current_task_id: int | None = None,
    memory_mode: str = "copromem",
    model_name: str = "google/gemini-2.5-flash",
) -> Table:
    """Build a rich terminal summary table."""
    cache_file = results_dir / "judge_cache.json"
    judge_cache = load_judge_cache(cache_file)
    api_key = load_api_key()

    table = Table(
        title=f"[bold cyan]COPROMEM Live Monitor[/bold cyan] | Model: [green]{model_name}[/green] | Mode: [yellow]{memory_mode}[/yellow]",
        show_header=True,
        header_style="bold magenta",
        expand=True,
    )

    table.add_column("#", style="dim", width=4)
    table.add_column("Task ID", style="bold white", width=14)
    table.add_column("Intent", style="white", ratio=2)
    table.add_column("Status", justify="center", width=12)
    table.add_column("Ground Truth", style="green", ratio=1)
    table.add_column("Prediction", style="yellow", ratio=1)
    table.add_column("Steps", justify="right", width=6)
    table.add_column("Cost", justify="right", width=8)

    for idx, tid in enumerate(task_order, 1):
        task_dir = results_dir / f"webarena.{tid}"
        cfg = get_task_config(tid)
        intent = cfg.get("intent", f"Task {tid}")[:50]
        gt = (cfg.get("eval", {}).get("reference_answer_raw_annotation") or "-")[:25]

        if task_dir.is_dir():
            res = evaluate_task_result(tid, results_dir, api_key, "openai/gpt-4o-mini", judge_cache)
            if res:
                badge = "[green]✓ PASS[/green]" if res["overall_success"] else "[red]✗ FAIL[/red]"
                pred = (res["prediction"] or "-")[:25]
                table.add_row(
                    str(idx),
                    f"webarena.{tid}",
                    intent,
                    badge,
                    gt,
                    pred,
                    str(res["steps"]),
                    f"${res['total_cost']:.4f}",
                )
        elif current_task_id == tid:
            table.add_row(
                str(idx),
                f"webarena.{tid}",
                intent,
                "[bold cyan]⚡ RUNNING[/bold cyan]",
                gt,
                "...",
                "...",
                "...",
            )

    return table


def run_watcher(
    results_dir: Path,
    report_file: Path,
    task_order: list[int],
    interval: float = 3.0,
    memory_mode: str = "copromem",
    model_name: str = "google/gemini-2.5-flash",
) -> None:
    """Run continuously in terminal, periodically updating the report and displaying live table."""
    logger.info(f"Starting Live Monitor Watcher -> {report_file} (interval={interval}s)")
    with Live(console=console, refresh_per_second=2) as live:
        while True:
            # Check if any task is actively running in results_dir
            active_tid = None
            if results_dir.exists():
                for entry in results_dir.iterdir():
                    if entry.is_dir() and "GenericAgentArgs_on_webarena." in entry.name:
                        m = re.search(r"webarena\.(\d+)", entry.name)
                        if m:
                            active_tid = int(m.group(1))
                            break

            update_markdown_report_file(
                report_file=report_file,
                task_order=task_order,
                results_dir=results_dir,
                current_task_id=active_tid,
                suite_name="mini30",
                model_name=model_name,
                memory_mode=memory_mode,
            )

            tbl = render_terminal_table(
                task_order=task_order,
                results_dir=results_dir,
                current_task_id=active_tid,
                memory_mode=memory_mode,
                model_name=model_name,
            )
            live.update(tbl)
            time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="COPROMEM Live Monitor & Benchmark Reporter")
    parser.add_argument("--results_dir", type=str, default="results_test_benchmark", help="Directory containing task results")
    parser.add_argument("--report_file", type=str, default="results_test_benchmark/report_copromem.md", help="Path to write report markdown")
    parser.add_argument("--tasks", type=str, default="mini30", help="'mini30' or comma-separated task IDs")
    parser.add_argument("--memory_mode", type=str, default="copromem", help="Memory mode label")
    parser.add_argument("--model_name", type=str, default="google/gemini-2.5-flash", help="Agent model name")
    parser.add_argument("--watch", action="store_true", help="Run in continuous watch mode")
    parser.add_argument("--interval", type=float, default=3.0, help="Watch update interval in seconds")
    args = parser.parse_args()

    results_dir = REPO_ROOT / args.results_dir
    report_file = REPO_ROOT / args.report_file

    if args.tasks == "mini30":
        tasks = MINI30_TASKS
        suite_name = "mini30"
    elif args.tasks in ("admin100", "test100", "100"):
        tasks = ADMIN100_TASKS
        suite_name = "admin100"
    else:
        tasks = [int(t.strip()) for t in args.tasks.split(",") if t.strip()]
        suite_name = "custom"

    if args.watch:
        run_watcher(
            results_dir=results_dir,
            report_file=report_file,
            task_order=tasks,
            interval=args.interval,
            memory_mode=args.memory_mode,
            model_name=args.model_name,
        )
    else:
        update_markdown_report_file(
            report_file=report_file,
            task_order=tasks,
            results_dir=results_dir,
            suite_name=suite_name,
            model_name=args.model_name,
            memory_mode=args.memory_mode,
        )
        print(f"Benchmark report updated at: {report_file}")


if __name__ == "__main__":
    main()
