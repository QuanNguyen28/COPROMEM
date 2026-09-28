"""Freeze the single fresh public A/B allocation for v5.1 run 010."""
from __future__ import annotations
import argparse, hashlib, json, pathlib, subprocess
from copromem.benchmarks.appworld.adapter import CoProMemAppWorldAdapter
from copromem.experiments.reme_copromem.runner import AppendOnlyLedger, construct_copromem, digest, raw_acquisition_trajectories, v5_budget_bound, write_json
from copromem.learning import ActionObservation, LearningCore
ROOT=pathlib.Path(__file__).resolve().parents[2]; PAIR=('4fab96f_1','4fab96f_2')
DESCRIPTOR=[{'operation':'apis.venmo.get_payment_requests','input_slots':['access_token'],'output_slots':['requests']},{'operation':'apis.venmo.send_reminder','input_slots':['access_token','request_id'],'output_slots':['observation']}]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def used():
 s=set()
 for p in (ROOT/'artifacts/research/official_reme_copromem_pilot').glob('**/manifest.json'):
  try:r=json.loads(p.read_text())
  except Exception:continue
  s|={str(x) for x in r.get('evaluation',{}).get('task_ids',[]) if x};s|={str(x) for x in r.get('acquisition',{}).get('task_ids',[]) if x}
 return s
def main():
 a=argparse.ArgumentParser();a.add_argument('--run',type=pathlib.Path,required=True);a.add_argument('--acquisition',type=pathlib.Path,required=True);x=a.parse_args();inv=ROOT/'artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v5_engineering_001/public-dev-descriptors.json';by={r['task_id']:r for r in json.loads(inv.read_text())['tasks']}
 if not set(PAIR)<=set(by) or set(PAIR)&used():raise RuntimeError('010 pair is not fresh')
 raw=json.loads(x.acquisition.read_text());rows=raw.get('trajectories',raw)
 if len(rows)!=32 or set(PAIR)&{r['task_id'] for r in rows}:raise RuntimeError('acquisition overlap')
 events=tuple(ActionObservation(**r) for r in DESCRIPTOR);assert LearningCore.signature(events)
 x.run.mkdir(parents=True,exist_ok=True);limits={'executor':240,'reme_lifecycle':0,'reme_embedding':0,'copromem_decomposition':0};ledger=AppendOnlyLedger(x.run/'ledger.jsonl',100.,limits);state,_=construct_copromem(run=x.run,progress=x.run/'progress.jsonl',ledger=ledger,api_key='',raw=raw_acquisition_trajectories(rows),call_cap=0);ad=CoProMemAppWorldAdapter(api_key='');ad.clone_from_state(state);assert ad.module.learning.retrieve('appworld',events).compatibility=='unknown'
 budget=v5_budget_bound(call_limits=limits,historical_usd=.171536418);budget.update({'call_limits':limits,'hard_cap_usd':100.,'fits_hard_cap':budget['all_in_usd']<=100.,'ledger_dispatch_cap_usd':budget['dispatchable_usd']})
 t={'protocol':'v5_1_engineering_009_observable_subgraph','task_boundary_policy':'observable_supported_subgraph_v5_1','helper_registry_version':'public-helper-registry-v1','engineering_only_exposed':True,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'acquisition':{'source_export':str(x.acquisition.resolve()),'export_sha256':sha(x.acquisition),'expected_trajectories':32,'fresh_state_required':True},'arms':['no_memory','copromem_dynamic'],'execution':{'max_actions':30,'temperature':.7,'top_p':1.,'c_floor_gib':5.,'model':'deepseek/deepseek-v4.1-flash','provider':'deepseek','fallbacks':False,'reasoning_effort':'none','stream':False,'completion_token_ceiling':2048},'evaluation':{'split':'dev','task_ids':list(PAIR),'a_task_id':PAIR[0],'b_task_id':PAIR[1],'trial_ids':[1,2],'seeds':[8001,8002],'expected_trajectories':8,'descriptors':{z:DESCRIPTOR for z in PAIR},'descriptor_sha256':digest(DESCRIPTOR),'public_instruction_sha256':{z:hashlib.sha256(by[z]['instruction'].encode()).hexdigest() for z in PAIR},'initial_compatibility':{z:'unknown' for z in PAIR}},'budget':budget,'selection':{'public_only':True,'test_normal_excluded':True,'prior_ids_sha256':digest(sorted(used()))}}
 write_json(x.run/'template.json',t);write_json(x.run/'descriptor-audit.json',{'a':PAIR[0],'b':PAIR[1],'descriptor_sha256':t['evaluation']['descriptor_sha256'],'policy':t['task_boundary_policy']});print(json.dumps({'a':PAIR[0],'b':PAIR[1],'all_in_usd':budget['all_in_usd']}))
if __name__=='__main__':main()
