"""Final 30-action acquisition-only readiness run; evaluation is impossible here."""
from __future__ import annotations
import json, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path
sys.path.insert(0, "src")
from copromem.appworld_acquisition_gate import AcquisitionJournal, AcquisitionRef
from copromem.checkpoints import RunStore, digest
from copromem.corrected_smoke_ledger import CorrectedSmokeLedger
from copromem.tool_transport_guard import bounded_native_feedback
from copromem.appworld_comparison_adapter import AcquisitionIdentity, CoProMemAppWorldAdapter, RawAcquisitionTrajectory
from copromem.reme_paper_lifecycle import ReMeMemory, ReMePaperLifecycle

ROOT=Path("artifacts/research/reme_copromem_comparison/final_acquisition_readiness")
HIST=[Path("artifacts/research/reme_copromem_comparison/openrouter_brokered_smoke"),Path("artifacts/research/reme_copromem_comparison/direct_deepseek_successor_smoke"),Path("artifacts/research/reme_copromem_comparison/corrected_direct_deepseek_smoke"),Path("artifacts/research/reme_copromem_comparison/acquisition_readiness")]
TASKS=(("50e1ac9_1",404),("50e1ac9_2",404))
WORKER="/mnt/e/Project/AAMAS/COPROMEM/research/containers/appworld/real_worker.py"; PYTHON="/home/xiqhq/copromem-appworld/venv/bin/python"
TOOL={"type":"function","function":{"name":"execute_python","description":"Execute one AppWorld Python action.","strict":True,"parameters":{"type":"object","properties":{"code":{"type":"string"}},"required":["code"],"additionalProperties":False}}}
INTERFACE="Use only prebound documented `apis`; do not import, reflect, or guess endpoint names. Read the task, consult documentation only when needed, execute and verify within the action budget."

def key():
 for line in Path(".env").read_text().splitlines():
  if line.startswith("DEEPSEEK_API_KEY="): return line.split("=",1)[1].strip().strip("'\"")
 raise RuntimeError("DEEPSEEK_API_KEY unavailable")
