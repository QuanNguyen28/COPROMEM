#!/usr/bin/env python3
"""Bounded, local-only WebArena pilot for outcome-backed memory injection.

The reset hook must restore the website and print a digest of its complete
underlying state. A screenshot digest is checked separately after each arm.
Historical source memories are development material, not clean held-out data.
"""

from __future__ import annotations

import argparse
import hashlib
from http.client import HTTPConnection
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
WEBARENA = ROOT / "external" / "reasoning-bank" / "WebArena"
SOURCE_JSONL = WEBARENA / "memories_h2h_deepseek_v4_1_copromem" / "shopping_admin.jsonl"
BOOTSTRAP = ROOT / "src" / "copromem" / "local_pilot_bootstrap"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from copromem.copromem_memory_module import (  # noqa: E402
    COPROMEMMemoryModule, ProceduralMemoryItem, extract_intent_constraints,
)
from copromem.evidence_policy import TransferObservation, scope_signature  # noqa: E402
from run_head_to_head_nemotron_100 import run_single_task  # noqa: E402


# Fixed before looking at any pilot outcomes. Each family has one source and
# two calibration tasks; native-only evaluation availability varies by family.
ALLOCATION = {
    "245": {"source": 114, "calibration": [112, 113], "evaluation": [116]},
    "288": {"source": 13, "calibration": [11, 14], "evaluation": [12, 15]},
    "364": {"source": 208, "calibration": [209, 210], "evaluation": [211, 212]},
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _config(task_id: int, family: str) -> dict:
    path = WEBARENA / "config_files" / f"{task_id}.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    if str(config.get("intent_template_id")) != family:
        raise ValueError(f"Task {task_id} has unexpected template ID")
    if config.get("sites") != ["shopping_admin"]:
        raise ValueError(f"Task {task_id} is not Shopping Admin")
    if config.get("require_reset"):
        raise ValueError(f"Task {task_id} requires a task-specific reset")
    if config.get("eval", {}).get("eval_types") != ["string_match"]:
        raise ValueError(f"Task {task_id} is not native string_match only")
    if not set(config["eval"].get("reference_answers", {})) <= {
        "exact_match", "must_include"
    }:
        raise ValueError(f"Task {task_id} requires an LLM judge")
    return config


def prepare(output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"Pilot output already exists: {output}")
    rows = [json.loads(line) for line in SOURCE_JSONL.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    module = COPROMEMMemoryModule(api_key="")
    source_ids: dict[str, str] = {}
    for family, allocation in ALLOCATION.items():
        ids = [allocation["source"], *allocation["calibration"], *allocation["evaluation"]]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Overlapping allocation in family {family}")
        configs = {task_id: _config(task_id, family) for task_id in ids}
        signatures = {scope_signature(extract_intent_constraints(configs[task_id]["intent"]))
                      for task_id in [allocation["source"], *allocation["calibration"]]}
        if len(signatures) != 1:
            raise ValueError(f"Family {family} lacks a common structural scope")
        source_id = allocation["source"]
        source = next((row for row in rows if str(row.get("task_id")) == str(source_id)
                       and row.get("status") == "success"), None)
        if source is None or source.get("query") != configs[source_id]["intent"]:
            raise ValueError(f"No verified successful source row for task {source_id}")
        items = source.get("memory_items")
        if not isinstance(items, list) or not items or not all(isinstance(x, str) for x in items):
            raise ValueError(f"Source task {source_id} has no textual memory items")
        procedure = "\n\n".join(items)
        for task_id in allocation["evaluation"]:
            answers = configs[task_id]["eval"]["reference_answers"].values()
            for answer in answers:
                for value in answer if isinstance(answer, list) else [answer]:
                    if len(str(value)) >= 5 and str(value).lower() in procedure.lower():
                        raise ValueError(f"Source memory may contain answer for task {task_id}")
        memory_id = f"source_{source_id}"
        module.add_memory(ProceduralMemoryItem(
            memory_id=memory_id,
            intent=source["query"],
            title=f"Observed procedure from task {source_id}",
            description="Archived successful task procedure",
            procedure=procedure,
            constraints=extract_intent_constraints(source["query"]),
            domain="web_shopping_admin",
            success=True,
            source="archived_success",
            source_task_id=str(source_id),
        ))
        source_ids[family] = memory_id

    output.mkdir(parents=True)
    manifest = {
        "protocol": "local_evidence_pilot_v1",
        "model": "qwen3.5:9b",
        "allocation": ALLOCATION,
        "source_memory_ids": source_ids,
        "source_jsonl_sha256": _digest(SOURCE_JSONL),
        "data_status": "development pilot; archived source and publicly visible task configs",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "initial_state.json").write_text(json.dumps(module.export_state(), indent=2) + "\n")


def _local_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError(f"Pilot endpoint must be local HTTP: {url}")
    return url


def _preflight(reset_hook: Path, model_name: str = "qwen3.5:9b") -> None:
    if not reset_hook.is_file() or not os.access(reset_hook, os.X_OK):
        raise ValueError("Executable reset hook is required")
    with urlopen("http://127.0.0.1:11434/api/tags", timeout=4) as response:
        tags = json.loads(response.read().decode("utf-8"))
        if not any(item.get("name") == model_name
                   for item in tags.get("models", ())):
            raise RuntimeError(f"Ollama {model_name} is unavailable")
    site_url = _local_url(os.environ.get(
        "WA_SHOPPING_ADMIN", "http://127.0.0.1:7780/admin"
    ))
    parsed = urlparse(site_url)
    connection = HTTPConnection(parsed.hostname, parsed.port, timeout=4)
    try:
        try:
            connection.request("GET", parsed.path or "/")
            response = connection.getresponse()
        except OSError as exc:
            raise RuntimeError(f"WebArena unavailable at {site_url}: {exc}") from exc
        location = response.getheader("Location")
        if response.status >= 400:
            raise RuntimeError(f"WebArena returned HTTP {response.status}")
        if location and urlparse(location).hostname not in (None, "localhost", "127.0.0.1"):
            raise RuntimeError(f"WebArena redirects outside loopback: {location}")
    finally:
        connection.close()
    for family, allocation in ALLOCATION.items():
        for task_id in [allocation["source"], *allocation["calibration"],
                        *allocation["evaluation"]]:
            config = _config(task_id, family)
            if config.get("require_login"):
                storage = WEBARENA / config["storage_state"]
                if not storage.exists():
                    raise RuntimeError(f"Missing WebArena auth state: {storage}")


def _reset(reset_hook: Path, task_id: int) -> str:
    result = subprocess.run([str(reset_hook), str(task_id)], check=True,
                            capture_output=True, text=True, timeout=180)
    digest = result.stdout.strip()
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("Reset hook must print one lowercase SHA-256 state digest")
    return digest


def _local_environment(arm: str, model_name: str = "qwen3.5:9b") -> None:
    os.environ["WA_SHOPPING_ADMIN"] = "http://127.0.0.1:7780/admin"
    os.environ["WA_SHOPPING"] = "http://127.0.0.1:7780"
    os.environ["OPENROUTER_API_KEY"] = ""
    os.environ["OPENROUTER_BASE_URL"] = "http://127.0.0.1:11434/v1"
    os.environ["OPENAI_API_KEY"] = "ollama"
    os.environ["OPENAI_BASE_URL"] = "http://127.0.0.1:11434/v1"
    for key in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        os.environ[key] = ""
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                "http_proxy", "https_proxy", "all_proxy"):
        os.environ[key] = ""
    os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"
    os.environ["no_proxy"] = os.environ["NO_PROXY"]
    os.environ["OPENAI_JUDGE_MODEL"] = f"openai/{model_name}"
    os.environ["COPROMEM_LOCAL_ONLY"] = "1"
    os.environ["COPROMEM_CONTRACT_GUIDANCE"] = "false"
    os.environ["COPROMEM_RETRIEVAL_ARM"] = (
        "copromem_evidence" if arm == "evidence" else "copromem_v2"
    )
    os.environ["COPROMEM_PILOT_ADAPTER"] = str(
        ROOT / "integrations" / "reasoning_bank" / "copromem_adapter.py"
    )
    os.environ["PYTHONPATH"] = os.pathsep.join((
        str(BOOTSTRAP), str(ROOT / "src"), os.environ.get("PYTHONPATH", ""),
    ))


def _run_arm(output: Path, reset_hook: Path, task_id: int, family: str,
             arm: str, state: dict, model_name: str = "qwen3.5:9b") -> dict:
    task_dir = output / "runs" / str(task_id) / arm
    if task_dir.exists():
        raise FileExistsError(f"Refusing to overwrite pilot arm: {task_dir}")
    results_dir = task_dir / "results"
    memory_dir = task_dir / "memory"
    results_dir.mkdir(parents=True)
    memory_dir.mkdir()
    if arm != "no_memory":
        (memory_dir / "copromem_state.json").write_text(json.dumps(state))
    _local_environment(arm, model_name)
    initial_state_digest = _reset(reset_hook, task_id)
    result = run_single_task(
        task_id=task_id, model_name=f"openai/{model_name}",
        memory_mode="no_memory" if arm == "no_memory" else "copromem",
        results_dir=results_dir,
        memory_path=memory_dir / "shopping_admin.txt",
        max_steps=25, timeout_seconds=600, contract_guidance=False,
    )
    agent_failure = result.get("err_msg") and (
        "Could not parse a valid value after 6 retries." in result["err_msg"]
        or "Task timed out after" in result["err_msg"]
    )
    if result.get("err_msg") and not agent_failure:
        raise RuntimeError(f"Task {task_id}/{arm} failed operationally: {result['err_msg']}")
    screenshot = results_dir / f"webarena.{task_id}" / "screenshot_step_0.png"
    if not screenshot.exists():
        raise RuntimeError(f"Missing initial screenshot: {screenshot}")
    selection = {}
    state_path = memory_dir / "copromem_state.json"
    if state_path.exists():
        saved = json.loads(state_path.read_text())
        selection = {key: saved.get(key) for key in ("active_memory_id", "selection_reason")}
    injected_path = memory_dir / "shopping_admin.txt"
    injected = injected_path.read_text(encoding="utf-8") if injected_path.exists() else ""
    record = {**result, "arm": arm, "family": family,
              "initial_state_digest": initial_state_digest,
              "initial_screenshot_sha256": _digest(screenshot),
              "injected_chars": len(injected),
              "injected_sha256": hashlib.sha256(injected.encode("utf-8")).hexdigest(),
              **selection}
    (task_dir / "result.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def run(output: Path, reset_hook: Path) -> None:
    manifest = json.loads((output / "manifest.json").read_text())
    if manifest["protocol"] != "local_evidence_pilot_v1":
        raise ValueError("Unsupported pilot manifest")
    if _digest(SOURCE_JSONL) != manifest["source_jsonl_sha256"]:
        raise ValueError("Archived source changed after allocation")
    _preflight(reset_hook)
    module = COPROMEMMemoryModule(api_key="")
    module.load_state(json.loads((output / "initial_state.json").read_text()))
    records: list[dict] = []
    for family, allocation in manifest["allocation"].items():
        for index, task_id in enumerate(allocation["calibration"]):
            arms = ("no_memory", "ungated") if index % 2 == 0 else ("ungated", "no_memory")
            pair = [_run_arm(output, reset_hook, task_id, family, arm, module.export_state())
                    for arm in arms]
            by_arm = {item["arm"]: item for item in pair}
            if len({item["initial_state_digest"] for item in pair}) != 1 or len({
                item["initial_screenshot_sha256"] for item in pair
            }) != 1:
                raise RuntimeError(f"Task {task_id} started from different observed states")
            expected = manifest["source_memory_ids"][family]
            if by_arm["ungated"].get("active_memory_id") != expected:
                raise RuntimeError(f"Task {task_id} did not retrieve expected memory {expected}")
            source_id = str(allocation["source"])
            module.record_transfer_observation(TransferObservation(
                memory_id=expected, task_id=str(task_id), source_task_id=source_id,
                family=family,
                constraints=extract_intent_constraints(_config(task_id, family)["intent"]),
                without_memory_success=by_arm["no_memory"]["success"],
                with_memory_success=by_arm["ungated"]["success"],
                initial_state_digest=pair[0]["initial_state_digest"],
            ))
            records.extend(pair)
    evaluation_ids = {str(task_id) for allocation in manifest["allocation"].values()
                      for task_id in allocation["evaluation"]}
    module.freeze_evaluation(evaluation_ids)
    frozen_state = module.export_state()
    (output / "frozen_state.json").write_text(json.dumps(frozen_state, indent=2) + "\n")
    for family, allocation in manifest["allocation"].items():
        for index, task_id in enumerate(allocation["evaluation"]):
            arms = ("no_memory", "ungated", "evidence")
            arms = arms[index % 3:] + arms[:index % 3]
            trio = [_run_arm(output, reset_hook, task_id, family, arm, frozen_state)
                    for arm in arms]
            if len({item["initial_state_digest"] for item in trio}) != 1 or len({
                item["initial_screenshot_sha256"] for item in trio
            }) != 1:
                raise RuntimeError(f"Task {task_id} started from different observed states")
            by_arm = {item["arm"]: item for item in trio}
            if (by_arm["evidence"].get("active_memory_id") is not None
                    and by_arm["evidence"]["active_memory_id"] ==
                    by_arm["ungated"].get("active_memory_id")
                    and by_arm["evidence"]["injected_sha256"] !=
                    by_arm["ungated"]["injected_sha256"]):
                raise RuntimeError(f"Task {task_id} changed prompt beyond the selection decision")
            records.extend(trio)
    _report(output, records)


def _report(output: Path, records: list[dict]) -> None:
    by_task: dict[int, dict[str, dict]] = {}
    for item in records:
        by_task.setdefault(item["task_id"], {})[item["arm"]] = item
    evaluation = {task_id for allocation in ALLOCATION.values()
                  for task_id in allocation["evaluation"]}
    eval_rows = [by_task[task_id] for task_id in sorted(evaluation)]
    gains = [row["evidence"]["family"] for row in eval_rows
             if row["evidence"]["success"] and not row["no_memory"]["success"]]
    harms = [row["evidence"]["family"] for row in eval_rows
             if row["no_memory"]["success"] and not row["evidence"]["success"]]
    vs_ungated = sum(row["evidence"]["success"] for row in eval_rows) - sum(
        row["ungated"]["success"] for row in eval_rows)
    summary = {
        "status": "development pilot, no SOTA or causal claim without audited reset",
        "evaluated_tasks": len(eval_rows),
        "beneficial_flip_families": gains,
        "harmful_flip_families": harms,
        "success_delta_vs_ungated": vs_ungated,
        "abstentions": sum(not row["evidence"].get("active_memory_id") for row in eval_rows),
        "go_signal": len(gains) >= 2 and len(set(gains)) >= 2 and len(harms) <= 1
                     and vs_ungated > 0,
        "tasks": by_task,
    }
    (output / "report.json").write_text(json.dumps(summary, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "run"))
    parser.add_argument("--output", type=Path,
                        default=ROOT / "artifacts" / "local_evidence_pilot_v1")
    parser.add_argument("--reset-hook", type=Path,
                        help="Executable: restore full site state and print its SHA-256 digest")
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare(args.output)
    else:
        if args.reset_hook is None:
            parser.error("run requires --reset-hook")
        run(args.output, args.reset_hook.resolve())


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, FileNotFoundError, FileExistsError, OSError) as exc:
        raise SystemExit(f"Pilot stopped: {exc}") from None
