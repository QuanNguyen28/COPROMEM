"""Corrected, durable exposure-labelled AppWorld plumbing smoke.

This script is intentionally manifest-pinned.  It emits no task-private native
output: raw action source is journaled, while output is represented by a digest.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, "src")
from copromem.appworld_acquisition_gate import AcquisitionJournal, AcquisitionRef, AcquisitionIncomplete
from copromem.appworld_comparison_adapter import AcquisitionIdentity, CoProMemAppWorldAdapter, RawAcquisitionTrajectory, TrialInput
from copromem.checkpoints import RunStore, digest
from copromem.corrected_smoke_ledger import CorrectedSmokeLedger
from copromem.reme_paper_lifecycle import ReMeMemory, ReMePaperLifecycle

ROOT = Path("artifacts/research/reme_copromem_comparison/corrected_direct_deepseek_smoke")
HISTORICAL = [
    Path("artifacts/research/reme_copromem_comparison/openrouter_brokered_smoke"),
    Path("artifacts/research/reme_copromem_comparison/direct_deepseek_successor_smoke"),
]
WORKER = "/mnt/e/Project/AAMAS/COPROMEM/research/containers/appworld/real_worker.py"
PYTHON = "/home/xiqhq/copromem-appworld/venv/bin/python"
TOOL = {"type": "function", "function": {"name": "execute_python", "description": "Execute one AppWorld Python action.", "strict": True,
        "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"], "additionalProperties": False}}}
ARMS = ("no_memory", "reme_fixed_faithful_adaptation", "reme_dynamic_faithful_adaptation", "copromem_v2")


def api_key() -> str:
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("DEEPSEEK_API_KEY="):
            return line.split("=", 1)[1].strip().strip("'\"")
    raise RuntimeError("DEEPSEEK_API_KEY is unavailable")


def open_worker(task_id: str, experiment_name: str):
    process = subprocess.Popen(["wsl.exe", "-d", "Ubuntu", "--cd", "/home/xiqhq/copromem-appworld", "--", PYTHON, WORKER],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    def send(request: dict) -> dict:
        assert process.stdin and process.stdout
        process.stdin.write(json.dumps(request) + "\n")
        process.stdin.flush()
        reply = process.stdout.readline()
        if not reply:
            raise RuntimeError("native AppWorld worker exited without a response")
        return json.loads(reply)
    return process, send({"op": "start", "task_id": task_id, "experiment_name": experiment_name}), send


def model_call(prompt: str, ledger: CorrectedSmokeLedger, metadata: dict) -> tuple[str | None, dict]:
    key = str(time.time_ns())
    ledger.reserve(key, 0.006, metadata)
    request = {"model": "deepseek-flash", "messages": [
        {"role": "system", "content": "You are an AppWorld executor. Return no prose: call execute_python exactly once with the next safe Python action."},
        {"role": "user", "content": prompt + "\n\nCall execute_python exactly once now."}],
        "tools": [TOOL], "tool_choice": {"type": "function", "function": {"name": "execute_python"}},
        "max_tokens": 128, "stream": False, "reasoning_effort": "none"}
    started = time.perf_counter()
    try:
        raw = urllib.request.urlopen(urllib.request.Request("https://api.deepseek.com/chat/completions", data=json.dumps(request).encode(),
            headers={"Authorization": "Bearer " + api_key(), "Content-Type": "application/json"}, method="POST"), timeout=45)
        response = json.loads(raw.read())
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise RuntimeError("direct DeepSeek authentication failed") from error
        return None, {"key": key, "finish_reason": f"http_{error.code}", "tool_valid": False, "latency_seconds": time.perf_counter() - started, "tokens": {}}
    usage = response.get("usage", {})
    cost = (usage.get("prompt_tokens", 0) * .3 + usage.get("completion_tokens", 0) * 1.2) / 1e6
    ledger.settle(key, cost)
    choice = response["choices"][0]
    calls = choice["message"].get("tool_calls") or []
    reasoning = usage.get("reasoning_tokens", usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0))
    telemetry = {"key": key, "response_model": response.get("model"), "finish_reason": choice.get("finish_reason"),
                 "tool_valid": False, "latency_seconds": time.perf_counter() - started,
                 "tokens": {"prompt": usage.get("prompt_tokens", 0), "completion": usage.get("completion_tokens", 0)}, "actual_usd": cost}
    if response.get("model") != "deepseek-flash" or reasoning or len(calls) != 1:
        return None, telemetry
    try:
        code = json.loads(calls[0]["function"]["arguments"])["code"]
    except (KeyError, TypeError, json.JSONDecodeError):
        return None, telemetry
    telemetry["tool_valid"] = isinstance(code, str) and bool(code.strip())
    return (code if telemetry["tool_valid"] else None), telemetry


def run_trajectory(task_id: str, arm: str, memory: str, ledger: CorrectedSmokeLedger, *, acquisition: bool) -> tuple[dict, list[dict], list[str], dict]:
    process, start, send = open_worker(task_id, arm)
    base = "Use only execute_python for AppWorld. " + start["instruction"] + "\n" + json.dumps(start["app_descriptions"]) + memory
    journal = AcquisitionJournal(RunStore(ROOT), AcquisitionRef(task_id, 0, 0)) if acquisition else None
    if journal:
        journal.start(task_manifest_sha256=digest({"task_id": task_id, "instruction": start["instruction"]}), base_prompt_sha256=digest(base), tool_schema_sha256=digest(TOOL))
    rows, actions = [], []
    for iteration in range(10):
        code, telemetry = model_call(base, ledger, {"arm": arm, "role": "executor", "task_id": task_id,
            "phase": "acquisition" if acquisition else "evaluation", "trial": 0, "iteration": iteration, "model": "deepseek-flash"})
        RunStore(ROOT).write("call_telemetry", telemetry["key"], {k: v for k, v in telemetry.items() if k != "key"})
        rows.append(telemetry)
        if code is None:
            break
        if journal:
            journal.plan_action(iteration, code=code)
        outcome = send({"op": "action", "code": code})
        actions.append(code)
        if journal:
            journal.action(iteration, code=code, native_output=outcome, completed=bool(outcome["completed"]))
        if outcome["completed"]:
            break
        base += "\nPrevious native action output: " + json.dumps(outcome) + "\nChoose the next action."
    score = send({"op": "finish"})
    process.wait(timeout=10)
    if journal:
        journal.finish(official_score=score)
    return score, rows, actions, start


def memory_bundle(raw: list[RawAcquisitionTrajectory], trial: TrialInput) -> dict[str, tuple[str, str]]:
    successful = [item for item in raw if item.success]
    if not successful:
        raise AcquisitionIncomplete("no successful acquisition can produce a provenance-bound memory")
    ids = [item.identity.value for item in successful]
    reme_fixed = ReMePaperLifecycle([ReMeMemory(f"reme-fixed::{identity}") for identity in ids], dynamic=False)
    reme_dynamic = ReMePaperLifecycle([ReMeMemory(f"reme-dynamic::{identity}") for identity in ids], dynamic=True)
    fixed = "ReMe fixed acquired trace IDs: " + ", ".join(reme_fixed.acquired.memories)
    dynamic = "ReMe dynamic acquired trace IDs: " + ", ".join(reme_dynamic.state_for_trial_stream(0).memories) + "; update utility/frequency only after this trial."
    copromem = CoProMemAppWorldAdapter(api_key="", decomposition_call_cap=0)
    for item in raw:
        copromem.ingest(item)
    copromem.consolidate()
    copro = copromem.prepare_trial(trial, 0)
    if not copro.strip():
        raise AcquisitionIncomplete("CoProMem v2 produced no admitted method-specific memory")
    return {"reme_fixed_faithful_adaptation": (fixed, "reme-paper-lifecycle-adapter"),
            "reme_dynamic_faithful_adaptation": (dynamic, "reme-paper-lifecycle-adapter-dynamic"),
            "copromem_v2": (copro, "copromem-v2-adapter")}


def main() -> None:
    if (ROOT / "corrected_result.json").exists():
        raise SystemExit("corrected smoke is terminal; replay requires a new authorization")
    store = RunStore(ROOT)
    ledger = CorrectedSmokeLedger(store, historical_roots=HISTORICAL)
    acquisition = []
    for task_id in ("50e1ac9_1", "50e1ac9_2"):
        score, calls, actions, start = run_trajectory(task_id, "shared_acquisition", "", ledger, acquisition=True)
        acquisition.append((task_id, score, calls, actions, start))
    raw = [RawAcquisitionTrajectory(AcquisitionIdentity(task_id, 0, 0), start["instruction"], "appworld", bool(score["success"]), tuple(actions), {"official_score": score})
           for task_id, score, calls, actions, start in acquisition]
    # Start evaluation only after the acquisition journal and method memories can be verified.
    preflight_process, evaluation_start, _ = open_worker("fac291d_1", "corrected_preflight")
    # This loads only the registered task interface for memory binding.  It is
    # not an execution/scoring attempt and makes no model call.
    preflight_process.terminate()
    preflight_process.wait(timeout=10)
    trial = TrialInput("fac291d_1", evaluation_start["instruction"], "appworld", base_prompt="Use only execute_python for AppWorld. " + evaluation_start["instruction"] + "\n" + json.dumps(evaluation_start["app_descriptions"]), tool_spec=TOOL)
    try:
        bundle = memory_bundle(raw, trial)
    except AcquisitionIncomplete as error:
        store.write("corrected_result", "gate_failure", {
            "status": "acquisition_gate_failed", "reason": str(error),
            "acquisition": [{"task_id": task, "official_score": score, "calls": calls}
                            for task, score, calls, _, _ in acquisition],
            "ledger_exposure_usd": ledger.charged_or_reserved,
        })
        (ROOT / "corrected_result.json").write_text(json.dumps({"status": "acquisition_gate_failed", "reason": str(error),
            "ledger_exposure_usd": ledger.charged_or_reserved}, indent=2) + "\n", encoding="utf-8")
        return
    for task_id, *_ in acquisition:
        journal = AcquisitionJournal(store, AcquisitionRef(task_id, 0, 0))
        for method, (text, provenance) in bundle.items():
            journal.admit_memory(method=method, provenance=provenance, memory_text=text)
        journal.approve_evaluation()
    results = {}
    for arm in ARMS:
        memory = "" if arm == "no_memory" else "\n\n" + bundle[arm][0]
        score, calls, _, _ = run_trajectory("fac291d_1", arm, memory, ledger, acquisition=False)
        results[arm] = {"official_score": score, "calls": calls, "memory_provenance": None if arm == "no_memory" else bundle[arm][1],
                        "memory_sha256": None if arm == "no_memory" else digest(bundle[arm][0])}
    store.write("corrected_result", "final", {"acquisition": [{"task_id": task, "official_score": score, "calls": calls} for task, score, calls, _, _ in acquisition],
                                                  "evaluation": results, "ledger_exposure_usd": ledger.charged_or_reserved})
    (ROOT / "corrected_result.json").write_text(json.dumps({"status": "complete", "ledger_exposure_usd": ledger.charged_or_reserved}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