def worker(task, name):
 p=subprocess.Popen(["wsl.exe","-d","Ubuntu","--cd","/home/xiqhq/copromem-appworld","--",PYTHON,WORKER],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
 def send(v):
  assert p.stdin and p.stdout;p.stdin.write(json.dumps(v)+"\n");p.stdin.flush();line=p.stdout.readline()
  if not line: raise RuntimeError("native worker ended unexpectedly")
  return json.loads(line)
 return p,send({"op":"start","task_id":task,"experiment_name":name}),send
def call(prompt, ledger, meta):
 attempt=str(time.time_ns());ledger.reserve(attempt,.01,meta); started=time.perf_counter()
 body={"model":"deepseek-flash","messages":[{"role":"system","content":"You are an AppWorld executor. Call execute_python exactly once; no prose."},{"role":"user","content":prompt+"\nCall execute_python exactly once now."}],"tools":[TOOL],"tool_choice":{"type":"function","function":{"name":"execute_python"}},"max_tokens":256,"stream":False,"reasoning_effort":"none"}
 try:
  raw=urllib.request.urlopen(urllib.request.Request("https://api.deepseek.com/chat/completions",data=json.dumps(body).encode(),headers={"Authorization":"Bearer "+key(),"Content-Type":"application/json"},method="POST"),timeout=45); response=json.loads(raw.read())
 except urllib.error.HTTPError as err:
  if err.code in (401,403): raise RuntimeError("direct DeepSeek authentication failed") from err
  return None,{"key":attempt,"tool_valid":False,"finish_reason":f"http_{err.code}","tokens":{},"latency_seconds":time.perf_counter()-started}
 usage=response.get("usage",{}); cost=(usage.get("prompt_tokens",0)*.3+usage.get("completion_tokens",0)*1.2)/1e6; ledger.settle(attempt,cost)
 choice=response["choices"][0]; tcs=choice["message"].get("tool_calls") or []; reasoning=usage.get("reasoning_tokens",usage.get("completion_tokens_details",{}).get("reasoning_tokens",0))
 tele={"key":attempt,"response_model":response.get("model"),"finish_reason":choice.get("finish_reason"),"tool_valid":False,"tokens":{"prompt":usage.get("prompt_tokens",0),"completion":usage.get("completion_tokens",0)},"latency_seconds":time.perf_counter()-started,"actual_usd":cost}
 if response.get("model")!="deepseek-flash" or reasoning or len(tcs)!=1:return None,tele
 try: code=json.loads(tcs[0]["function"]["arguments"])["code"]
 except (KeyError,TypeError,json.JSONDecodeError):return None,tele
 tele["tool_valid"]=isinstance(code,str) and bool(code.strip());return (code if tele["tool_valid"] else None),tele
def trajectory(task,seed,ledger):
 p,start,send=worker(task,f"final_acquisition_seed_{seed}"); base="Use only execute_python for AppWorld. "+INTERFACE+"\nTask:\n"+start["instruction"]+"\nApps:\n"+json.dumps(start["app_descriptions"]); store=RunStore(ROOT); j=AcquisitionJournal(store,AcquisitionRef(task,seed,0));j.start(task_manifest_sha256=digest({"task_id":task,"instruction":start["instruction"]}),base_prompt_sha256=digest(base),tool_schema_sha256=digest(TOOL));calls=[]
 for i in range(30):
  code,tel=call(base,ledger,{"arm":"final_acquisition_readiness","role":"executor","task_id":task,"phase":"acquisition","trial":0,"seed":seed,"iteration":i,"model":"deepseek-flash"});store.write("call_telemetry",tel["key"],{k:v for k,v in tel.items() if k!="key"});calls.append(tel)
  if code is None:break
  j.plan_action(i,code=code);out=send({"op":"action","code":code});j.action(i,code=code,native_output=out,completed=bool(out["completed"]))
  if out["completed"]:break
  base+="\nPrevious native action output: "+bounded_native_feedback(out)+"\nContinue using only documented APIs."
 score=send({"op":"finish"});p.wait(timeout=10);return {"task_id":task,"seed":seed,"official_score":score,"trace_sha256":j.finish(official_score=score),"calls":calls}
def lifecycle(results):
 store=RunStore(ROOT); valid=[x for x in results if x["official_score"]["success"]]
 raw=[RawAcquisitionTrajectory(AcquisitionIdentity(x["task_id"],x["seed"],0),"AppWorld acquisition","appworld",True,()) for x in valid]
 fixed=ReMePaperLifecycle([ReMeMemory("reme-fixed::"+x["trace_sha256"]) for x in valid],dynamic=False)
 dynamic=ReMePaperLifecycle([ReMeMemory("reme-dynamic::"+x["trace_sha256"]) for x in valid],dynamic=True)
 copro=CoProMemAppWorldAdapter(api_key="",decomposition_call_cap=0)
 for item in raw:copro.ingest(item)
 copro.consolidate()
 texts={"reme_fixed_faithful_adaptation":("ReMe fixed lifecycle state: "+",".join(fixed.acquired.memories),"reme-faithful-adapter-fixed"),"reme_dynamic_faithful_adaptation":("ReMe dynamic lifecycle state: "+",".join(dynamic.state_for_trial_stream(0).memories),"reme-faithful-adapter-dynamic"),"copromem_v2":("CoProMem v2 lifecycle state: "+digest(copro.export_state()),"copromem-v2")}
 for item in valid:
  j=AcquisitionJournal(store,AcquisitionRef(item["task_id"],item["seed"],0))
  for method,(text,provenance) in texts.items():j.admit_memory(method=method,provenance=provenance,memory_text=text)
  j.approve_evaluation()
 return {k:{"provenance":v[1],"sha256":digest(v[0])} for k,v in texts.items()}
def main():
 if (ROOT/"final_result.json").exists():raise SystemExit("final readiness run is terminal")
 store=RunStore(ROOT);ledger=CorrectedSmokeLedger(store,historical_roots=HIST,max_new_attempts=60,expected_historical_attempts=102,expected_historical_exposure=.11080818);results=[trajectory(t,s,ledger) for t,s in TASKS]; success=any(x["official_score"]["success"] for x in results); outputs=lifecycle(results) if success else {};status="go_separate_corrected_evaluation_smoke" if outputs else "no_go_executor_acquisition_incompatible";store.write("final_result","final",{"status":status,"results":results,"lifecycle_outputs":outputs,"ledger_exposure_usd":ledger.charged_or_reserved});(ROOT/"final_result.json").write_text(json.dumps({"status":status,"ledger_exposure_usd":ledger.charged_or_reserved},indent=2)+"\n")
if __name__=="__main__":main()
