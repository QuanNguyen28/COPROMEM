"""Manifest-pinned OpenRouter successor pilot entry point."""
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path
sys.path.insert(0, "src")
from copromem.appworld_live_smoke import LockedOpenRouterTransport, UnifiedSuccessorRunner
from copromem.checkpoints import RunStore
from copromem.corrected_smoke_ledger import CorrectedSmokeLedger
from copromem.appworld_comparison_adapter import AcquisitionIdentity, RawAcquisitionTrajectory, CoProMemAppWorldAdapter
from copromem.reme_paper_lifecycle import ReMeMemory, ReMePaperLifecycle

ROOT=Path("artifacts/research/reme_copromem_comparison/openrouter_successor_exact_id_pilot")
MANIFEST=Path("research/OPENROUTER_SUCCESSOR_EXACT_ID_MANIFEST.json")
WORKER="/mnt/e/Project/AAMAS/COPROMEM/research/containers/appworld/real_worker.py"
PYTHON="/home/xiqhq/copromem-appworld/venv/bin/python"
TOOLS={"type":"function","function":{"name":"execute_python","description":"Execute one documented AppWorld Python action.","parameters":{"type":"object","properties":{"code":{"type":"string"}},"required":["code"],"additionalProperties":False}}}
PROMPT="Use only documented prebound `apis`; do not import, reflect, or guess endpoint names. Execute and verify the task within the action budget."

def key():
    return os.environ.get("OPENROUTER_API_KEY") or next((line.split("=",1)[1].strip().strip("'\"") for line in Path(".env").read_text().splitlines() if line.startswith("OPENROUTER_API_KEY=")), "")
class Worker:
    def start(self, task, phase):
        env=f"APPWORLD_ALLOWED_TASKS={task}"; p=subprocess.Popen(["wsl.exe","-d","Ubuntu","--cd","/home/xiqhq/copromem-appworld","--","env",env,PYTHON,WORKER],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        def send(v):
            p.stdin.write(json.dumps(v)+"\n");p.stdin.flush();line=p.stdout.readline()
            if not line: raise RuntimeError("native worker ended")
            return json.loads(line)
        world=send({"op":"start","task_id":task,"experiment_name":"openrouter_successor"}); world["_send"],world["_process"]=send,p; return world
    def act(self, world, code): return world["_send"]({"op":"action","code":code})
    def finish(self, world):
        try:return world["_send"]({"op":"finish"})
        finally: world["_process"].wait(timeout=15)
def main():
    if not key(): raise RuntimeError("OPENROUTER_API_KEY unavailable")
    if __import__("shutil").disk_usage("C:\\").free < 10*1024**3: raise RuntimeError("C storage floor breached")
    manifest=json.loads(MANIFEST.read_text())
    store=RunStore(ROOT)
    ledger=CorrectedSmokeLedger(store,historical_roots=[Path("artifacts/research/reme_copromem_comparison/openrouter_deepseek_successor_canary"),Path("artifacts/research/reme_copromem_comparison/openrouter_deepseek_successor_canary_corrected")],max_new_attempts=9440,expected_historical_attempts=2,expected_historical_exposure=.0100651,max_usd=35)
    transport=LockedOpenRouterTransport(api_key=key(),ledger=ledger)
    worker=Worker(); runner=UnifiedSuccessorRunner(store=store,transport=transport,start_world=worker.start,act=worker.act,finish=worker.finish,tools=TOOLS,base_system_prompt=PROMPT)
    def lifecycle(acquisition, locked_transport):
        raw=[]
        for row in acquisition:
            ref=f"{row['task_id']}--seed-{row['seed']}--trajectory-{manifest['acquisition']['seeds'].index(row['seed'])}"
            ctx=store.read("trajectory_context", ref+"--acquisition--shared") or {}
            actions=[store.read("acquisition_actions", p.stem)["code"] for p in sorted((ROOT/"acquisition_actions").glob(ref+"--*.json"))]
            raw.append(RawAcquisitionTrajectory(AcquisitionIdentity(row["task_id"],row["seed"],manifest["acquisition"]["seeds"].index(row["seed"])),ctx.get("instruction",row["task_id"]),"appworld",bool(row["official_score"]["success"]),tuple(actions)))
        successful=[item for item in raw if item.success]
        fixed=ReMePaperLifecycle([ReMeMemory("reme-fixed::"+item.identity.value) for item in successful],dynamic=False)
        dynamic=ReMePaperLifecycle([ReMeMemory("reme-dynamic::"+item.identity.value) for item in successful],dynamic=True)
        serial=[0]
        decomp_tool={"type":"function","function":{"name":"return_decomposition_json","description":"Return decomposition JSON.","parameters":{"type":"object","properties":{"result":{"type":"object"}},"required":["result"],"additionalProperties":False}}}
        def decompose_call(*,system_prompt,user_prompt,max_tokens,schema_name=None):
            serial[0]+=1; key=f"copromem-decomposition-{serial[0]}"
            result=locked_transport.dispatch(key=key,metadata={"role":"copromem_decomposition","phase":"lifecycle","arm":"copromem_v2","iteration":serial[0],"model":"deepseek/deepseek-v4.1-flash"},prompt=system_prompt+"\n"+user_prompt,tools=decomp_tool,upper_usd=.003072)
            return result.output["result"]
        copro=CoProMemAppWorldAdapter(api_key=key(),model="deepseek/deepseek-v4.1-flash",provider_only="deepseek",reasoning_effort="none",llm_json_call=decompose_call,decomposition_call_cap=320)
        for item in raw: copro.ingest(item)
        copro.consolidate()
        def text(state): return json.dumps(state,sort_keys=True)
        return {"reme_fixed":text({"provenance":"reme-faithful-adapter-fixed","memories":[vars(x) for x in fixed.acquired.memories.values()]}),"reme_dynamic":text({"provenance":"reme-faithful-adapter-dynamic","memories":[vars(x) for x in dynamic.acquired.memories.values()]}),"copromem_v2":text({"provenance":"copromem-v2","state":copro.export_state()})}
    result=runner.run_manifest(manifest, lifecycle)
    print(json.dumps({"status":result["status"],"ledger_exposure_usd":ledger.charged_or_reserved}))
if __name__=="__main__":main()
