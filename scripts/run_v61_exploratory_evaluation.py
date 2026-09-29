#!/usr/bin/env python3
"""Standalone five-arm, exploratory-only v6.1 evaluation successor."""
from __future__ import annotations
import argparse, hashlib, json, os, pathlib, sys, time
ROOT=pathlib.Path(__file__).resolve().parents[1]; sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from copromem.contrastive_graph_v6 import digest
from copromem.experiments.reme_copromem.contrastive_v6_runner import retrieval_record, semantic_task_batch_update
from copromem.experiments.reme_copromem.task_query import derive_task_query, validate_task_query
from copromem.experiments.reme_copromem.runner import AppendOnlyLedger, execute_trajectory, official_post, services, v5_budget_bound, write_json, append
from copromem.integrations.reme.dynamic_checkpoint import DynamicUpdateIdentity, ReMeDynamicCheckpointManager
from copromem.experiments.reme_copromem.evidence_contract import validate as validate_execution_evidence
from copromem.experiments.reme_copromem.live_summary import build_live_summary, write_live_summary
from copromem.experiments.reme_copromem.live_summary import reconcile_ledger
from copromem.experiments.reme_copromem.copromem_dynamic_checkpoint import CoProMemDynamicCheckpointManager
from copromem.integrations.reme.fixed_checkpoint import ReMeFixedIntegrityManager
from copromem.experiments.reme_copromem.runtime_identity import build_evaluation_runtime_identity, verify_runtime_identity, evaluation_runtime_inputs
from copromem.experiments.reme_copromem.v61_custody import classify
from scripts.run_v6_shared_acquisition import c_free_gib,file_sha,git_head

SOURCE=ROOT/'artifacts/research/official_reme_copromem_pilot/v6_shared_acquisition_001'; CONSTRUCTION=ROOT/'artifacts/research/official_reme_copromem_pilot/v6_1_exploratory_diagnostic_construction_003'
COPRO=SOURCE/'copromem-v6.1-semantic-recovery-003'; INV=ROOT/'artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v5_engineering_001/public-dev-descriptors.json'; REG=ROOT/'research/reme_copromem_fixed_dynamic_review/appworld_public_tool_schema_registry_v5_3.json'
ARMS=['no_memory','official_upstream_reme_fixed','official_upstream_reme_dynamic','copromem_v6_1_fixed','copromem_v6_1_dynamic']
FROZEN_TASK_IDS=['57c3486_2','4ec8de5_1','530b157_1','6bdbc26_2','b119b1f_2','6171bbc_1']
# Evaluations 004 and 005 are audit-only.  The latter's settled exposure and
# unresolved reservation maximum are retained once, never as live requests.
# Evaluation 006 is immutable infrastructure-only evidence.  Its settled
# exposure carries forward once, but no evaluation artifact or Dynamic state is
# imported into this clean restart.
HISTORICAL_EXPOSURE=2.416212543
PROTOCOL='v6_1_exploratory_diagnostic_evaluation_007_clean_restart'
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
def source_commit():
 return os.environ.get('COPROMEM_SOURCE_COMMIT') or git_head()
def _runtime_identity(run,m):
 record_path=run/'runtime-identity.json'
 if not record_path.is_file():raise RuntimeError('runtime identity record is absent')
 record=json.loads(record_path.read_text(encoding='utf-8'))
 content,trees,labels=evaluation_runtime_inputs(root=ROOT,source_commit=m['git_commit'])
 verify_runtime_identity(record,content=content,trees=trees,labels=labels)
 if file_sha(record_path)!=m.get('runtime_identity_file_sha256') or record.get('runtime_identity_sha256')!=m.get('runtime_identity_sha256'):raise RuntimeError('manifest-bound runtime identity mismatch')
 return record
