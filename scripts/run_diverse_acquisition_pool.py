"""Frozen 12-task acquisition pool. This program has no evaluation path."""
from __future__ import annotations
import json, shutil, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path
sys.path.insert(0,"src")
from copromem.appworld_acquisition_gate import AcquisitionJournal, AcquisitionRef
from copromem.appworld_comparison_adapter import AcquisitionIdentity, CoProMemAppWorldAdapter, RawAcquisitionTrajectory
from copromem.checkpoints import RunStore, digest
from copromem.corrected_smoke_ledger import CorrectedSmokeLedger
from copromem.reme_paper_lifecycle import ReMeMemory, ReMePaperLifecycle
from copromem.tool_transport_guard import bounded_native_feedback

ROOT=Path("artifacts/research/reme_copromem_comparison/diverse_acquisition")
HIST=[Path("artifacts/research/reme_copromem_comparison/openrouter_brokered_smoke"),Path("artifacts/research/reme_copromem_comparison/direct_deepseek_successor_smoke"),Path("artifacts/research/reme_copromem_comparison/corrected_direct_deepseek_smoke"),Path("artifacts/research/reme_copromem_comparison/acquisition_readiness"),Path("artifacts/research/reme_copromem_comparison/final_acquisition_readiness")]
TASKS=("530b157_1","4ec8de5_1","b119b1f_1","d4e9306_1","0d8a4ee_1","37a8675_1","3ab5b8b_1","df61dc5_1","383cbac_1","23cf851_1","57c3486_1","68ee2c9_1")
WORKER="/mnt/e/Project/AAMAS/COPROMEM/research/containers/appworld/real_worker.py"; PYTHON="/home/xiqhq/copromem-appworld/venv/bin/python"; SEED=701
TOOL={"type":"function","function":{"name":"execute_python","description":"Execute one AppWorld Python action.","strict":True,"parameters":{"type":"object","properties":{"code":{"type":"string"}},"required":["code"],"additionalProperties":False}}}
INTERFACE="Use only prebound documented `apis`; do not import, reflect, or guess endpoint names. Read the task, consult documentation only when needed, execute and verify within the action budget."
def key():
 for line in Path(".env").read_text().splitlines():
  if line.startswith("DEEPSEEK_API_KEY="):return line.split("=",1)[1].strip().strip("'\"")
 raise RuntimeError("DEEPSEEK_API_KEY unavailable")
