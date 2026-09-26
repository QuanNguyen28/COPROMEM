"""Registered exposed-task plumbing smoke; invoke only after zero-cost tests."""
import json, os, subprocess, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0,"src")
from copromem.checkpoints import RunStore
from copromem.successor_ledger import SuccessorLedger
from copromem.appworld_acquisition_gate import AcquisitionJournal, AcquisitionRef
from copromem.checkpoints import digest

ROOT=Path("artifacts/research/reme_copromem_comparison/direct_deepseek_successor_smoke")
PARENT=Path("artifacts/research/reme_copromem_comparison/openrouter_brokered_smoke")
WORKER="/mnt/e/Project/AAMAS/COPROMEM/research/containers/appworld/real_worker.py"
PY="/home/xiqhq/copromem-appworld/venv/bin/python"
TOOL={"type":"function","function":{"name":"execute_python","description":"Execute one AppWorld Python action.","strict":True,"parameters":{"type":"object","properties":{"code":{"type":"string"}},"required":["code"],"additionalProperties":False}}}
def key():
 for line in Path(".env").read_text().splitlines():
  if line.startswith("DEEPSEEK_API_KEY="): return line.split("=",1)[1].strip().strip("'\\\"")
 raise RuntimeError("missing key")
def worker(task, name):
 p=subprocess.Popen(["wsl.exe","-d","Ubuntu","--cd","/home/xiqhq/copromem-appworld","--",PY,WORKER],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
 def send(x): p.stdin.write(json.dumps(x)+"\n");p.stdin.flush();return json.loads(p.stdout.readline())
 return p,send({"op":"start","task_id":task,"experiment_name":name}),send
def call(prompt, ledger, meta):
 k=str(time.time_ns()); ledger.reserve(k,.006,meta)
 body={"model":"deepseek-flash","messages":[{"role":"system","content":"You are an AppWorld executor. Return no prose: call execute_python exactly once with the next safe Python action."},{"role":"user","content":prompt+"\n\nCall execute_python exactly once now."}],"tools":[TOOL],"tool_choice":{"type":"function","function":{"name":"execute_python"}},"max_tokens":128,"stream":False,"reasoning_effort":"none"}
 t=time.perf_counter()
 try:
  r=urllib.request.urlopen(urllib.request.Request("https://api.deepseek.com/chat/completions",data=json.dumps(body).encode(),headers={"Authorization":"Bearer "+key(),"Content-Type":"application/json"},method="POST"),timeout=45)
  x=json.loads(r.read()); u=x.get("usage",{}); c=(u.get("prompt_tokens",0)*.3+u.get("completion_tokens",0)*1.2)/1e6; ledger.settle(k,c)
 except urllib.error.HTTPError as err:
  if err.code in (401, 403): raise RuntimeError("direct DeepSeek authentication failed") from err
  return None,{"usage":{},"cost":.006,"latency":time.perf_counter()-t,"finish":"http_"+str(err.code),"tool_valid":False}
 except Exception as err:
  return None,{"usage":{},"cost":.006,"latency":time.perf_counter()-t,"finish":"transport_error","tool_valid":False}
 ch=x["choices"][0]; tc=(ch["message"].get("tool_calls") or [])
 reasoning=u.get("reasoning_tokens",u.get("completion_tokens_details",{}).get("reasoning_tokens",0))
 if x.get("model")!="deepseek-flash" or reasoning or len(tc)!=1:
  return None,{"usage":u,"cost":c,"latency":time.perf_counter()-t,"finish":ch.get("finish_reason"),"tool_valid":False}
 try: code=json.loads(tc[0]["function"]["arguments"])["code"]
 except Exception: return None,{"usage":u,"cost":c,"latency":time.perf_counter()-t,"finish":ch.get("finish_reason"),"tool_valid":False}
 return code,{"usage":u,"cost":c,"latency":time.perf_counter()-t,"finish":ch.get("finish_reason"),"tool_valid":True}
def trajectory(task, arm, memory, ledger):
 p,start,send=worker(task,arm); base="Use only execute_python for AppWorld. "+start["instruction"]+"\n"+json.dumps(start["app_descriptions"])+memory; rows=[]
 journal=None
 if arm=="shared_acquisition":
  journal=AcquisitionJournal(RunStore(ROOT),AcquisitionRef(task,0,0))
  journal.start(task_manifest_sha256=digest({"task_id":task,"instruction":start["instruction"]}),base_prompt_sha256=digest(base),tool_schema_sha256=digest(TOOL))
 for i in range(10):
  code,rec=call(base,ledger,{"arm":arm,"role":"executor","task_id":task,"phase":"acquisition" if arm=="shared_acquisition" else "evaluation","trial":0,"iteration":i,"model":"deepseek-flash"})
  if code is None:
   rows.append(rec);break
  out=send({"op":"action","code":code});rows.append({**rec,"tool_valid":True,"output":out})
  if journal is not None: journal.action(i,code=code,native_output=out,completed=bool(out["completed"]))
  if out["completed"]: break
  base += "\nPrevious native action output: "+json.dumps(out)+"\nChoose the next action."
 score=send({"op":"finish"});p.wait(timeout=10)
 if journal is not None: journal.finish(official_score=score)
 return score,rows
def main():
 if ROOT.joinpath("smoke_result.json").exists():
  raise SystemExit("registered smoke is terminal; create a newly authorized manifest before any replay")
 l=SuccessorLedger(RunStore(ROOT),parent_root=PARENT); results={}
 acq=[]
 existing={}
 existing_arms=set()
 for path in (ROOT/"reservations").glob("*.json"):
  try:
   item=json.loads(path.read_text()); existing.setdefault(item.get("task_id"),[]).append(item); existing_arms.add(item.get("arm"))
  except json.JSONDecodeError: pass
 for t in ("50e1ac9_1","50e1ac9_2"):
  if t in existing:
   acq.append({"task":t,"score":{"success":False,"skipped_replay":True},"calls":[],"note":"prior settled acquisition dispatch; never replayed"})
  else:
   s,r=trajectory(t,"shared_acquisition","",l);acq.append({"task":t,"score":s,"calls":r})
 mem="\nShared acquisition evidence available." if any(x["score"]["success"] for x in acq) else "\nShared acquisition failures retained."
 for arm in ("no_memory","reme_fixed_faithful_adaptation","reme_dynamic_faithful_adaptation","copromem_v2"):
  if arm in existing_arms:
   results[arm]={"score":{"success":False,"interrupted":True},"calls":[],"note":"prior settled dispatch was interrupted by controller timeout; never replayed"}
   continue
  suffix="" if arm=="no_memory" else mem
  s,r=trajectory("fac291d_1",arm,suffix,l);results[arm]={"score":s,"calls":r}
 ROOT.joinpath("smoke_result.json").write_text(json.dumps({"acquisition":acq,"arms":results,"ledger":l.charged_or_reserved},indent=2))
if __name__=="__main__":main()