def prepare(run):
 if run.exists() and any(run.iterdir()):raise RuntimeError('run nonempty')
 report,gate=identities(); run.mkdir(parents=True)
 limits={'executor':1800,'reme_lifecycle':256,'reme_embedding':1024,'copromem_decomposition':0}; budget=v5_budget_bound(call_limits=limits,historical_usd=HISTORICAL_EXPOSURE,lifecycle_input_ceiling=131072)
 if budget['all_in_usd']>100:raise RuntimeError('budget exceeds USD 100')
 commit=source_commit();runtime=build_evaluation_runtime_identity(root=ROOT,source_commit=commit);write_json(run/'runtime-identity.json',runtime)
 m={'protocol':PROTOCOL,'exploratory_diagnostic_only':True,'predecessor_evaluation_002_excluded':True,'predecessor_evaluation_004_excluded':True,'predecessor_evaluation_005_excluded':True,'git_commit':commit,'runtime_identity_sha256':runtime['runtime_identity_sha256'],'runtime_identity_file_sha256':file_sha(run/'runtime-identity.json'),'arms':ARMS,'evaluation':{'split':'dev','task_ids':FROZEN_TASK_IDS,'seeds':[11001,11002],'stochastic_trial_ids':[11001,11002],'provider_seed':None,'trial_semantics':'ordered_stochastic_labels_not_provider_seeds','expected_trajectories':60},'banks':{'reme_shared_sha256':report['shared_bank_sha256'],'copromem_sha256':gate['state_sha256']},'storage_policy':{'launch_floor_gib':5,'warning_gib':4,'mandatory_stop_gib':3},'execution':{'model':'deepseek/deepseek-v4.1-flash','provider_only':'deepseek','temperature':.7,'top_p':1.0,'max_actions':30,'completion_token_ceiling':2048,'context_token_ceiling':32768},'budget':{**budget,'hard_cap_usd':100,'call_limits':limits,'historical_settled_exposure':HISTORICAL_EXPOSURE,'evaluation_004_unresolved_retained_usd':0.0060078,'evaluation_005_unresolved_retained_usd':0.005946},'scientific_protocol_unchanged':True,'clean_restart_from_original_initial_banks':True}
 write_json(run/'template.json',m)
def freeze(run):
 m=json.loads((run/'template.json').read_text());
 if m['git_commit']!=source_commit():raise RuntimeError('source changed')
 _runtime_identity(run,m)
 write_json(run/'manifest.json',m)
 (run/'manifest.sha256').write_text(file_sha(run/'manifest.json')+'\n')
def load(run):
 if file_sha(run/'manifest.json')!=(run/'manifest.sha256').read_text().strip():raise RuntimeError('manifest mismatch')
 m=json.loads((run/'manifest.json').read_text());
 _runtime_identity(run,m)
 if c_free_gib()<5:raise RuntimeError('C launch floor')
 identities()
 return m
def summary(run,m,*,state='running',final=False):
 out=build_live_summary(ledger_path=run/'ledger.jsonl',artifact_root=run/'artifacts',expected_tasks=m['evaluation']['task_ids'],expected_seeds=m['evaluation']['seeds'],historical_expected_usd=HISTORICAL_EXPOSURE,state=state,final=final,expected_trajectories=m['evaluation']['expected_trajectories'])
 write_live_summary(run/'live-summary.json',out)
def _dynamic_order(manifest):
 return [DynamicUpdateIdentity(f'evaluation:official_upstream_reme_dynamic:{task}:trial={trial}:seed={seed}',task,trial,seed) for task in manifest['evaluation']['task_ids'] for trial,seed in enumerate(manifest['evaluation']['seeds'],1)]
def _settled_after(path,offset):
 if not path.exists(): return []
 rows=[]
 for line in path.read_bytes()[offset:].splitlines():
  try:
   row=json.loads(line)
   if row.get('event')=='settle' and str(row.get('role','')).startswith(('reme_lifecycle:reme-dynamic','reme_embedding:reme-dynamic')):rows.append(str(row['id']))
  except json.JSONDecodeError: raise RuntimeError('ledger tail is malformed')
 return rows
def _ledger_tail(path,offset):
 if not path.exists(): return []
 return [json.loads(line) for line in path.read_bytes()[offset:].splitlines()]
def _validate_dynamic_settlements(path,offset,ids):
 rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []
 tail=_ledger_tail(path,offset)
 reserved={str(row['id']) for row in rows if row.get('event')=='reserve'}; settled={str(row['id']) for row in rows if row.get('event')=='settle'}
 for row in tail:
  if row.get('event')=='reserve' and str(row.get('role','')).startswith(('reme_lifecycle:reme-dynamic','reme_embedding:reme-dynamic')) and str(row['id']) not in settled:raise RuntimeError('unresolved ReMe Dynamic lifecycle reservation')
 if any(item not in reserved or item not in settled for item in ids):raise RuntimeError('unknown ReMe Dynamic settlement binding')
