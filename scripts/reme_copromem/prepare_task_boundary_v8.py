"""Freeze the final strict-v5 public-development A/B task pair."""
from __future__ import annotations
import argparse, hashlib, json, pathlib, subprocess
from copromem.benchmarks.appworld.adapter import CoProMemAppWorldAdapter
from copromem.experiments.reme_copromem.runner import AppendOnlyLedger, construct_copromem, digest, raw_acquisition_trajectories, v5_budget_bound, write_json
from copromem.learning import ActionObservation, LearningCore
ROOT=pathlib.Path(__file__).resolve().parents[2]; PAIR=("b119b1f_1","b119b1f_3")
# Public API-shape descriptor only; no task values, execution evidence, or scorer data.
DESCRIPTOR=[
 {"operation":"apis.api_docs.show_api_descriptions","input_slots":["app_name"],"output_slots":["observation"]},
 {"operation":"apis.api_docs.show_api_doc","input_slots":["api_name","app_name"],"output_slots":["observation"]},
 {"operation":"apis.supervisor.show_account_passwords","input_slots":[],"output_slots":["credentials"]},
 {"operation":"apis.spotify.login","input_slots":["credentials"],"output_slots":["access_token"]},
 {"operation":"apis.spotify.play_previous_song","input_slots":["access_token"],"output_slots":["observation"]},
 {"operation":"apis.supervisor.complete_task","input_slots":[],"output_slots":["observation"]},]
def sha(p:pathlib.Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def prior_ids()->set[str]:
 out=set()
 for p in (ROOT/'artifacts/research/official_reme_copromem_pilot').glob('**/manifest.json'):
  try:r=json.loads(p.read_text())
  except Exception:continue
  out|={str(x) for x in r.get('evaluation',{}).get('task_ids',[]) if x};out|={str(x) for x in r.get('acquisition',{}).get('task_ids',[]) if x}
 return out
def main()->None:
 q=argparse.ArgumentParser();q.add_argument('--run',type=pathlib.Path,required=True);q.add_argument('--acquisition',type=pathlib.Path,required=True);a=q.parse_args()
 public=json.loads((ROOT/'artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v5_engineering_001/public-dev-descriptors.json').read_text());by={x['task_id']:x for x in public['tasks']}
 if not set(PAIR)<=set(by) or set(PAIR)&prior_ids():raise RuntimeError('008 pair is not fresh public-development inventory')
 raw=json.loads(a.acquisition.read_text());rows=raw.get('trajectories',raw)
 if len(rows)!=32 or set(PAIR)&{x['task_id'] for x in rows}:raise RuntimeError('008 acquisition overlap')
 events=tuple(ActionObservation(**x) for x in DESCRIPTOR)
 if LearningCore.signature(events) is None:raise RuntimeError('invalid public descriptor')
 a.run.mkdir(parents=True,exist_ok=True); limits={'executor':240,'reme_lifecycle':0,'reme_embedding':0,'copromem_decomposition':0};ledger=AppendOnlyLedger(a.run/'ledger.jsonl',100.,limits)
 state,_=construct_copromem(run=a.run,progress=a.run/'progress.jsonl',ledger=ledger,api_key='',raw=raw_acquisition_trajectories(rows),call_cap=0)
 bank=CoProMemAppWorldAdapter(api_key='');bank.clone_from_state(state)
 if bank.module.learning.retrieve('appworld',events).compatibility!='unknown':raise RuntimeError('008 must begin unknown')
 budget=v5_budget_bound(call_limits=limits,historical_usd=.171536418);budget.update({'call_limits':limits,'hard_cap_usd':100.,'fits_hard_cap':budget['all_in_usd']<=100.,'ledger_dispatch_cap_usd':budget['dispatchable_usd']})
 t={'protocol':'v5_engineering_008_task_boundary','engineering_only_exposed':True,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'acquisition':{'source_export':str(a.acquisition.resolve()),'export_sha256':sha(a.acquisition),'expected_trajectories':32,'fresh_state_required':True},'arms':['no_memory','copromem_dynamic'],'execution':{'max_actions':30,'temperature':.7,'top_p':1.,'c_floor_gib':5.,'model':'deepseek/deepseek-v4.1-flash','provider':'deepseek','fallbacks':False,'reasoning_effort':'none','stream':False,'completion_token_ceiling':2048},'evaluation':{'split':'dev','task_ids':list(PAIR),'a_task_id':PAIR[0],'b_task_id':PAIR[1],'trial_ids':[1,2],'seeds':[7801,7802],'expected_trajectories':8,'descriptors':{PAIR[0]:DESCRIPTOR,PAIR[1]:DESCRIPTOR},'descriptor_sha256':digest(DESCRIPTOR),'public_instruction_sha256':{x:hashlib.sha256(by[x]['instruction'].encode()).hexdigest() for x in PAIR},'initial_compatibility':{x:'unknown' for x in PAIR}},'budget':budget,'selection':{'public_only':True,'test_normal_excluded':True,'inventory_sha256':sha(ROOT/'artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v5_engineering_001/public-dev-descriptors.json'),'prior_ids_sha256':digest(sorted(prior_ids()))}}
 write_json(a.run/'template.json',t);write_json(a.run/'descriptor-audit.json',{'a':PAIR[0],'b':PAIR[1],'descriptor_sha256':t['evaluation']['descriptor_sha256'],'public_only':True,'test_normal_used':False});print(json.dumps({'a':PAIR[0],'b':PAIR[1],'all_in_usd':budget['all_in_usd']},sort_keys=True))
if __name__=='__main__':main()
