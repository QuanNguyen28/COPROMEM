#!/usr/bin/env python3
"""Run the committed v6.2.1 public-instruction descriptor screen offline."""
from __future__ import annotations
import argparse, hashlib, json, pathlib, subprocess, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]; sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from copromem.experiments.reme_copromem.descriptor_screening_v621 import screen_public_descriptor, digest

def main() -> None:
 p=argparse.ArgumentParser();p.add_argument('--protocol',required=True,type=pathlib.Path);p.add_argument('--out',required=True,type=pathlib.Path);p.add_argument('--allocation-out',type=pathlib.Path);a=p.parse_args()
 protocol=json.loads(a.protocol.read_text(encoding='utf-8')); registry=json.loads((ROOT/'research/reme_copromem_fixed_dynamic_review/appworld_public_tool_schema_registry_v5_3.json').read_text())
 state=json.loads((ROOT/'artifacts/research/official_reme_copromem_pilot/v6_shared_acquisition_001/copromem-v6.1-semantic-recovery-003/fixed-bank.json').read_text())
 task_root=ROOT.parent/'_work/appworld_official_0.1.3.post1/data/tasks'; rows=[]
 for task_id in protocol['ordered_candidate_ids']:
  raw=json.loads((task_root/task_id/'specs.json').read_text(encoding='utf-8'))
  instruction=raw.get('instruction')
  if not isinstance(instruction,str):raise RuntimeError(f'public instruction absent: {task_id}')
  # Never inspect or retain supervisor, datetime, database version, or canary.
  row=screen_public_descriptor(task_id=task_id,instruction=instruction,app_descriptions={},tool_metadata={'app_descriptions':{}},registry=registry,state=state)
  row['screening_sha256']=digest({key:value for key,value in row.items() if key!='screening_sha256'});rows.append(row)
 compatible=[r for r in rows if r['compatibility_class']=='compatible']; selected=compatible[:2]
 selected_ids={r['task_id'] for r in selected}; negative=next((r for r in rows if r['task_id'] not in selected_ids and r['compatibility_class']=='incompatible'),None)
 out={'version':'v6.2.1-engineering-descriptor-screening-results-v1','screening_protocol_sha256':hashlib.sha256(a.protocol.read_bytes()).hexdigest(),'provider_calls':0,'execution_calls':0,'scorer_calls':0,'model_calls':0,'rows':rows,'compatible_count':len(compatible),'incompatible_count':len(rows)-len(compatible),'selected_task_ids':[r['task_id'] for r in selected]+([] if negative is None else [negative['task_id']]),'selection_satisfied':len(selected)==2 and negative is not None}
 out['screening_table_sha256']=digest(out['rows']);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
 if a.allocation_out:
  if not out['selection_satisfied']:raise RuntimeError('screening did not yield the preregistered allocation')
  selected_rows=[next(row for row in rows if row['task_id']==task_id) for task_id in out['selected_task_ids']]
  allocation={'version':'v6.2.1-engineering-allocation-v1','selection_source':'public_pre_execution_metadata_only','payloads_opened':False,'split':'test_normal','source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'selected_task_ids':out['selected_task_ids'],'compatible_task_count':2,'negative_control_count':1,'screening_results_sha256':hashlib.sha256(a.out.read_bytes()).hexdigest(),'selected_descriptor_sha256s':[row['descriptor_sha256'] for row in selected_rows],'selected_compatible_schema_ids':[row['compatible_schema_ids'] for row in selected_rows],'negative_control_rejection_reasons':selected_rows[2]['candidate_features'],'registry_sha256':registry['registry_sha256']}
  a.allocation_out.parent.mkdir(parents=True,exist_ok=True);a.allocation_out.write_text(json.dumps(allocation,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