def _validate_marker_settlements(path,marker):
 rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []
 settled={str(row['id']):row for row in rows if row.get('event')=='settle'}
 for item in marker['newly_settled_lifecycle_or_embedding_ids']:
  row=settled.get(str(item)); role=str(row.get('role','')) if row else ''
  if not row or not role.startswith(('reme_lifecycle:reme-dynamic','reme_embedding:reme-dynamic')):raise RuntimeError('ReMe Dynamic marker settlement binding is invalid')
def _verify_verifier_no_provider(path,offset):
 if any(str(row.get('role','')).startswith(('reme_lifecycle:reme-dynamic-verifier','reme_embedding:reme-dynamic-verifier')) for row in _ledger_tail(path,offset)):raise RuntimeError('ReMe Dynamic verifier attempted a provider request')
def _dynamic_checkpoint(run,manifest,dynamic,verifier):
 ledger_path=run/'ledger.jsonl'
 def dump(path): official_post(dynamic.base_url,'dump_memory',{'dump_file_path':str(path)})
 def load(path): official_post(dynamic.base_url,'load_memory',{'load_file_path':str(path),'clear_existing':True})
 def verify(snapshot,target):
  official_post(verifier.base_url,'load_memory',{'load_file_path':str(snapshot),'clear_existing':True})
  official_post(verifier.base_url,'dump_memory',{'dump_file_path':str(target)})
 def update(agent,score,event):
  from copromem.integrations.reme.lifecycle import dynamic_post_trial_update
  return dynamic_post_trial_update(agent,score,event)
 return ReMeDynamicCheckpointManager(root=run/'reme-dynamic-checkpoints',ordered_updates=_dynamic_order(manifest),dump_current=dump,load_current=load,dump_verifier=verify,official_update=update,ledger_offset=lambda:ledger_path.stat().st_size if ledger_path.exists() else 0,settled_ids=lambda offset:_settled_after(ledger_path,offset),validate_settlements=lambda offset,ids:_validate_dynamic_settlements(ledger_path,offset,ids),validate_marker_settlements=lambda marker:_validate_marker_settlements(ledger_path,marker),verify_no_provider_calls=lambda offset:_verify_verifier_no_provider(ledger_path,offset),initial_semantic_hash=manifest['banks']['reme_shared_sha256'],validate_evidence=lambda result:validate_execution_evidence(result,run_root=run,expected_registry_sha256=json.loads(REG.read_text())['registry_sha256']),event=lambda row:ev(run,row.pop('event'),**row))
def _has_ledger_reservation(path,call_id):
 if not path.exists():return False
 return any(json.loads(line).get('event')=='reserve' and json.loads(line).get('id')==call_id for line in path.read_text(encoding='utf-8').splitlines())
def _ledger_reconciled(path):
 return not reconcile_ledger(path,historical_expected_usd=HISTORICAL_EXPOSURE).unresolved_reservation_ids
