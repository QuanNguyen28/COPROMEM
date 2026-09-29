#!/usr/bin/env python3
"""Standalone five-arm, exploratory-only v6.1 evaluation successor."""
from __future__ import annotations
import argparse, hashlib, json, os, pathlib, sys, time
ROOT=pathlib.Path(__file__).resolve().parents[1]; sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from copromem.contrastive_graph_v6 import digest
from copromem.experiments.reme_copromem.contrastive_v6_runner import retrieval_record, task_batch_update
from copromem.experiments.reme_copromem.runner import AppendOnlyLedger, execute_trajectory, official_post, services, v5_budget_bound, write_json, append
from copromem.experiments.reme_copromem.v61_custody import classify
from scripts.run_v6_shared_acquisition import c_free_gib,file_sha,git_head

SOURCE=ROOT/'artifacts/research/official_reme_copromem_pilot/v6_shared_acquisition_001'; CONSTRUCTION=ROOT/'artifacts/research/official_reme_copromem_pilot/v6_1_exploratory_diagnostic_construction_003'
COPRO=SOURCE/'copromem-v6.1-semantic-recovery-003'; INV=ROOT/'artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v5_engineering_001/public-dev-descriptors.json'; REG=ROOT/'research/reme_copromem_fixed_dynamic_review/appworld_public_tool_schema_registry_v5_3.json'
ARMS=['no_memory','official_upstream_reme_fixed','official_upstream_reme_dynamic','copromem_v6_1_fixed','copromem_v6_1_dynamic']
def ev(run,n,**x): append(run/'progress.jsonl',{'event':n,'time_ns':time.time_ns(),**x})
def st(run,s,**x): write_json(run/'runner-status.json',{'state':s,'pid':os.getpid(),'updated_ns':time.time_ns(),**x})
def key():
 for line in (ROOT/'.env').read_text(encoding='utf-8').splitlines():
  if line.startswith('OPENROUTER_API_KEY='): return line.split('=',1)[1].strip().strip("'\"")
 raise RuntimeError('OpenRouter credential unavailable')
def guard(value,run,stage):
 free=c_free_gib(); p=value['storage_policy']
 if free<3: raise RuntimeError('C-drive mandatory stop threshold breached')
 if free<4: ev(run,'storage_warning',stage=stage,c_free_gib=free)
def identities():
 report=json.loads((CONSTRUCTION/'FINAL_CONSTRUCTION_REPORT.json').read_text()); gate=json.loads((COPRO/'semantic-admission-gate.json').read_text())
 if report['shared_bank_sha256']!='6c3bc799ec0beb034fd2b81ee0d5cbf6e89a14f3a5a39ebf70d34853686b00a0' or gate['state_sha256']!='add35eca3ccaa9780183a144328157db2c64b932e5b69a7e3d5b87fd4efc9448':raise RuntimeError('completed bank identity mismatch')
 return report,gate
def prepare(run):
 if run.exists() and any(run.iterdir()):raise RuntimeError('run nonempty')
 report,gate=identities(); audit=classify(ROOT,INV); hard=set(audit['hard_exclusion'])|set(audit['ambiguous_exclusion']); inv=json.loads(INV.read_text())['tasks']; state=json.loads((COPRO/'fixed-bank.json').read_text()); registry=json.loads(REG.read_text())
 schemas=state['contrastive_v6_schemas']; terminals=sorted({x['terminal_effect'] for x in schemas.values()}); candidates=[]
 for row in inv:
  tid=str(row['task_id']); fam=tid.rsplit('_',1)[0]
  if tid in hard:continue
  desc={'family':fam,'public_app_descriptions_sha256':digest(row['app_descriptions']),'compatible_terminal_effects':terminals}
  candidates.append({'task_id':tid,'family':fam,'schema_family_hash':digest(terminals),'descriptor_sha256':digest(desc),'descriptor':desc})
 candidates.sort(key=lambda x:(x['schema_family_hash'],x['descriptor_sha256'],x['task_id'])); selected=[]; seen=set()
 for row in candidates:
  if row['family'] not in seen: selected.append(row);seen.add(row['family'])
  if len(selected)==6:break
 run.mkdir(parents=True); write_json(run/'custody-audit.json',audit); write_json(run/'allocation-audit.json',{'inventory_sha256':file_sha(INV),'exclusion_set_sha256':digest(sorted(hard)),'candidate_list_sha256':digest(candidates),'ordering_rule':'(schema_family_hash, descriptor_sha256, task_id)','selected':selected,'compatibility_conditioned_exploratory_sampling':True,'test_normal_used':False})
 if len(selected)<6:raise RuntimeError('fewer than six fresh compatible public families')
 limits={'executor':1800,'reme_lifecycle':256,'reme_embedding':1024,'copromem_decomposition':0}; budget=v5_budget_bound(call_limits=limits,historical_usd=2.31368065,lifecycle_input_ceiling=131072)
 if budget['all_in_usd']>100:raise RuntimeError('budget exceeds USD 100')
 m={'protocol':'v6_1_exploratory_diagnostic_evaluation_001','exploratory_diagnostic_only':True,'git_commit':git_head(),'arms':ARMS,'evaluation':{'split':'dev','task_ids':[x['task_id'] for x in selected],'seeds':[11001,11002],'expected_trajectories':60},'banks':{'reme_shared_sha256':report['shared_bank_sha256'],'copromem_sha256':gate['state_sha256']},'storage_policy':{'launch_floor_gib':5,'warning_gib':4,'mandatory_stop_gib':3},'execution':{'model':'deepseek/deepseek-v4.1-flash','provider_only':'deepseek','temperature':.7,'top_p':1.0,'max_actions':30,'completion_token_ceiling':2048,'context_token_ceiling':32768},'budget':{**budget,'hard_cap_usd':100,'call_limits':limits},'allocation_audit_sha256':file_sha(run/'allocation-audit.json'),'custody_audit_sha256':file_sha(run/'custody-audit.json')}
 write_json(run/'template.json',m)
