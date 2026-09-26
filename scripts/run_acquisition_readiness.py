"""Manifest-pinned, acquisition-only readiness run. It never opens evaluation."""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, "src")
from copromem.appworld_acquisition_gate import AcquisitionJournal, AcquisitionRef
from copromem.checkpoints import RunStore, digest
from copromem.corrected_smoke_ledger import CorrectedSmokeLedger

ROOT = Path("artifacts/research/reme_copromem_comparison/acquisition_readiness")
HISTORICAL = [Path("artifacts/research/reme_copromem_comparison/openrouter_brokered_smoke"),
              Path("artifacts/research/reme_copromem_comparison/direct_deepseek_successor_smoke"),
              Path("artifacts/research/reme_copromem_comparison/corrected_direct_deepseek_smoke")]
TASKS = (("50e1ac9_1", (101, 202, 303)), ("50e1ac9_2", (101, 202, 303)))
WORKER = "/mnt/e/Project/AAMAS/COPROMEM/research/containers/appworld/real_worker.py"
PYTHON = "/home/xiqhq/copromem-appworld/venv/bin/python"
TOOL = {"type": "function", "function": {"name": "execute_python", "description": "Execute one AppWorld Python action.", "strict": True,
        "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"], "additionalProperties": False}}}
INTERFACE = ("Interface contract: use only the prebound `apis` object and API names returned by AppWorld documentation. "
             "Do not import modules, use dir/inspect/hasattr, or guess endpoint names. First read the task, then use the documented API route only as needed, then perform and verify the requested operation. Budget actions deliberately.")


def key() -> str:
    for line in Path(".env").read_text().splitlines():
        if line.startswith("DEEPSEEK_API_KEY="):
            return line.split("=", 1)[1].strip().strip("'\"")
    raise RuntimeError("DEEPSEEK_API_KEY unavailable")


def worker(task_id: str, experiment: str):
    process = subprocess.Popen(["wsl.exe", "-d", "Ubuntu", "--cd", "/home/xiqhq/copromem-appworld", "--", PYTHON, WORKER], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    def send(item: dict) -> dict:
        assert process.stdin and process.stdout
        process.stdin.write(json.dumps(item) + "\n"); process.stdin.flush()
        line = process.stdout.readline()
        if not line: raise RuntimeError("native worker ended unexpectedly")
        return json.loads(line)
    return process, send({"op": "start", "task_id": task_id, "experiment_name": experiment}), send


def request(prompt: str, ledger: CorrectedSmokeLedger, metadata: dict) -> tuple[str | None, dict]:
    attempt = str(time.time_ns()); ledger.reserve(attempt, .006, metadata)
    body = {"model": "deepseek-flash", "messages": [{"role": "system", "content": "You are an AppWorld executor. Call execute_python exactly once; no prose."}, {"role": "user", "content": prompt + "\nCall execute_python exactly once now."}], "tools": [TOOL], "tool_choice": {"type": "function", "function": {"name": "execute_python"}}, "max_tokens": 128, "stream": False, "reasoning_effort": "none"}
    started = time.perf_counter()
    try:
        raw = urllib.request.urlopen(urllib.request.Request("https://api.deepseek.com/chat/completions", data=json.dumps(body).encode(), headers={"Authorization": "Bearer " + key(), "Content-Type": "application/json"}, method="POST"), timeout=45)
        response = json.loads(raw.read())
    except urllib.error.HTTPError as error:
        if error.code in (401, 403): raise RuntimeError("direct DeepSeek authentication failed") from error
        return None, {"key": attempt, "tool_valid": False, "finish_reason": f"http_{error.code}", "tokens": {}, "latency_seconds": time.perf_counter()-started}
    usage = response.get("usage", {}); cost = (usage.get("prompt_tokens", 0)*.3 + usage.get("completion_tokens", 0)*1.2)/1e6; ledger.settle(attempt, cost)
    choice = response["choices"][0]; calls = choice["message"].get("tool_calls") or []
    reasoning = usage.get("reasoning_tokens", usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0))
    tel = {"key": attempt, "response_model": response.get("model"), "finish_reason": choice.get("finish_reason"), "tool_valid": False, "tokens": {"prompt": usage.get("prompt_tokens",0),"completion": usage.get("completion_tokens",0)}, "latency_seconds": time.perf_counter()-started,"actual_usd":cost}
    if response.get("model") != "deepseek-flash" or reasoning or len(calls) != 1: return None, tel
    try: code = json.loads(calls[0]["function"]["arguments"])["code"]
    except (KeyError, TypeError, json.JSONDecodeError): return None, tel
    tel["tool_valid"] = isinstance(code, str) and bool(code.strip())
    return (code if tel["tool_valid"] else None), tel


def trajectory(task_id: str, seed: int, ledger: CorrectedSmokeLedger) -> dict:
    process, start, send = worker(task_id, f"acquisition_readiness_seed_{seed}")
    base = "Use only execute_python for AppWorld. " + INTERFACE + "\nTask:\n" + start["instruction"] + "\nApps:\n" + json.dumps(start["app_descriptions"])
    store = RunStore(ROOT); journal = AcquisitionJournal(store, AcquisitionRef(task_id, seed, 0))
    journal.start(task_manifest_sha256=digest({"task_id":task_id,"instruction":start["instruction"]}),base_prompt_sha256=digest(base),tool_schema_sha256=digest(TOOL))
    calls=[]
    for iteration in range(10):
        code, telemetry = request(base, ledger, {"arm":"shared_acquisition_readiness","role":"executor","task_id":task_id,"phase":"acquisition","trial":0,"seed":seed,"iteration":iteration,"model":"deepseek-flash"})
        store.write("call_telemetry", telemetry["key"], {k:v for k,v in telemetry.items() if k!="key"}); calls.append(telemetry)
        if code is None: break
        journal.plan_action(iteration, code=code)
        outcome = send({"op":"action","code":code})
        journal.action(iteration, code=code, native_output=outcome, completed=bool(outcome["completed"]))
        if outcome["completed"]: break
        base += "\nPrevious native action output: " + json.dumps(outcome) + "\nContinue using only documented APIs."
    score=send({"op":"finish"}); process.wait(timeout=10); trace=journal.finish(official_score=score)
    return {"task_id":task_id,"seed":seed,"official_score":score,"trace_sha256":trace,"calls":calls}


def main() -> None:
    if (ROOT/"readiness_result.json").exists(): raise SystemExit("readiness run is terminal")
    store=RunStore(ROOT); ledger=CorrectedSmokeLedger(store,historical_roots=HISTORICAL,max_new_attempts=60,expected_historical_attempts=76,expected_historical_exposure=.07770738)
    results=[]; succeeded=set()
    for index in range(3):
        for task_id,seeds in TASKS:
            item=trajectory(task_id,seeds[index],ledger); results.append(item)
            if item["official_score"]["success"]: succeeded.add(task_id)
            if len(succeeded)>=2: break
        if len(succeeded)>=2: break
    status="go_lifecycle_validation" if len(succeeded)>=2 else "no_go_executor_acquisition_capability"
    store.write("readiness_result","final",{"status":status,"results":results,"successful_tasks":sorted(succeeded),"ledger_exposure_usd":ledger.charged_or_reserved})
    (ROOT/"readiness_result.json").write_text(json.dumps({"status":status,"successful_tasks":sorted(succeeded),"ledger_exposure_usd":ledger.charged_or_reserved},indent=2)+"\n")

if __name__=="__main__": main()
