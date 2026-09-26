"""Versioned JSON-lifecycle successor to the stopped exploratory pilot."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, "src")
from copromem.appworld_comparison_adapter import AcquisitionIdentity, CoProMemAppWorldAdapter, RawAcquisitionTrajectory, TrialInput
from copromem.appworld_live_smoke import ARMS, LOCKED_MODEL, UnifiedSuccessorRunner
from copromem.checkpoints import RunStore, digest
from copromem.exploratory_successor_ledger import ExploratorySuccessorLedger
from copromem.locked_lifecycle_json import LockedLifecycleJsonTransport
from copromem.reme_paper_lifecycle import ReMePaperLifecycle


SOURCE_ROOT = Path("artifacts/research/reme_copromem_comparison/openrouter_successor_exact_id_pilot")
FAILED_ROOT = Path("artifacts/research/reme_copromem_comparison/openrouter_failure_informed_exploratory_pilot")
ROOT = Path("artifacts/research/reme_copromem_comparison/openrouter_failure_informed_json_lifecycle_successor")
SOURCE_MANIFEST = Path("research/OPENROUTER_SUCCESSOR_EXACT_ID_MANIFEST.json")
WORKER = "/mnt/e/Project/AAMAS/COPROMEM/research/containers/appworld/real_worker.py"
PYTHON = "/home/xiqhq/copromem-appworld/venv/bin/python"
PROMPT = "Use only documented prebound `apis`; do not import, reflect, or guess endpoint names. Execute and verify the task within the action budget."
TOOLS = {"type": "function", "function": {"name": "execute_python", "description": "Execute one documented AppWorld Python action.", "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"], "additionalProperties": False}}}
JSON_SUFFIX = {
    "copromem_complexity_v1": "\nReturn the entire assistant response as exactly one JSON object with exactly keys `is_compound` (boolean) and `rationale` (string). No Markdown, commentary, or extra keys.",
    "copromem_subgoals_v1": "\nReturn the entire assistant response as exactly one JSON object with exactly key `subgoals`, a list of 2 or 3 objects. Each object has exactly `description` (nonempty string) and `is_atomic` (boolean). No Markdown, commentary, or extra keys.",
    "reme_failure_reflection_v1": "\nReturn the entire assistant response as exactly one JSON object with exactly keys `failure_evidence_ids` (list of nonempty strings) and `memory_text` (string). No Markdown, commentary, or extra keys.",
}
HISTORICAL_ROOTS = [
    Path("artifacts/research/reme_copromem_comparison/acquisition_readiness"),
    Path("artifacts/research/reme_copromem_comparison/corrected_direct_deepseek_smoke"),
    Path("artifacts/research/reme_copromem_comparison/direct_deepseek_successor_smoke"),
    Path("artifacts/research/reme_copromem_comparison/diverse_acquisition"),
    Path("artifacts/research/reme_copromem_comparison/final_acquisition_readiness"),
    Path("artifacts/research/reme_copromem_comparison/openrouter_brokered_smoke"),
    Path("artifacts/research/reme_copromem_comparison/openrouter_deepseek_successor_canary"),
    Path("artifacts/research/reme_copromem_comparison/openrouter_deepseek_successor_canary_corrected"),
    SOURCE_ROOT, FAILED_ROOT,
]
HISTORICAL_ATTEMPTS = 1104
HISTORICAL_EXPOSURE = 0.777939615
EVALUATION_CALLS, DECOMPOSITION_CALLS, PER_CALL_USD = 7200, 320, 0.003072
CANARY_RESERVE = 0.01
NEW_RESERVED_USD = EVALUATION_CALLS * PER_CALL_USD + DECOMPOSITION_CALLS * PER_CALL_USD + CANARY_RESERVE
CONTINGENCY_USD = NEW_RESERVED_USD * .15


def api_key() -> str:
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    dotenv = Path(".env")
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return ""


class Worker:
    def start(self, task: str, phase: str) -> Mapping[str, Any]:
        process = subprocess.Popen(["wsl.exe", "-d", "Ubuntu", "--cd", "/home/xiqhq/copromem-appworld", "--", "env", f"APPWORLD_ALLOWED_TASKS={task}", PYTHON, WORKER], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        def send(value: Mapping[str, Any]) -> Mapping[str, Any]:
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write(json.dumps(value) + "\n"); process.stdin.flush()
            line = process.stdout.readline()
            if not line: raise RuntimeError("native AppWorld worker ended")
            return json.loads(line)
        world = dict(send({"op":"start", "task_id":task, "experiment_name":"failure_informed_json_successor"}))
        world["_send"], world["_process"] = send, process
        return world
    def act(self, world: Mapping[str, Any], code: str) -> Mapping[str, Any]: return world["_send"]({"op":"action", "code":code})
    def finish(self, world: Mapping[str, Any]) -> Mapping[str, Any]:
        try: return world["_send"]({"op":"finish"})
        finally: world["_process"].wait(timeout=15)


def source_pool() -> list[dict[str, Any]]:
    rows=[]
    for path in sorted((SOURCE_ROOT / "acquisition_scores").glob("*.json")):
        item=json.loads(path.read_text(encoding="utf-8")); parts=path.stem.split("--seed-")
        task_id=parts[0]; seed=int(parts[1].split("--", 1)[0])
        rows.append({"task_id":task_id,"seed":seed,"official_success":bool(item["official_score"]["success"]),"score_artifact_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"trace_sha256":item.get("trace_sha256","")})
    if len(rows)!=48 or any(row["official_success"] for row in rows): raise RuntimeError("unchanged observed 0/48 source pool required")
    return rows


def freeze(store: RunStore) -> dict[str, Any]:
    source=json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8")); pool=source_pool()
    manifest={
        "version":"failure-informed-json-lifecycle-successor-v1", "status":"frozen_before_lifecycle_canary",
        "interpretation":"Created after confirmatory 0/48 acquisition NO-GO and a stopped native-tool lifecycle attempt. Exploratory, failure-informed, exact-task-ID-held-out only; no confirmatory efficacy, superiority, task-family, or benchmark-wide generalization claim.",
        "source_confirmatory_manifest_sha256":hashlib.sha256(SOURCE_MANIFEST.read_bytes()).hexdigest(),
        "source_failed_lifecycle_terminal_sha256":hashlib.sha256((FAILED_ROOT/"pilot_terminal"/"locked_route_failure.json").read_bytes()).hexdigest(),
        "source_pool":pool, "source_acquisition_seeds":source["acquisition"]["seeds"],
        "evaluation":{"task_ids":source["evaluation"]["task_ids"],"seeds":source["evaluation"]["seeds"],"exact_id_holdout_only":True}, "arms":list(ARMS),"max_actions":30,"max_completion_tokens":1024,
        "executor_route":{"native_tools":True,"tool_choice":"auto","parallel_tools":"one declared tool plus exactly-one-call gate"},
        "lifecycle_route":{"native_tools":False,"tool_choice":None,"whole_response_json":True,"schemas":JSON_SUFFIX,"parser_source_sha256":hashlib.sha256(Path("src/copromem/locked_lifecycle_json.py").read_bytes()).hexdigest(),"decomposer_source_sha256":hashlib.sha256(Path("src/copromem/decomposition.py").read_bytes()).hexdigest()},
        "route":{"endpoint":"https://openrouter.ai/api/v1/chat/completions","model":LOCKED_MODEL,"provider_only":["deepseek"],"allow_fallbacks":False,"reasoning_effort":"none","stream":False},
        "parity":{"prompt_sha256":digest(PROMPT),"tool_schema_sha256":digest(TOOLS),"memory_is_only_arm_specific_executor_input":True,"official_scorer":"native AppWorld worker"},
        "analysis":{"unit":"task x seed paired arm outcome","estimands":["paired success-rate differences versus No Memory","task-clustered bootstrap confidence intervals"],"not_confirmatory":True},
        "budget":{"historical_records":1104,"historical_exposure_usd":0.777939615,"canary_reserved_usd":0.01,"evaluation_calls":7200,"copromem_decomposition_calls":320,"reme_lifecycle_calls":0,"new_reserved_usd":23.11144,"non_dispatchable_contingency_usd":3.466716,"all_in_usd":27.356095615,"absolute_cap_usd":35.0},
    }
    store.write("manifest","failure_informed_json_lifecycle_successor_v1",manifest); return manifest


class JsonLifecycle:
    def __init__(self, store: RunStore, transport: LockedLifecycleJsonTransport, manifest: Mapping[str, Any]) -> None:
        self.store,self.transport,self.manifest=store,transport,manifest; self.serial=0
        self.copro=CoProMemAppWorldAdapter(api_key=api_key(),model=LOCKED_MODEL,provider_only="deepseek",reasoning_effort="none",llm_json_call=self._call,decomposition_call_cap=DECOMPOSITION_CALLS)
        self.fixed=ReMePaperLifecycle([],dynamic=False); self.dynamic=ReMePaperLifecycle([],dynamic=True)

    def _call(self, *, system_prompt: str, user_prompt: str, max_tokens: int, schema_name: str | None = None) -> dict[str, Any]:
        if schema_name not in JSON_SUFFIX: raise RuntimeError("unfrozen lifecycle schema")
        self.serial += 1
        result=self.transport.dispatch(key=f"lifecycle-json--copromem--{self.serial}",metadata={"phase":"lifecycle","role":"copromem_decomposition_json","arm":"copromem_v2","iteration":self.serial,"model":LOCKED_MODEL},system_prompt=system_prompt+JSON_SUFFIX[schema_name],user_prompt=user_prompt,schema_name=schema_name,upper_usd=PER_CALL_USD)
        return dict(result.output)

    def _raw(self) -> list[RawAcquisitionTrajectory]:
        output=[]; source_store=RunStore(SOURCE_ROOT)
        for row in self.manifest["source_pool"]:
            index=self.manifest["source_acquisition_seeds"].index(row["seed"]); ref=f"{row['task_id']}--seed-{row['seed']}--trajectory-{index}"
            context=source_store.read("trajectory_context",ref+"--acquisition--shared") or {}
            actions=tuple((json.loads(p.read_text(encoding="utf-8"))).get("code","") for p in sorted((SOURCE_ROOT/"acquisition_actions").glob(ref+"--*.json")))
            output.append(RawAcquisitionTrajectory(AcquisitionIdentity(row["task_id"],row["seed"],index),str(context.get("instruction",row["task_id"])),"appworld",False,actions,{"source_trace_sha256":row["trace_sha256"],"source_score_artifact_sha256":row["score_artifact_sha256"]}))
        return output

    def construct(self) -> Mapping[str,str]:
        existing=[self.store.read("lifecycle_outputs",arm) for arm in ("reme_fixed","reme_dynamic","copromem_v2")]
        if all(existing):
            self.copro.load_state(existing[2]["payload"]["state"]); return {"reme_fixed":"","reme_dynamic":"","copromem_v2":""}
        progress=sorted((self.store.root/"lifecycle_progress").glob("*.json")); start=0
        if progress:
            latest=json.loads(progress[-1].read_text(encoding="utf-8"));self.copro.load_state(latest["state"]);start=int(latest["index"])+1;self.serial=int(latest["calls"])
        raw=self._raw()
        for index,trajectory in enumerate(raw[start:],start=start):
            self.copro.ingest(trajectory)
            self.store.write("lifecycle_progress",f"{index:03d}",{"index":index,"identity":trajectory.identity.value,"calls":self.serial,"state":self.copro.export_state()})
        self.copro.consolidate()
        pool_hash=digest(self.manifest["source_pool"])
        payloads={"reme_fixed":{"method":"reme_fixed_faithful_adaptation","source_pool_sha256":pool_hash,"failure_source_episodes":48,"memory_text":"","memory_ids":[]},"reme_dynamic":{"method":"reme_dynamic_faithful_adaptation","source_pool_sha256":pool_hash,"failure_source_episodes":48,"memory_text":"","memory_ids":[]},"copromem_v2":{"method":"copromem_v2_json_lifecycle_adaptation","source_pool_sha256":pool_hash,"failure_source_episodes":48,"state":self.copro.export_state()}}
        for arm,payload in payloads.items(): self.store.write("lifecycle_outputs",arm,{"sha256":digest(payload),"payload":payload})
        return {"reme_fixed":"","reme_dynamic":"","copromem_v2":""}

    def memory_for(self, *, task_id: str, seed: int, arm: str, fallback: str) -> str:
        key=f"{task_id}--seed-{seed}--{arm}"; prior=self.store.read("memory_inputs",key)
        if prior is not None:return str(prior["memory_text"])
        if arm=="copromem_v2":
            index=self.manifest["evaluation"]["task_ids"].index(task_id)*len(self.manifest["evaluation"]["seeds"])+self.manifest["evaluation"]["seeds"].index(seed)
            memory=self.copro.prepare_trial(TrialInput(task_id,task_id,"appworld",base_prompt=PROMPT,tool_spec=TOOLS),index)
        else: memory=""
        self.store.write("memory_inputs",key,{"task_id":task_id,"seed":seed,"arm":arm,"memory_text":memory,"memory_sha256":digest(memory),"empty":not bool(memory.strip()),"source_pool_sha256":digest(self.manifest["source_pool"])})
        return memory

    def after_trial(self, *, task_id: str, seed: int, arm: str, result: Mapping[str,Any]) -> None:
        if arm!="reme_dynamic":return
        stream=self.manifest["evaluation"]["seeds"].index(seed);state=self.dynamic.state_for_trial_stream(stream);retrieved=list(state.memories)
        self.dynamic.after_evaluation(stream=stream,retrieved_ids=retrieved,success=bool((result.get("official_score") or {}).get("success")),validated_addition=None)
        self.store.write("dynamic_updates",f"{task_id}--seed-{seed}",{"task_id":task_id,"seed":seed,"retrieved_ids":retrieved,"official_success":bool((result.get("official_score") or {}).get("success")),"state_sha256":digest({key:vars(value) for key,value in self.dynamic.state_for_trial_stream(stream).memories.items()})})


def ledger(store: RunStore) -> ExploratorySuccessorLedger:
    return ExploratorySuccessorLedger(store,historical_roots=HISTORICAL_ROOTS,expected_historical_attempts=HISTORICAL_ATTEMPTS,expected_historical_exposure=HISTORICAL_EXPOSURE,max_new_attempts=EVALUATION_CALLS+DECOMPOSITION_CALLS+1,max_new_reserved_usd=NEW_RESERVED_USD,max_usd=35.0)


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--freeze-only",action="store_true");parser.add_argument("--canary",action="store_true");args=parser.parse_args()
    store=RunStore(ROOT);manifest=freeze(store)
    if args.freeze_only: print(json.dumps({"status":"frozen","manifest_sha256":digest(manifest)}));return
    if not api_key():raise RuntimeError("OPENROUTER_API_KEY unavailable")
    if shutil.disk_usage("C:\\").free<10*1024**3:raise RuntimeError("C storage floor breached")
    budget=ledger(store); transport=LockedLifecycleJsonTransport(api_key=api_key(),ledger=budget)
    if args.canary:
        if store.read("reservations","lifecycle-json-canary") is not None: raise RuntimeError("canary already attempted; no retry permitted")
        outcome=transport.dispatch(key="lifecycle-json-canary",metadata={"phase":"canary","role":"lifecycle_json_canary","model":LOCKED_MODEL},system_prompt="You are validating a strict lifecycle JSON response contract."+JSON_SUFFIX["copromem_complexity_v1"],user_prompt="Classify this generic lifecycle intent as atomic or compound: read one documented value.",schema_name="copromem_complexity_v1",upper_usd=CANARY_RESERVE)
        print(json.dumps({"status":"canary_passed","actual_usd":outcome.actual_usd}));return
    canary=store.read("locked_lifecycle_json","lifecycle-json-canary")
    if canary is None or not all(canary["validation"].values()):raise RuntimeError("passing lifecycle JSON canary required")
    lifecycle=JsonLifecycle(store,transport,manifest); memories=lifecycle.construct(); runner=UnifiedSuccessorRunner(store=store,transport=None,start_world=Worker().start,act=Worker().act,finish=Worker().finish,tools=TOOLS,base_system_prompt=PROMPT)
    # Executors remain native-tool calls.  Supply the original locked executor
    # transport only after lifecycle JSON construction; this import boundary
    # keeps lifecycle requests tool-free.
    from copromem.appworld_live_smoke import LockedOpenRouterTransport
    runner.transport=LockedOpenRouterTransport(api_key=api_key(),ledger=budget)
    evaluation=runner.run_evaluation(manifest,memories,lifecycle)
    store.write("pilot_terminal","complete",{"status":"exploratory_complete","evaluation_count":len(evaluation),"ledger_charged_or_reserved_usd":budget.charged_or_reserved})
    print(json.dumps({"status":"exploratory_complete","evaluation_count":len(evaluation),"ledger_charged_or_reserved_usd":budget.charged_or_reserved}))

if __name__=="__main__":main()
