#!/usr/bin/env python3
"""Read-only live monitor for artifacts/local_easy_medium_30."""

from __future__ import annotations

import argparse
import ast
import json
import re
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.table import Table


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "local_easy_medium_30"
console = Console()


def _status(output: Path, task: dict, arm: str) -> tuple[str, str]:
    task_id = task["task_id"]
    result_path = output / "runs" / str(task_id) / arm / "result.json"
    if result_path.is_file():
        try:
            result = json.loads(result_path.read_text())
            label = "PASS" if result.get("success") else "FAIL"
            return label, f"{result.get('steps', '?')} steps"
        except (OSError, json.JSONDecodeError):
            return "READ ERR", ""

    arm_dir = output / "runs" / str(task_id) / arm
    logs = sorted(arm_dir.glob("results/**/experiment.log"),
                  key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    for log in logs:
        try:
            text = log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "Saving summary info." not in text:
            steps = len(re.findall(r"browsergym\.experiments\.loop - INFO - action:", text))
            return "RUN", f"{steps} steps"
    return "WAIT", ""


def _prediction(output: Path, task_id: int, arm: str) -> str:
    arm_dir = output / "runs" / str(task_id) / arm
    logs = sorted(arm_dir.glob("results/**/experiment.log"),
                  key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    for log in logs:
        try:
            lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            marker = "send_msg_to_user("
            if marker not in line:
                continue
            raw = line[line.index(marker) + len(marker):]
            end = raw.rfind(")")
            if end >= 0:
                raw = raw[:end].strip()
            try:
                value = ast.literal_eval(raw)
                return str(value).strip()
            except (ValueError, SyntaxError):
                return raw.strip(" '\"")
    return ""


def render_table(output: Path) -> Table:
    manifest_path = output / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing pilot manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    tasks = manifest["tasks"]
    calibration = {task_id for row in manifest["allocation"].values()
                   for task_id in row["calibration"]}
    expected_arms = {"no_memory", "ungated"}
    table = Table(title=(f"COPROMEM local pilot | {manifest.get('model')} | "
                         f"{manifest.get('num_ctx', '?')} ctx"), expand=True)
    table.add_column("Tier", width=8)
    table.add_column("Task", width=6)
    table.add_column("Phase", width=12)
    for arm in ("no_memory", "ungated", "evidence"):
        table.add_column(arm, justify="center", width=18)

    completed = 0
    successes = {arm: 0 for arm in ("no_memory", "ungated", "evidence")}
    for task in tasks:
        task_id = task["task_id"]
        arms = ("no_memory", "ungated") if task_id in calibration else (
            "no_memory", "ungated", "evidence")
        cells = []
        for arm in ("no_memory", "ungated", "evidence"):
            if arm not in arms:
                cells.append("—")
                continue
            state, detail = _status(output, task, arm)
            cells.append(f"{state} {detail}".strip())
            if state in {"PASS", "FAIL"}:
                completed += 1
                if task_id not in calibration:
                    successes[arm] += int(state == "PASS")
        table.add_row(task["tier"], str(task_id),
                      "calibration" if task_id in calibration else "evaluation", *cells)

    total_arms = sum(2 if row["task_id"] in calibration else 3 for row in tasks)
    report_path = output / "report.json"
    overall = "finished" if report_path.exists() else "running"
    summary = (f"{overall}: {completed}/{total_arms} arms | "
               f"completed eval successes (no-memory / ungated / evidence): "
               f"{successes['no_memory']} / {successes['ungated']} / {successes['evidence']}")
    table.caption = summary
    return table


def render_markdown(output: Path) -> str:
    manifest = json.loads((output / "manifest.json").read_text())
    tasks = manifest["tasks"]
    calibration = {task_id for row in manifest["allocation"].values()
                   for task_id in row["calibration"]}
    task_results: dict[int, dict[str, dict]] = {}
    for task in tasks:
        tid = task["task_id"]
        task_results[tid] = {}
        arms = ("no_memory", "ungated") if tid in calibration else (
            "no_memory", "ungated", "evidence")
        for arm in arms:
            path = output / "runs" / str(tid) / arm / "result.json"
            if path.is_file():
                try:
                    task_results[tid][arm] = json.loads(path.read_text())
                except (OSError, json.JSONDecodeError):
                    pass

    total_arms = sum(2 if row["task_id"] in calibration else 3 for row in tasks)
    completed = sum(len(arms) for arms in task_results.values())
    evaluations = [row for row in tasks if row["task_id"] not in calibration]
    full_eval = [row for row in evaluations
                 if all(arm in task_results[row["task_id"]]
                        for arm in ("no_memory", "ungated", "evidence"))]
    running = []
    for task in tasks:
        tid = task["task_id"]
        arms = ("no_memory", "ungated") if tid in calibration else (
            "no_memory", "ungated", "evidence")
        for arm in arms:
            if arm in task_results[tid]:
                continue
            state, detail = _status(output, task, arm)
            if state == "RUN":
                running.append(f"task {tid}/{arm} ({detail})")
    status_text = ", ".join(running) if running else "between tasks / waiting for next arm"
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    report_path = output / "report.json"
    overall = "Complete" if report_path.exists() else "Running"

    lines = [
        "# Live Browser WebArena Benchmark Report — COPROMEM Evidence Pilot",
        "",
        f"- **Updated:** {timestamp}",
        f"- **Pilot status:** {overall}",
        "- **Suite:** 30 Shopping Admin tasks (15 easy, 15 medium); 6 calibration + 24 evaluation",
        f"- **Agent model:** `{manifest.get('model')}` (local Ollama; context {manifest.get('num_ctx')})",
        "- **Judge:** WebArena native `string_match` (`exact_match` / `must_include`); no external judge",
        f"- **Progress:** {completed}/{total_arms} arms ({100 * completed / total_arms:.1f}%)",
        f"- **Live status:** {status_text}",
        "- **Site snapshot:** Docker image `copromem-shopping-admin-pilot:local`; reset digest is checked before every arm",
        "- **Model calls:** local loopback Ollama only",
        "",
        "## 1. Summary Comparison",
        "",
        "Counts below include completed evaluation tasks only. The matched column compares tasks with all three arms finished.",
        "",
        "| Arm | Completed evaluation successes | Completed / 24 | Matched successes / 24 matched |",
        "| :--- | :---: | :---: | :---: |",
    ]
    for arm in ("no_memory", "ungated", "evidence"):
        done = [row for row in evaluations if arm in task_results[row["task_id"]]]
        passed = sum(bool(task_results[row["task_id"]][arm].get("success")) for row in done)
        matched_passed = sum(bool(task_results[row["task_id"]][arm].get("success"))
                             for row in full_eval)
        matched_den = len(full_eval)
        matched = f"{matched_passed}/{matched_den}" if matched_den else "—"
        lines.append(f"| `{arm}` | {passed} | {len(done)}/24 | {matched} |")

    lines.extend([
        "",
        "## 2. Outcome Matrix",
        "",
        "| # | Tier | Task | Intent | Phase | No memory | Ungated | Evidence gate |",
        "| :---: | :---: | :---: | :--- | :---: | :--- | :--- | :--- |",
    ])
    for index, task in enumerate(tasks, 1):
        tid = task["task_id"]
        config_path = ROOT / "external" / "reasoning-bank" / "WebArena" / "config_files" / f"{tid}.json"
        try:
            config = json.loads(config_path.read_text())
            intent = str(config.get("intent", "")).replace("|", "\\|").replace("\n", " ")
            answers = config.get("eval", {}).get("reference_answers", {})
            expected = "; ".join(str(value) for value in answers.values()) or "—"
        except (OSError, json.JSONDecodeError):
            intent, expected = f"Task {tid}", "—"
        phase = "calibration" if tid in calibration else "evaluation"
        cells = []
        for arm in ("no_memory", "ungated", "evidence"):
            if phase == "calibration" and arm == "evidence":
                cells.append("—")
            elif arm in task_results[tid]:
                result = task_results[tid][arm]
                badge = "PASS" if result.get("success") else "FAIL"
                memory = result.get("active_memory_id")
                suffix = f", mem `{memory}`" if memory else ""
                cells.append(f"**{badge}** ({result.get('steps', '?')} steps{suffix})")
            else:
                state, detail = _status(output, task, arm)
                cells.append(f"**{state}** ({detail})" if detail else f"*{state}*")
        lines.append(f"| {index} | {task['tier']} | {tid} | {intent} | {phase} | "
                     f"{cells[0]} | {cells[1]} | {cells[2]} |")

    lines.extend([
        "",
        "## 3. Task-by-task results",
        "",
    ])
    for index, task in enumerate(tasks, 1):
        tid = task["task_id"]
        phase = "calibration" if tid in calibration else "evaluation"
        config_path = ROOT / "external" / "reasoning-bank" / "WebArena" / "config_files" / f"{tid}.json"
        try:
            config = json.loads(config_path.read_text())
            intent = str(config.get("intent", f"Task {tid}"))
            refs = config.get("eval", {}).get("reference_answers", {})
            expected = "; ".join(str(value) for value in refs.values()) or "—"
        except (OSError, json.JSONDecodeError):
            intent, expected = f"Task {tid}", "—"
        lines.extend([
            "<details>",
            f"<summary>#{index} — Task {tid} ({task['tier']}, {phase})</summary>",
            "",
            f"**Intent:** {intent}",
            "",
            f"**Reference answer:** `{expected}`",
            "",
            "| Arm | Outcome | Steps | Duration | Extracted answer | Selected memory | Selection reason |",
            "| :--- | :---: | ---: | ---: | :--- | :--- | :--- |",
        ])
        expected_task_arms = ("no_memory", "ungated") if phase == "calibration" else (
            "no_memory", "ungated", "evidence")
        for arm in expected_task_arms:
            result = task_results[tid].get(arm)
            if result:
                outcome = "PASS" if result.get("success") else "FAIL"
                steps = str(result.get("steps", "—"))
                elapsed = result.get("elapsed")
                duration = f"{float(elapsed):.1f}s" if elapsed is not None else "—"
                memory = str(result.get("active_memory_id") or "—")
                reason = str(result.get("selection_reason") or "—").replace("|", "\\|")
                prediction = _prediction(output, tid, arm) or "*(no final answer in log)*"
                prediction = prediction.replace("|", "\\|").replace("\n", " ")
                lines.append(f"| `{arm}` | **{outcome}** | {steps} | {duration} | {prediction} | `{memory}` | {reason} |")
                if result.get("err_msg"):
                    error = str(result["err_msg"]).replace("|", "\\|").replace("\n", " ")
                    lines.extend(["", f"Run note for `{arm}`: `{error}`", ""])
            else:
                state, detail = _status(output, task, arm)
                lines.append(f"| `{arm}` | **{state}** | — | — | {detail or '—'} | — | — |")
        lines.extend(["", "</details>", ""])

    lines.extend([
        "## 4. Protocol and interpretation",
        "",
        f"- Calibration tasks: {len(calibration)}. Evaluation tasks: {len(evaluations)}.",
        f"- Evaluation tasks with all three arms complete: {len(full_eval)}/{len(evaluations)}.",
        "- Calibration uses paired no-memory and ungated runs; the evidence state is frozen before evaluation.",
        "- This is a development pilot using archived source memories and public task configurations. It does not establish a SOTA result.",
        "- Raw per-arm logs, screenshots, prompt hashes, and selection metadata are kept under `artifacts/local_easy_medium_30/runs/`.",
        "",
    ])
    return "\n".join(lines)


def write_report(output: Path, report_file: Path) -> None:
    content = render_markdown(output)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = report_file.with_suffix(report_file.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(report_file)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--watch", action="store_true", help="Refresh continuously")
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--report-file", type=Path,
                        default=ROOT / "artifacts" / "live_browser_benchmark_report.md")
    parser.add_argument("--terminal", action="store_true",
                        help="Also display the status table in the terminal")
    args = parser.parse_args()
    while True:
        write_report(args.output, args.report_file)
        if args.terminal:
            console.print(render_table(args.output))
        else:
            print(f"Updated {args.report_file}", flush=True)
        if not args.watch or (args.output / "report.json").exists():
            break
        time.sleep(max(1.0, args.interval))


if __name__ == "__main__":
    main()