def freeze(run):
 m=json.loads((run/'template.json').read_text());
 if m['git_commit']!=git_head():raise RuntimeError('source changed')
 write_json(run/'manifest.json',m)
 (run/'manifest.sha256').write_text(file_sha(run/'manifest.json')+'\n')
def load(run):
 if file_sha(run/'manifest.json')!=(run/'manifest.sha256').read_text().strip():raise RuntimeError('manifest mismatch')
 m=json.loads((run/'manifest.json').read_text());
 if c_free_gib()<5:raise RuntimeError('C launch floor')
 identities()
 return m
def summary(run,m):
 rows=[]
 for p in (run/'artifacts').glob('*/*/*.json'):
  try:rows.append(json.loads(p.read_text()))
  except:pass
 out={'completed':len(rows),'expected':60,'arms':{}}
 for a in ARMS:
  x=[r for r in rows if r.get('arm')==a]; out['arms'][a]={'Completed':len(x),'Successes':sum(r['after_score']==1 for r in x),'AvgScore':sum(r['after_score'] for r in x)/len(x) if x else 0,'SuccessRate':sum(r['after_score']==1 for r in x)/len(x) if x else 0,'AvgActions':sum(r['actions'] for r in x)/len(x) if x else 0,'Calls':0,'Cost':0}
 write_json(run/'live-summary.json',out)
def run(run):
 m=load(run); lock=run/'runner.lock';
 if lock.exists():raise RuntimeError('duplicate runner')
 write_json(lock,{'pid':os.getpid()})
 ledger=AppendOnlyLedger(run/'ledger.jsonl',100,m['budget']['call_limits']);ledger.reserve('historical-construction-carry',2.31368065,{'role':'historical_carry_forward'});ledger.settle('historical-construction-carry',2.31368065,{'role':'historical_carry_forward'});k=key();st(run,'running',manifest_sha256=file_sha(run/'manifest.json')); state=json.loads((COPRO/'fixed-bank.json').read_text()); registry=json.loads(REG.read_text()); terms=sorted({x['terminal_effect'] for x in state['contrastive_v6_schemas'].values()})
 try:
  with services(run,run/'ledger.jsonl',run/'progress.jsonl',100,['reme-fixed','reme-dynamic'],lifecycle_input_ceiling=131072) as svc:
   shared=CONSTRUCTION/'reme/shared-bank.jsonl';
   for name in ('reme-fixed','reme-dynamic'): official_post(svc[name].base_url,'load_memory',{'load_file_path':str(shared),'clear_existing':True})
   for task in m['evaluation']['task_ids']:
    guard(m,run,'task'); pre=state; copro=[]
    for trial,seed in enumerate(m['evaluation']['seeds'],1):
     for arm in ARMS:
      path=run/'artifacts'/task/arm/f'trial-{trial}.json';
      if path.exists():continue
      kwargs={};
      if arm.startswith('official_upstream_reme'):kwargs['memory_base_url']=svc['reme-fixed' if arm.endswith('fixed') else 'reme-dynamic'].base_url
      if arm.startswith('copromem'):
       guidance,prov=retrieval_record(state=pre,query_operations=terms,registry_sha256=registry['registry_sha256']); write_json(run/'retrievals'/task/f'{arm}-{trial}.json',{'pre_state_sha256':digest(pre),'guidance':guidance,'provenance':prov});kwargs['memory_for_instruction']=lambda *_a,g=guidance:g
      result=execute_trajectory(run=run,progress=run/'progress.jsonl',ledger=ledger,api_key=k,all_task_ids=m['evaluation']['task_ids'],arm=arm,task_id=task,trial_id=trial,seed=seed,max_actions=30,temperature=.7,phase='evaluation',artifact_path=path,**kwargs)
      if arm=='copromem_v6_1_dynamic':copro.append(result)
     summary(run,m)
    post,marker,audit=task_batch_update(artifacts=copro,registry=registry,pre_state=pre,evidence_paths=[r['execution_evidence_path'] for r in copro]);write_json(run/'copromem-dynamic'/task/'update.json',{'pre_state_sha256':digest(pre),'post_state_sha256':digest(post),'marker':marker,'audit':audit});state=post
  summary(run,m);st(run,'completed')
 finally:
  if lock.exists():lock.unlink()
def main():
 p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','freeze','preflight','run']);p.add_argument('--run',required=True,type=pathlib.Path);a=p.parse_args();
 if a.command=='prepare':prepare(a.run)
 elif a.command=='freeze':freeze(a.run)
 elif a.command=='preflight':load(a.run);st(a.run,'preflight_passed')
 else:run(a.run)
if __name__=='__main__':main()