def run(run):
 m=load(run); lock=run/'runner.lock';
 if lock.exists():raise RuntimeError('duplicate runner')
 write_json(lock,{'pid':os.getpid()})
 ledger=AppendOnlyLedger(run/'ledger.jsonl',100,m['budget']['call_limits']);
 if not _has_ledger_reservation(run/'ledger.jsonl','historical-construction-carry'):
  ledger.reserve('historical-construction-carry',HISTORICAL_EXPOSURE,{'role':'historical_carry_forward'});ledger.settle('historical-construction-carry',HISTORICAL_EXPOSURE,{'role':'historical_carry_forward'})
 k=key();st(run,'running',manifest_sha256=file_sha(run/'manifest.json')); fixed_state=json.loads((COPRO/'fixed-bank.json').read_text()); dynamic_state=json.loads(json.dumps(fixed_state,sort_keys=True)); registry=json.loads(REG.read_text())
 if digest(fixed_state)!=digest(dynamic_state) or fixed_state is dynamic_state:raise RuntimeError('CoProMem Fixed/Dynamic initial state isolation failed')
 write_json(run/'copromem-state-identities.json',{'fixed_initial_sha256':digest(fixed_state),'dynamic_initial_sha256':digest(dynamic_state),'non_aliased':True})
 copro_checkpoint=CoProMemDynamicCheckpointManager(root=run/'copromem-dynamic-checkpoints',manifest_sha256=file_sha(run/'manifest.json'),source_identity_sha256=digest({'git_commit':m.get('git_commit','offline-shadow')}),registry_sha256=registry['registry_sha256'],ordered_tasks=m['evaluation']['task_ids'],fixed_initial_state=fixed_state,dynamic_initial_state=dynamic_state)
 prefix=copro_checkpoint.reconcile(ledger_reconciled=_ledger_reconciled(run/'ledger.jsonl'),fixed_current_state=fixed_state);dynamic_state=prefix['dynamic_state']
 try:
  with services(run,run/'ledger.jsonl',run/'progress.jsonl',100,['reme-fixed','reme-dynamic','reme-dynamic-verifier'],lifecycle_input_ceiling=131072) as svc:
   shared=CONSTRUCTION/'reme/shared-bank.jsonl';
   for name in ('reme-fixed','reme-dynamic'): official_post(svc[name].base_url,'load_memory',{'load_file_path':str(shared),'clear_existing':True})
   def dump_fixed(path): official_post(svc['reme-fixed'].base_url,'dump_memory',{'dump_file_path':str(path)})
   fixed_checkpoint=ReMeFixedIntegrityManager(root=run/'reme-fixed-integrity',frozen_semantic_hash=m['banks']['reme_shared_sha256'],dump_current=dump_fixed)
   fixed_marker=fixed_checkpoint.checkpoint(label='initial')
   dynamic_checkpoint=_dynamic_checkpoint(run,m,svc['reme-dynamic'],svc['reme-dynamic-verifier'])
   dynamic_checkpoint.restore_latest()
   for task_position,task in enumerate(m['evaluation']['task_ids'],1):
    if task_position <= int(prefix['completed_task_count']): continue
    guard(m,run,'task'); pre_dynamic_state=json.loads(json.dumps(dynamic_state,sort_keys=True)); copro=[]
    copro_checkpoint.freeze_task_pre_state(task,pre_dynamic_state)
    for trial,seed in enumerate(m['evaluation']['seeds'],1):
     for arm in ARMS:
       path=run/'artifacts'/task/arm/f'trial-{trial}.json';
       holder={}
       retrieval_path=run/'retrievals'/task/f'{arm}-{trial}.json'
       if path.exists():
        result=json.loads(path.read_text(encoding='utf-8'))
        if arm=='official_upstream_reme_dynamic':
         checkpoint_state=dynamic_checkpoint.reconcile(); identity=DynamicUpdateIdentity.from_result(result)
         if _dynamic_order(m).index(identity)>=checkpoint_state['completed_count']:raise RuntimeError('scored ReMe Dynamic artifact lacks a completed durable update marker')
        if arm.startswith('copromem'):
         if not retrieval_path.is_file():raise RuntimeError('completed CoProMem artifact lacks retrieval record')
         holder.update(json.loads(retrieval_path.read_text(encoding='utf-8')))
       else:
        kwargs={};
        if arm.startswith('official_upstream_reme'):kwargs['memory_base_url']=svc['reme-fixed' if arm.endswith('fixed') else 'reme-dynamic'].base_url
        if arm=='official_upstream_reme_dynamic':kwargs.update({'post_score_update':dynamic_checkpoint.callback(path),'post_score_update_strict':True})
        if arm.startswith('copromem'):
         retrieval_state=fixed_state if arm=='copromem_v6_1_fixed' else pre_dynamic_state
         def conditioned_memory(instruction, domain, tool_meta, *, state=retrieval_state, holder=holder):
          query=derive_task_query(instruction,domain,tool_meta,registry); validate_task_query(query,instruction=instruction,public_tool_metadata=tool_meta,callable_registry=registry)
          guidance,prov=retrieval_record(state=state,query_operations=query['query_operations'],registry_sha256=registry['registry_sha256'],task_query=query)
          holder.update({'guidance':guidance,'provenance':prov,'query':query,'state_sha256':digest(state)})
          return guidance
         kwargs['memory_for_instruction']=conditioned_memory
        result=execute_trajectory(run=run,progress=run/'progress.jsonl',ledger=ledger,api_key=k,all_task_ids=m['evaluation']['task_ids'],arm=arm,task_id=task,trial_id=trial,seed=seed,max_actions=30,temperature=.7,phase='evaluation',artifact_path=path,execution_evidence={'registry_path':str(REG.resolve()),'registry_sha256':registry['registry_sha256']},**kwargs)
       if arm.startswith('copromem'):
        if not holder:raise RuntimeError('task-conditioned retrieval callback was not invoked')
        if not retrieval_path.exists():write_json(retrieval_path,{'pre_state_sha256':holder['state_sha256'],'guidance':holder['guidance'],'provenance':holder['provenance'],'task_query':holder['query']})
        if arm=='copromem_v6_1_fixed' and digest(fixed_state)!=m['banks']['copromem_sha256']:raise RuntimeError('CoProMem Fixed state mutated')
       if arm=='copromem_v6_1_dynamic':copro.append(result)
       # The durable public status is refreshed immediately after every
       # artifact, never deferred to the end of a five-arm trial batch.
       summary(run,m)
    if len(copro)!=len(m['evaluation']['seeds']):raise RuntimeError('CoProMem Dynamic batch is incomplete after restart reconciliation')
    retrieval_hashes=[]
    for trial in range(1,len(m['evaluation']['seeds'])+1):
     record=json.loads((run/'retrievals'/task/f'copromem_v6_1_dynamic-{trial}.json').read_text(encoding='utf-8'));retrieval_hashes.append(digest(record))
    copro_checkpoint.record(task,'retrievals_materialized',task_query_hashes=[str(json.loads((run/'retrievals'/task/f'copromem_v6_1_dynamic-{trial}.json').read_text(encoding='utf-8'))['task_query']['query_sha256']) for trial in range(1,len(m['evaluation']['seeds'])+1)],retrieval_hashes=retrieval_hashes)
    copro_checkpoint.record(task,'trajectories_complete',artifact_hashes=[digest(item) for item in copro],scorer_evidence_hashes=[str(item['official_scorer_evidence']['sha256']) for item in copro])
    post,marker,audit=semantic_task_batch_update(artifacts=copro,registry=registry,pre_state=pre_dynamic_state,evidence_paths=[r['execution_evidence_path'] for r in copro],run_root=run)
    copro_checkpoint.record(task,'batch_ready',semantic_projection_hashes=[item['semantic_projection_sha256'] for item in audit['semantic_graph_audits']])
    plan=audit['plan'];validation=audit['validation'];copro_checkpoint.record(task,'semantic_plan_persisted',plan_sha256=plan['plan_sha256']);copro_checkpoint.record(task,'validation_persisted',validation_sha256=digest(validation),validation_passed=bool(validation['passed']))
    copro_checkpoint.record(task,'commit_persisted',marker_sha256=digest(marker),state=marker['state'],winner_schema_id=marker.get('winner_schema_id'))
    copro_checkpoint.snapshot_post_state(task,post,marker_sha256=digest(marker),plan_sha256=plan['plan_sha256'],validation_sha256=digest(validation));copro_checkpoint.record(task,'next_task_authorized',post_state_sha256=digest(post))
    write_json(run/'copromem-dynamic'/task/'update.json',{'pre_state_sha256':digest(pre_dynamic_state),'post_state_sha256':digest(post),'marker':marker,'audit':audit});dynamic_state=post
    if digest(fixed_state)!=m['banks']['copromem_sha256'] or fixed_state is dynamic_state:raise RuntimeError('CoProMem Fixed/Dynamic state isolation violated')
    fixed_marker=fixed_checkpoint.checkpoint(label=f'task-{task_position:04d}',predecessor_checkpoint_sha256=fixed_marker['checkpoint_sha256'])
    summary(run,m)
  summary(run,m,state='completed',final=True);st(run,'completed')
 except BaseException as exc:
  st(run,'failed',failure_class=type(exc).__name__,failure_message=str(exc)[:240])
  ev(run,'runner_failed',failure_class=type(exc).__name__)
  try:summary(run,m,state='failed')
  except Exception:pass
  raise
 finally:
  if lock.exists():lock.unlink()
def main():
 p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','freeze','preflight','run']);p.add_argument('--run',required=True,type=pathlib.Path);a=p.parse_args();a.run=a.run.resolve()
 if a.command=='prepare':prepare(a.run)
 elif a.command=='freeze':freeze(a.run)
 elif a.command=='preflight':load(a.run);st(a.run,'preflight_passed')
 else:run(a.run)
if __name__=='__main__':main()
