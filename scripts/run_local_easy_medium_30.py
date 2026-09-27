#!/usr/bin/env python3
"""Resume-safe 30-task Shopping Admin development pilot using local Ollama."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import time

from PIL import Image, ImageDraw

import run_local_evidence_pilot as base
from copromem.copromem_memory_module import COPROMEMMemoryModule, extract_intent_constraints
from copromem.evidence_policy import TransferObservation


OUTPUT = base.ROOT / "artifacts" / "local_easy_medium_30"
MODEL = "copromem-qwen3.5-9b-16k:latest"
EASY = [41, 42, 43, 94, 95, 112, 113, 116, 198, 199, 200,
        209, 210, 211, 212]
MEDIUM = [11, 12, 14, 15, 77, 78, 79, 128, 129, 130, 131,
          184, 185, 187, 193]
SOURCE_IDS = {int(row["source"]) for row in base.ALLOCATION.values()}
CALIBRATION_IDS = {int(task_id) for row in base.ALLOCATION.values()
                   for task_id in row["calibration"]}


def _task(task_id: int, tier: str) -> dict:
    config = json.loads((base.WEBARENA / "config_files" / f"{task_id}.json").read_text())
    family = str(config["intent_template_id"])
    base._config(task_id, family)
    return {"task_id": task_id, "family": family, "tier": tier}


def prepare(output: Path) -> None:
    all_tasks = [_task(task_id, "easy") for task_id in EASY]
    all_tasks += [_task(task_id, "medium") for task_id in MEDIUM]
    ids = {row["task_id"] for row in all_tasks}
    if len(all_tasks) != 30 or len(ids) != 30 or ids & SOURCE_IDS:
        raise ValueError("Expected exactly 30 distinct tasks, disjoint from sources")
    if len(ids & CALIBRATION_IDS) != 6:
        raise ValueError("Expected six calibration tasks")
    rows = [json.loads(line) for line in base.SOURCE_JSONL.read_text().splitlines()
            if line.strip()]
    procedures = []
    for source_id in SOURCE_IDS:
        source = next(row for row in rows if str(row.get("task_id")) == str(source_id)
                      and row.get("status") == "success")
        procedures.append("\n\n".join(source["memory_items"]).lower())
    evaluation = [row for row in all_tasks if row["task_id"] not in CALIBRATION_IDS]
    for row in evaluation:
        answers = base._config(row["task_id"], row["family"])["eval"]["reference_answers"]
        for answer in answers.values():
            for value in answer if isinstance(answer, list) else [answer]:
                if len(str(value)) >= 5 and any(str(value).lower() in p for p in procedures):
                    raise ValueError(f"Archived memory may contain answer for {row['task_id']}")
    base.prepare(output)
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.update({"protocol": "local_easy_medium_30_v1", "model": MODEL,
                     "base_model": "qwen3.5:9b", "num_ctx": 16384,
                     "tasks": all_tasks,
                     "evaluation_tasks": evaluation, "calibration_count": 6,
                     "evaluation_count": 24})
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


def _arm(output: Path, reset_hook: Path, row: dict, arm: str, state: dict,
         model_name: str) -> dict:
    task_id = row["task_id"]
    result_path = output / "runs" / str(task_id) / arm / "result.json"
    if result_path.exists():
        result = json.loads(result_path.read_text())
        if result.get("task_id") != task_id or result.get("arm") != arm:
            raise ValueError(f"Invalid saved arm: {result_path}")
        return result
    task_dir = result_path.parent
    if task_dir.exists():
        quarantine = output / "failures" / "incomplete"
        quarantine.mkdir(parents=True, exist_ok=True)
        shutil.move(str(task_dir), str(quarantine / f"{task_id}_{arm}_{time.time_ns()}"))
    result = base._run_arm(output, reset_hook, task_id, row["family"], arm, state,
                           model_name=model_name)
    print(f"task={task_id} tier={row['tier']} arm={arm} success={result['success']}", flush=True)
    return result


def _check_pair(output: Path, task_id: int, records: list[dict]) -> None:
    if len({row["initial_state_digest"] for row in records}) != 1:
        raise RuntimeError(f"Task {task_id} started from different site snapshots")
    if len({row["initial_screenshot_sha256"] for row in records}) == 1:
        return
    # Magento gives the tied Bestseller rows in varying order even from the
    # same image snapshot. Ignore only that initial dashboard table region.
    hashes = set()
    for row in records:
        screenshot = (output / "runs" / str(task_id) / row["arm"] / "results" /
                      f"webarena.{task_id}" / "screenshot_step_0.png")
        image = Image.open(screenshot).convert("RGB")
        if image.size != (1500, 1280):
            raise RuntimeError(f"Unexpected initial screenshot size for task {task_id}")
        ImageDraw.Draw(image).rectangle((580, 650, 1450, 900), fill="white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        hashes.add(hashlib.sha256(buffer.getvalue()).hexdigest())
    if len(hashes) != 1:
        raise RuntimeError(f"Task {task_id} started from different screenshots")


def run(output: Path, reset_hook: Path) -> None:
    manifest = json.loads((output / "manifest.json").read_text())
    if manifest["protocol"] != "local_easy_medium_30_v1":
        raise ValueError("Wrong manifest protocol")
    if base._digest(base.SOURCE_JSONL) != manifest["source_jsonl_sha256"]:
        raise ValueError("Archived source changed after allocation")
    tokenizer_cache = output / "tokenizer_cache"
    tokenizer_file = tokenizer_cache / "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"
    if (not tokenizer_file.is_file() or base._digest(tokenizer_file) !=
            "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"):
        raise ValueError("Missing or invalid pinned cl100k tokenizer cache")
    os.environ["TIKTOKEN_CACHE_DIR"] = str(tokenizer_cache.resolve())
    if manifest["model"] != MODEL or manifest.get("num_ctx") != 16384:
        raise ValueError("Unexpected model configuration")
    base._preflight(reset_hook, MODEL)
    module = COPROMEMMemoryModule(api_key="")
    module.load_state(json.loads((output / "initial_state.json").read_text()))
    tiers = {row["task_id"]: row["tier"] for row in manifest["tasks"]}
    records = []
    for family, allocation in manifest["allocation"].items():
        for index, task_id in enumerate(allocation["calibration"]):
            row = {"task_id": task_id, "family": family, "tier": tiers[task_id]}
            arms = ("no_memory", "ungated") if index % 2 == 0 else ("ungated", "no_memory")
            pair = [_arm(output, reset_hook, row, arm, module.export_state(), MODEL)
                    for arm in arms]
            _check_pair(output, task_id, pair)
            by_arm = {item["arm"]: item for item in pair}
            expected = manifest["source_memory_ids"][family]
            if by_arm["ungated"].get("active_memory_id") != expected:
                raise RuntimeError(f"Task {task_id} retrieved an unexpected memory")
            module.record_transfer_observation(TransferObservation(
                memory_id=expected, task_id=str(task_id),
                source_task_id=str(allocation["source"]), family=family,
                constraints=extract_intent_constraints(base._config(task_id, family)["intent"]),
                without_memory_success=by_arm["no_memory"]["success"],
                with_memory_success=by_arm["ungated"]["success"],
                initial_state_digest=pair[0]["initial_state_digest"],
            ))
            records.extend(pair)
    evaluation_ids = {str(row["task_id"]) for row in manifest["evaluation_tasks"]}
    module.freeze_evaluation(evaluation_ids)
    frozen_state = module.export_state()
    (output / "frozen_state.json").write_text(json.dumps(frozen_state, indent=2) + "\n")
    for index, row in enumerate(manifest["evaluation_tasks"]):
        task_id = row["task_id"]
        arms = ("no_memory", "ungated", "evidence")
        arms = arms[index % 3:] + arms[:index % 3]
        trio = [_arm(output, reset_hook, row, arm, frozen_state, MODEL)
                for arm in arms]
        _check_pair(output, task_id, trio)
        by_arm = {item["arm"]: item for item in trio}
        if (by_arm["evidence"].get("active_memory_id") is not None
                and by_arm["evidence"]["active_memory_id"] ==
                by_arm["ungated"].get("active_memory_id")
                and by_arm["evidence"]["injected_sha256"] !=
                by_arm["ungated"]["injected_sha256"]):
            raise RuntimeError(f"Task {task_id} changed prompt beyond memory selection")
        records.extend(trio)
    _report(output, manifest, records)


def _report(output: Path, manifest: dict, records: list[dict]) -> None:
    tasks = {}
    for record in records:
        tasks.setdefault(record["task_id"], {})[record["arm"]] = record
    eval_rows = [(row, tasks[row["task_id"]]) for row in manifest["evaluation_tasks"]]
    gains = [row["family"] for row, results in eval_rows
             if results["evidence"]["success"] and not results["no_memory"]["success"]]
    harms = [row["family"] for row, results in eval_rows
             if results["no_memory"]["success"] and not results["evidence"]["success"]]
    delta = sum(results["evidence"]["success"] - results["ungated"]["success"]
                for _, results in eval_rows)
    summary = {
        "status": "development pilot; publicly visible task configs and archived source memories",
        "unique_tasks_run": len(tasks), "calibration_tasks": 6, "evaluated_tasks": len(eval_rows),
        "success_by_arm": {arm: sum(results[arm]["success"] for _, results in eval_rows)
                           for arm in ("no_memory", "ungated", "evidence")},
        "success_by_tier": {tier: {arm: sum(results[arm]["success"] for row, results in eval_rows
                                          if row["tier"] == tier)
                                  for arm in ("no_memory", "ungated", "evidence")}
                            for tier in ("easy", "medium")},
        "beneficial_flip_families": gains, "harmful_flip_families": harms,
        "success_delta_vs_ungated": delta,
        "abstentions": sum(not results["evidence"].get("active_memory_id")
                           for _, results in eval_rows),
        "go_signal": len(set(gains)) >= 2 and len(harms) <= 1 and delta > 0,
        "tasks": tasks,
    }
    (output / "report.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "run"))
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--reset-hook", type=Path)
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare(args.output)
    else:
        if args.reset_hook is None:
            parser.error("run requires --reset-hook")
        run(args.output, args.reset_hook.resolve())