def worker(task):
 p=subprocess.Popen(["wsl.exe","-d","Ubuntu","--cd","/home/xiqhq/copromem-appworld","--","env",f"APPWORLD_ALLOWED_TASKS={task}",PYTHON,WORKER],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
 def send(v):
  assert p.stdin and p.stdout;p.stdin.write(json.dumps(v)+"\n");p.stdin.flush();line=p.stdout.readline()
  if not line:raise RuntimeError("native worker ended unexpectedly")
  return json.loads(line)
 return p,send({"op":"start","task_id":task,"experiment_name":"diverse_acquisition"}),send
def call(prompt,ledger,meta):
 attempt=str(time.time_ns());ledger.reserve(attempt,.02,meta);start=time.perf_counter();body={"model":"deepseek-flash","messages":[{"role":"system","content":"You are an AppWorld executor. Call execute_python exactly once; no prose."},{"role":"user","content":prompt+"\nCall execute_python exactly once now."}],"tools":[TOOL],"tool_choice":{"type":"function","function":{"name":"execute_python"}},"max_tokens":1024,"stream":False,"reasoning_effort":"none"}
 try:raw=urllib.request.urlopen(urllib.request.Request("https://api.deepseek.com/chat/completions",data=json.dumps(body).encode(),headers={"Authorization":"Bearer "+key(),"Content-Type":"application/json"},method="POST"),timeout=45);rsp=json.loads(raw.read())
 except urllib.error.HTTPError as err:
  if err.code in (401,403):raise RuntimeError("direct DeepSeek authentication failed") from err
  return None,{"key":attempt,"tool_valid":False,"finish_reason":f"http_{err.code}","tokens":{},"latency_seconds":time.perf_counter()-start}
 usage=rsp.get("usage",{});cost=(usage.get("prompt_tokens",0)*.3+usage.get("completion_tokens",0)*1.2)/1e6;ledger.settle(attempt,cost);choice=rsp["choices"][0];tcs=choice["message"].get("tool_calls") or [];reasoning=usage.get("reasoning_tokens",usage.get("completion_tokens_details",{}).get("reasoning_tokens",0));tel={"key":attempt,"response_model":rsp.get("model"),"finish_reason":choice.get("finish_reason"),"tool_valid":False,"tokens":{"prompt":usage.get("prompt_tokens",0),"completion":usage.get("completion_tokens",0)},"latency_seconds":time.perf_counter()-start,"actual_usd":cost}
 if rsp.get("model")!="deepseek-flash" or reasoning or len(tcs)!=1:return None,tel
 try:code=json.loads(tcs[0]["function"]["arguments"])["code"]
 except (KeyError,TypeError,json.JSONDecodeError):return None,tel
 tel["tool_valid"]=isinstance(code,str) and bool(code.strip());return (code if tel["tool_valid"] else None),tel
def trajectory(task,ledger):
 p,start,send=worker(task);base="Use only execute_python for AppWorld. "+INTERFACE+"\nTask:\n"+start["instruction"]+"\nApps:\n"+json.dumps(start["app_descriptions"]);store=RunStore(ROOT);j=AcquisitionJournal(store,AcquisitionRef(task,SEED,0));j.start(task_manifest_sha256=digest({"task_id":task,"instruction":start["instruction"]}),base_prompt_sha256=digest(base),tool_schema_sha256=digest(TOOL));calls=[];actions=[]
 for i in range(30):
  code,tel=call(base,ledger,{"arm":"diverse_shared_acquisition","role":"executor","task_id":task,"phase":"acquisition","trial":0,"seed":SEED,"iteration":i,"model":"deepseek-flash"});store.write("call_telemetry",tel["key"],{k:v for k,v in tel.items() if k!="key"});calls.append(tel)
  if code is None:break
  j.plan_action(i,code=code);out=send({"op":"action","code":code});actions.append(code);j.action(i,code=code,native_output=out,completed=bool(out["completed"]))
  if out["completed"]:break
  base+="\nPrevious native action output: "+bounded_native_feedback(out)+"\nContinue using only documented APIs."
 score=send({"op":"finish"});p.wait(timeout=10);return {"task_id":task,"seed":SEED,"official_score":score,"trace_sha256":j.finish(official_score=score),"actions":actions,"calls":calls,"instruction":start["instruction"]}
def lifecycle(pool):
 store=RunStore(ROOT);raw=[RawAcquisitionTrajectory(AcquisitionIdentity(x["task_id"],SEED,0),x["instruction"],"appworld",bool(x["official_score"]["success"]),tuple(x["actions"])) for x in pool];successful=[x for x in raw if x.success]
 fixed=ReMePaperLifecycle([ReMeMemory("reme-fixed::"+x.identity.value) for x in successful],dynamic=False);dynamic=ReMePaperLifecycle([ReMeMemory("reme-dynamic::"+x.identity.value) for x in successful],dynamic=True);copro=CoProMemAppWorldAdapter(api_key="",decomposition_call_cap=0)
 for item in raw:copro.ingest(item)
 copro.consolidate();outputs={"reme_fixed_faithful_adaptation":{"provenance":"reme-faithful-adapter-fixed","memory_sha256":digest(list(fixed.acquired.memories)),"empty":not bool(fixed.acquired.memories)},"reme_dynamic_faithful_adaptation":{"provenance":"reme-faithful-adapter-dynamic","memory_sha256":digest(list(dynamic.state_for_trial_stream(0).memories)),"empty":not bool(dynamic.state_for_trial_stream(0).memories)},"copromem_v2":{"provenance":"copromem-v2","memory_sha256":digest(copro.export_state()),"empty":not bool(successful)}};store.write("lifecycle","pool",{"outputs":outputs,"source_trace_hashes":[x["trace_sha256"] for x in pool]});return outputs
def disk_guard():
 if shutil.disk_usage("C:\\").free < 10*1024**3: raise RuntimeError("C free space is below the 10 GiB trajectory guard")
def saved(task,store):
 key=f"{task}--seed-{SEED}--trajectory-0"; score=store.read("acquisition_scores",key)
 if score is None:return None
 actions=[store.read("acquisition_actions",p.stem)["code"] for p in sorted((ROOT/"acquisition_actions").glob(f"{key}--*.json"))]
 return {"task_id":task,"seed":SEED,"official_score":score["official_score"],"trace_sha256":score["raw_trajectory_sha256"],"actions":actions,"instruction":"AppWorld acquisition","calls":[],"resumed":True}
def recover(task,store):
 key=f"{task}--seed-{SEED}--trajectory-0"; actions=[store.read("acquisition_actions",p.stem)["code"] for p in sorted((ROOT/"acquisition_actions").glob(f"{key}--*.json"))]
 if not actions:return None
 disk_guard();p,start,send=worker(task)
 for code in actions: send({"op":"action","code":code})
 score=send({"op":"finish"});p.wait(timeout=10);journal=AcquisitionJournal(store,AcquisitionRef(task,SEED,0));trace=journal.finish(official_score=score);store.write("recovery",key,{"replayed_native_actions":len(actions),"model_calls":0,"retained_unsettled_request":True,"trace_sha256":trace})
 return saved(task,store)
def main():
 if (ROOT/"diverse_result.json").exists():raise SystemExit("diverse acquisition is terminal")
 store=RunStore(ROOT);ledger=CorrectedSmokeLedger(store,historical_roots=HIST,max_new_attempts=360,expected_historical_attempts=123,expected_historical_exposure=.13762998,max_usd=8);pool=[]
 for task in TASKS:
  item=saved(task,store)
  if item is None and store.read("acquisition_start",f"{task}--seed-{SEED}--trajectory-0") is not None:item=recover(task,store)
  if item is None:
   disk_guard();item=trajectory(task,ledger);disk_guard()
  pool.append(item)
 outputs=lifecycle(pool);successes=[x for x in pool if x["official_score"]["success"]];families={x["task_id"].split("_")[0] for x in successes};signal=len(successes)>=3 and len(families)>=3;status="go_separate_corrected_evaluation_smoke" if signal else "no_go_insufficient_diverse_acquisition_signal";store.write("diverse_result","final",{"status":status,"pool":pool,"lifecycle_outputs":outputs,"success_count":len(successes),"success_families":sorted(families),"ledger_exposure_usd":ledger.charged_or_reserved});(ROOT/"diverse_result.json").write_text(json.dumps({"status":status,"success_count":len(successes),"success_families":sorted(families),"ledger_exposure_usd":ledger.charged_or_reserved},indent=2)+"\n")
if __name__=="__main__":main()
