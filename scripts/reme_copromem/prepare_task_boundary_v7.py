"""Freeze the public-only development allocation for task-boundary 007."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess

from copromem.benchmarks.appworld.adapter import CoProMemAppWorldAdapter
from copromem.experiments.reme_copromem.runner import AppendOnlyLedger, construct_copromem, digest, raw_acquisition_trajectories, v5_budget_bound, write_json
from copromem.learning import ActionObservation, LearningCore

ROOT = pathlib.Path(__file__).resolve().parents[2]
PAIR = ("37a8675_1", "37a8675_2")
# Public operation/slot shape only; concrete payment/contact values are absent.
DESCRIPTOR = [
 {"operation":"apis.api_docs.show_api_descriptions","input_slots":["app_name"],"output_slots":["observation"]},
 {"operation":"apis.api_docs.show_api_doc","input_slots":["api_name","app_name"],"output_slots":["observation"]},
 {"operation":"apis.api_docs.show_app_descriptions","input_slots":[],"output_slots":["observation"]},
 {"operation":"apis.api_docs.show_api_descriptions","input_slots":["app_name"],"output_slots":["observation"]},
 {"operation":"apis.supervisor.show_account_passwords","input_slots":[],"output_slots":["var_1"]},
 {"operation":"apis.venmo.login","input_slots":["password","username","var_1"],"output_slots":["var_2"]},
 {"operation":"apis.api_docs.show_api_descriptions","input_slots":["app_name"],"output_slots":["observation"]},
 {"operation":"apis.api_docs.show_api_doc","input_slots":["api_name","app_name"],"output_slots":["observation"]},
 {"operation":"apis.venmo.send_money","input_slots":["access_token","amount","phone_number"],"output_slots":["observation"]},
 {"operation":"apis.supervisor.complete_task","input_slots":[],"output_slots":["observation"]}
]
def sha(p:pathlib.Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def previously_registered_ids() -> set[str]:
 """Metadata-only custody check; no AppWorld task is opened here."""
 result:set[str]=set()
 for path in (ROOT/'artifacts/research/official_reme_copromem_pilot').glob('**/manifest.json'):
  try: row=json.loads(path.read_text(encoding='utf-8'))
  except (OSError,json.JSONDecodeError): continue
  result.update(str(x) for x in row.get('evaluation',{}).get('task_ids',[]))
  result.update(str(x) for x in row.get('acquisition',{}).get('task_ids',[]))
 return result
def main()->None:
 p=argparse.ArgumentParser();p.add_argument('--run',type=pathlib.Path,required=True);p.add_argument('--acquisition',type=pathlib.Path,required=True);a=p.parse_args()
 inv=ROOT/'artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v5_engineering_001/public-dev-descriptors.json'; public=json.loads(inv.read_text())
 ids={x['task_id'] for x in public['tasks']}
 if not set(PAIR)<=ids:raise RuntimeError('007 pair is not public development inventory')
 raw=json.loads(a.acquisition.read_text());rows=raw.get('trajectories',raw)
 if len(rows)!=32 or set(PAIR)&{x['task_id'] for x in rows}:raise RuntimeError('007 acquisition overlap')
 if set(PAIR)&previously_registered_ids():raise RuntimeError('007 pair overlaps a prior frozen allocation')
 events=tuple(ActionObservation(**x) for x in DESCRIPTOR)
 if not LearningCore.signature(events):raise RuntimeError('007 public descriptor invalid')
 a.run.mkdir(parents=True,exist_ok=True); limits={'executor':240,'reme_lifecycle':0,'reme_embedding':0,'copromem_decomposition':0}; ledger=AppendOnlyLedger(a.run/'ledger.jsonl',100.,limits)
 state,_=construct_copromem(run=a.run,progress=a.run/'progress.jsonl',ledger=ledger,api_key='',raw=raw_acquisition_trajectories(rows),call_cap=0)
 adapter=CoProMemAppWorldAdapter(api_key='');adapter.clone_from_state(state); compatibility=adapter.module.learning.retrieve('appworld',events).compatibility
 if compatibility!='unknown':raise RuntimeError('007 pair not initially unknown')
 budget=v5_budget_bound(call_limits=limits,historical_usd=.171536418);budget.update({'call_limits':limits,'hard_cap_usd':100.,'fits_hard_cap':budget['all_in_usd']<=100.,'ledger_dispatch_cap_usd':budget['dispatchable_usd']})
 selected={x['task_id']:x for x in public['tasks'] if x['task_id'] in PAIR}
 template={'protocol':'v5_engineering_007_task_boundary','engineering_only_exposed':True,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
 'acquisition':{'source_export':str(a.acquisition.resolve()),'export_sha256':sha(a.acquisition),'expected_trajectories':32,'fresh_state_required':True},'arms':['no_memory','copromem_dynamic'],
 'execution':{'max_actions':30,'temperature':.7,'top_p':1.,'c_floor_gib':5.,'model':'deepseek/deepseek-v4.1-flash','provider':'deepseek','fallbacks':False,'reasoning_effort':'none','stream':False,'completion_token_ceiling':2048},
 'evaluation':{'split':'dev','task_ids':list(PAIR),'a_task_id':PAIR[0],'b_task_id':PAIR[1],'trial_ids':[1,2],'seeds':[7701,7702],'expected_trajectories':8,'descriptors':{PAIR[0]:DESCRIPTOR,PAIR[1]:DESCRIPTOR},'descriptor_sha256':digest(DESCRIPTOR),'public_instruction_sha256':{k:hashlib.sha256(selected[k]['instruction'].encode()).hexdigest() for k in PAIR},'initial_compatibility':{k:compatibility for k in PAIR}},
 'budget':budget,'selection':{'public_only':True,'test_normal_excluded':True,'task_family':'37a8675','inventory_sha256':sha(inv),'acquisition_ids_sha256':digest(sorted({x['task_id'] for x in rows})),'prior_registered_ids_sha256':digest(sorted(previously_registered_ids()))}}
 write_json(a.run/'template.json',template);write_json(a.run/'descriptor-audit.json',{'a':PAIR[0],'b':PAIR[1],'compatibility':compatibility,'descriptor_sha256':template['evaluation']['descriptor_sha256'],'public_only':True,'test_normal_used':False})
 print(json.dumps({'a':PAIR[0],'b':PAIR[1],'all_in_usd':budget['all_in_usd']},sort_keys=True))
if __name__=='__main__':main()
