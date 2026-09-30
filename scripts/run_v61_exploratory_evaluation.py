#!/usr/bin/env python3
"""Standalone five-arm, exploratory-only v6.1 evaluation successor."""
from __future__ import annotations
import argparse, hashlib, json, os, pathlib, sys, time
ROOT=pathlib.Path(__file__).resolve().parents[1]; sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from copromem.contrastive_graph_v6 import digest
from copromem.experiments.reme_copromem.contrastive_v6_runner import retrieval_record, semantic_task_batch_update, scorer_evidence_sha256
from copromem.experiments.reme_copromem.task_query import derive_task_query, validate_task_query
from copromem.experiments.reme_copromem.runner import AppendOnlyLedger, execute_trajectory, official_post, services, v5_budget_bound, write_json, append
from copromem.integrations.reme.dynamic_checkpoint import DynamicUpdateIdentity, ReMeDynamicCheckpointManager
from copromem.experiments.reme_copromem.evidence_contract import validate as validate_execution_evidence
from copromem.experiments.reme_copromem.live_summary import build_live_summary, write_live_summary
from copromem.experiments.reme_copromem.live_summary import reconcile_ledger
from copromem.experiments.reme_copromem.copromem_dynamic_checkpoint import CoProMemDynamicCheckpointManager
from copromem.integrations.reme.fixed_checkpoint import ReMeFixedIntegrityManager
from copromem.experiments.reme_copromem.runtime_identity import apply_runtime_locators, build_evaluation_runtime_identity, verify_runtime_identity, evaluation_runtime_inputs
from copromem.experiments.reme_copromem.runtime_identity_v3 import IDENTITY_VERSION as RUNTIME_IDENTITY_V3, verify_manifest_identity as verify_runtime_identity_v3
from copromem.experiments.reme_copromem.terminal_reconciliation import validate_terminal_run
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
# Maintained configuration seams for separately frozen successors.  Historical
# entry points retain these defaults; a dedicated successor wrapper may set
# them before calling any lifecycle or task boundary.
EVALUATION_SPLIT='dev'
HARD_CAP_USD=100
CALL_LIMITS={'executor':1800,'reme_lifecycle':256,'reme_embedding':1024,'copromem_decomposition':0}
LIFECYCLE_INPUT_CEILING=131072
COPRO_FIXED_ARM='copromem_v6_1_fixed'
COPRO_DYNAMIC_ARM='copromem_v6_1_dynamic'
TASK_MAJOR_ARM_FIRST=False
PREEXISTING_RUN_FILES=set()
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
 if m.get('runtime_identity_version')==RUNTIME_IDENTITY_V3:
  inputs=m.get('runtime_identity_inputs')
  if not isinstance(inputs,dict):raise RuntimeError('v3 manifest runtime identity inputs are absent')
  try:
   verify_runtime_identity_v3(m,record,root=ROOT,runtime_configuration=inputs['runtime_configuration'],external_dependencies=inputs['external_dependencies'],scientific_inputs=inputs['scientific_inputs'])
  except (KeyError, TypeError) as exc:raise RuntimeError('v3 manifest runtime identity inputs are invalid') from exc
  if file_sha(record_path)!=m.get('runtime_identity_file_sha256'):raise RuntimeError('manifest-bound v3 runtime identity file mismatch')
  return record
 content,trees,labels=evaluation_runtime_inputs(root=ROOT,source_commit=m['git_commit'])
 verify_runtime_identity(record,content=content,trees=trees,labels=labels)
 if file_sha(record_path)!=m.get('runtime_identity_file_sha256') or record.get('runtime_identity_sha256')!=m.get('runtime_identity_sha256'):raise RuntimeError('manifest-bound runtime identity mismatch')
 return record
def _runtime_checkpoint(run,m,stage):
 """Recompute the content identity at every dispatch-capable boundary."""
 record=_runtime_identity(run,m)
 body={'version':'v6.2-runtime-verification-v1','stage':str(stage),'manifest_sha256':file_sha(run/'manifest.json'),'runtime_identity_sha256':record['runtime_identity_sha256'],'runtime_identity_file_sha256':file_sha(run/'runtime-identity.json')}
 body['checkpoint_sha256']=digest(body)
 path=run/'runtime-verifications'/f'{str(stage).replace("/","_")}.json'
 if path.exists():
  if json.loads(path.read_text(encoding='utf-8'))!=body:raise RuntimeError('runtime verification checkpoint conflict')
 else:write_json(path,body)
 return path,body
def _inventory_hash(root):
 """Hash file identities, never their (potentially sensitive) contents in logs."""
 if not root.exists():return digest([])
 return digest([{'path':str(path.relative_to(root.parent)).replace('\\','/'),'sha256':file_sha(path)} for path in sorted(root.rglob('*')) if path.is_file()])
def _validate_terminal_retrieval_inventory(run,m):
 """Ensure every CoProMem evidence-bearing trajectory retained its query record."""
 for task in m['evaluation']['task_ids']:
  for trial in range(1,len(m['evaluation']['seeds'])+1):
   for arm in (COPRO_FIXED_ARM,COPRO_DYNAMIC_ARM):
    path=run/'retrievals'/task/f'{arm}-{trial}.json'
    if not path.is_file():raise RuntimeError(f'missing terminal retrieval record: {task}/{arm}/{trial}')
    record=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(record.get('task_query'),dict) or not record['task_query'].get('query_sha256'):
     raise RuntimeError(f'invalid terminal retrieval query: {task}/{arm}/{trial}')
def _write_final_reports(run,manifest,marker,marker_file_sha256):
 marker_path=run/'copromem-dynamic-checkpoints'/'run-reconciled.json'
 if not marker_path.is_file() or file_sha(marker_path)!=marker_file_sha256:raise RuntimeError('final report requires valid run_reconciled marker')
 summary_path=run/'live-summary.json'
 report={'version':'v6.2-terminal-report-v1','manifest_sha256':file_sha(run/'manifest.json'),'run_reconciled_sha256':marker['record_sha256'],'run_reconciled_file_sha256':marker_file_sha256,'live_summary_sha256':file_sha(summary_path),'exploratory_diagnostic_only':True,'expected_trajectories':manifest['evaluation']['expected_trajectories']}
 write_json(run/'final-report.json',report)
 (run/'FINAL_REPORT.md').write_text('# Exploratory diagnostic evaluation\n\nThis report is bound to `run_reconciled`; it is not an efficacy claim.\n',encoding='utf-8')
 return report
def _completed_run_is_valid(run,m):
 """A completed run is terminal and read-only; never relaunch its services."""
 status_path=run/'runner-status.json'; marker_path=run/'copromem-dynamic-checkpoints'/'run-reconciled.json'; report_path=run/'final-report.json'
 if not status_path.is_file() or json.loads(status_path.read_text(encoding='utf-8')).get('state')!='completed':return False
 if not marker_path.is_file() or not report_path.is_file():raise RuntimeError('completed status lacks terminal marker or report')
 marker=json.loads(marker_path.read_text(encoding='utf-8')); semantic=dict(marker); recorded=semantic.pop('record_sha256',None); semantic.pop('nonsemantic_metadata',None)
 if recorded!=digest(semantic) or marker.get('manifest_sha256')!=file_sha(run/'manifest.json'):raise RuntimeError('completed run_reconciled marker is invalid')
 report=json.loads(report_path.read_text(encoding='utf-8'))
 if report.get('run_reconciled_sha256')!=recorded or report.get('run_reconciled_file_sha256')!=file_sha(marker_path):raise RuntimeError('completed final report is not bound to run_reconciled')
 return True
def _terminalize(run,m,copro_checkpoint,dynamic_checkpoint,fixed_checkpoint,owned_services):
 """Read-only reconciliation, then the only path to completed status."""
 _runtime_checkpoint(run,m,'terminal')
 summary(run,m,state='reconciling',final=True);st(run,'reconciling',manifest_sha256=file_sha(run/'manifest.json'))
 report=validate_terminal_run(run_root=run,manifest=m,runtime_verify=lambda:_runtime_identity(run,m),copro_reconcile=lambda:copro_checkpoint.reconcile(ledger_reconciled=_ledger_reconciled(run/'ledger.jsonl'),fixed_current_state=copro_checkpoint.fixed_initial_state),reme_dynamic_reconcile=dynamic_checkpoint.reconcile,reme_fixed_reconcile=fixed_checkpoint.reconcile,active_processes=lambda:any(getattr(item,'proc',None) is not None and item.proc.poll() is None for item in owned_services.values()),historical_exposure=HISTORICAL_EXPOSURE,additional_checks={'task_query_and_retrieval_inventory':lambda:_validate_terminal_retrieval_inventory(run,m)})
 write_json(run/'terminal-reconciliation.json',report)
 if not report['valid']:raise RuntimeError('terminal reconciliation failed: '+json.dumps(report['failures'],sort_keys=True))
 runtime_path,_=_runtime_checkpoint(run,m,'terminal')
 marker=copro_checkpoint.record_run_reconciled(manifest_sha256=file_sha(run/'manifest.json'),source_commit=m['git_commit'],runtime_identity_file_sha256=file_sha(run/'runtime-identity.json'),runtime_verification_file_sha256=file_sha(runtime_path),scored_artifact_inventory_sha256=_inventory_hash(run/'artifacts'),evidence_inventory_sha256=digest({'journals':_inventory_hash(run/'journals'),'scorer':_inventory_hash(run/'scorer')}),task_query_retrieval_inventory_sha256=_inventory_hash(run/'retrievals'),copromem_fixed_state_sha256=m['banks']['copromem_sha256'],copromem_dynamic_terminal_state_sha256=digest(copro_checkpoint.reconcile(ledger_reconciled=True,fixed_current_state=copro_checkpoint.fixed_initial_state)['dynamic_state']),reme_dynamic_checkpoint_chain_sha256=_inventory_hash(run/'reme-dynamic-checkpoints'),reme_fixed_checkpoint_chain_sha256=_inventory_hash(run/'reme-fixed-integrity'),ledger_sha256=file_sha(run/'ledger.jsonl'),live_summary_sha256=file_sha(run/'live-summary.json'),terminal_reconciliation_sha256=file_sha(run/'terminal-reconciliation.json'),expected_trajectories=m['evaluation']['expected_trajectories'],nonsemantic_metadata={'finalizer_pid':os.getpid()})
 _write_final_reports(run,m,marker,file_sha(copro_checkpoint.run_reconciled_path))
 st(run,'completed',manifest_sha256=file_sha(run/'manifest.json'),run_reconciled_sha256=marker['record_sha256'])
 return marker
def prepare(run):
 if run.exists() and any(path.name not in PREEXISTING_RUN_FILES for path in run.iterdir()):raise RuntimeError('run nonempty')
 apply_runtime_locators(ROOT)
 report,gate=identities(); run.mkdir(parents=True,exist_ok=True)
 limits=dict(CALL_LIMITS); budget=v5_budget_bound(call_limits=limits,historical_usd=HISTORICAL_EXPOSURE,lifecycle_input_ceiling=LIFECYCLE_INPUT_CEILING)
 if budget['all_in_usd']>HARD_CAP_USD:raise RuntimeError(f'budget exceeds USD {HARD_CAP_USD:g}')
 commit=source_commit();runtime=build_evaluation_runtime_identity(root=ROOT,source_commit=commit);write_json(run/'runtime-identity.json',runtime)
 m={'protocol':PROTOCOL,'exploratory_diagnostic_only':True,'predecessor_evaluation_002_excluded':True,'predecessor_evaluation_004_excluded':True,'predecessor_evaluation_005_excluded':True,'git_commit':commit,'runtime_identity_sha256':runtime['runtime_identity_sha256'],'runtime_identity_file_sha256':file_sha(run/'runtime-identity.json'),'arms':ARMS,'evaluation':{'split':EVALUATION_SPLIT,'task_ids':FROZEN_TASK_IDS,'seeds':[11001,11002],'stochastic_trial_ids':[11001,11002],'provider_seed':None,'trial_semantics':'ordered_stochastic_labels_not_provider_seeds','expected_trajectories':len(FROZEN_TASK_IDS)*len([11001,11002])*len(ARMS)},'banks':{'reme_shared_sha256':report['shared_bank_sha256'],'copromem_sha256':gate['state_sha256']},'storage_policy':{'launch_floor_gib':5,'warning_gib':4,'mandatory_stop_gib':3},'execution':{'model':'deepseek/deepseek-v4.1-flash','provider_only':'deepseek','temperature':.7,'top_p':1.0,'max_actions':30,'completion_token_ceiling':2048,'context_token_ceiling':32768},'budget':{**budget,'hard_cap_usd':HARD_CAP_USD,'call_limits':limits,'historical_settled_exposure':HISTORICAL_EXPOSURE,'evaluation_004_unresolved_retained_usd':0.0060078,'evaluation_005_unresolved_retained_usd':0.005946},'scientific_protocol_unchanged':True,'clean_restart_from_original_initial_banks':True}
 write_json(run/'template.json',m)
def freeze(run):
 apply_runtime_locators(ROOT)
 m=json.loads((run/'template.json').read_text());
 if m['git_commit']!=source_commit():raise RuntimeError('source changed')
 _runtime_identity(run,m)
 write_json(run/'manifest.json',m)
 (run/'manifest.sha256').write_text(file_sha(run/'manifest.json')+'\n')
def load(run):
 apply_runtime_locators(ROOT)
 if file_sha(run/'manifest.json')!=(run/'manifest.sha256').read_text().strip():raise RuntimeError('manifest mismatch')
 m=json.loads((run/'manifest.json').read_text());
 _runtime_identity(run,m)
 if c_free_gib()<5:raise RuntimeError('C launch floor')
 identities()
 return m
def summary(run,m,*,state='running',final=False):
 out=build_live_summary(ledger_path=run/'ledger.jsonl',artifact_root=run/'artifacts',expected_tasks=m['evaluation']['task_ids'],expected_seeds=m['evaluation']['seeds'],historical_expected_usd=HISTORICAL_EXPOSURE,state=state,final=final,expected_trajectories=m['evaluation']['expected_trajectories'],registered_arms=m['arms'])
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
 return not reconcile_ledger(path,historical_expected_usd=HISTORICAL_EXPOSURE,registered_arms=ARMS).unresolved_reservation_ids
def run(run):
 m=load(run); lock=run/'runner.lock';
 if _completed_run_is_valid(run,m):return
 if lock.exists():raise RuntimeError('duplicate runner')
 write_json(lock,{'pid':os.getpid()})
 ledger=AppendOnlyLedger(run/'ledger.jsonl',HARD_CAP_USD,m['budget']['call_limits']);
 if not _has_ledger_reservation(run/'ledger.jsonl','historical-construction-carry'):
  ledger.reserve('historical-construction-carry',HISTORICAL_EXPOSURE,{'role':'historical_carry_forward'});ledger.settle('historical-construction-carry',HISTORICAL_EXPOSURE,{'role':'historical_carry_forward'})
 _runtime_checkpoint(run,m,'startup');k=key();st(run,'running',manifest_sha256=file_sha(run/'manifest.json')); fixed_state=json.loads((COPRO/'fixed-bank.json').read_text()); dynamic_state=json.loads(json.dumps(fixed_state,sort_keys=True)); registry=json.loads(REG.read_text())
 if digest(fixed_state)!=digest(dynamic_state) or fixed_state is dynamic_state:raise RuntimeError('CoProMem Fixed/Dynamic initial state isolation failed')
 write_json(run/'copromem-state-identities.json',{'fixed_initial_sha256':digest(fixed_state),'dynamic_initial_sha256':digest(dynamic_state),'non_aliased':True})
 copro_checkpoint=CoProMemDynamicCheckpointManager(root=run/'copromem-dynamic-checkpoints',manifest_sha256=file_sha(run/'manifest.json'),source_identity_sha256=digest({'git_commit':m.get('git_commit','offline-shadow')}),registry_sha256=registry['registry_sha256'],ordered_tasks=m['evaluation']['task_ids'],fixed_initial_state=fixed_state,dynamic_initial_state=dynamic_state)
 prefix=copro_checkpoint.reconcile(ledger_reconciled=_ledger_reconciled(run/'ledger.jsonl'),fixed_current_state=fixed_state);dynamic_state=prefix['dynamic_state']
 owned_services={}
 try:
  with services(run,run/'ledger.jsonl',run/'progress.jsonl',HARD_CAP_USD,['reme-fixed','reme-dynamic','reme-dynamic-verifier'],lifecycle_input_ceiling=LIFECYCLE_INPUT_CEILING) as svc:
   owned_services=svc
   shared=CONSTRUCTION/'reme/shared-bank.jsonl';
   for name in ('reme-fixed','reme-dynamic'): official_post(svc[name].base_url,'load_memory',{'load_file_path':str(shared),'clear_existing':True})
   def dump_fixed(path): official_post(svc['reme-fixed'].base_url,'dump_memory',{'dump_file_path':str(path)})
   fixed_checkpoint=ReMeFixedIntegrityManager(root=run/'reme-fixed-integrity',frozen_semantic_hash=m['banks']['reme_shared_sha256'],dump_current=dump_fixed)
   fixed_marker=fixed_checkpoint.checkpoint(label='initial')
   dynamic_checkpoint=_dynamic_checkpoint(run,m,svc['reme-dynamic'],svc['reme-dynamic-verifier'])
   dynamic_checkpoint.restore_latest()
   for task_position,task in enumerate(m['evaluation']['task_ids'],1):
    if task_position <= int(prefix['completed_task_count']): continue
    _runtime_checkpoint(run,m,f'task-{task_position:04d}-before-open')
    guard(m,run,'task'); pre_dynamic_state=json.loads(json.dumps(dynamic_state,sort_keys=True)); copro=[]
    copro_checkpoint.freeze_task_pre_state(task,pre_dynamic_state)
    ordered_units = ([(arm,trial,seed) for arm in ARMS for trial,seed in enumerate(m['evaluation']['seeds'],1)]
                     if TASK_MAJOR_ARM_FIRST else
                     [(arm,trial,seed) for trial,seed in enumerate(m['evaluation']['seeds'],1) for arm in ARMS])
    for arm,trial,seed in ordered_units:
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
        _runtime_checkpoint(run,m,f'dispatch-{task_position:04d}-{trial:02d}-{arm}')
        kwargs={};
        if arm.startswith('official_upstream_reme'):kwargs['memory_base_url']=svc['reme-fixed' if arm.endswith('fixed') else 'reme-dynamic'].base_url
        if arm=='official_upstream_reme_dynamic':kwargs.update({'post_score_update':dynamic_checkpoint.callback(path),'post_score_update_strict':True})
        if arm.startswith('copromem'):
         retrieval_state=fixed_state if arm==COPRO_FIXED_ARM else pre_dynamic_state
         def conditioned_memory(instruction, domain, tool_meta, *, state=retrieval_state, holder=holder):
          query=derive_task_query(instruction,domain,tool_meta,registry); validate_task_query(query,instruction=instruction,public_tool_metadata=tool_meta,callable_registry=registry)
          guidance,prov=retrieval_record(state=state,query_operations=query['query_operations'],registry_sha256=registry['registry_sha256'],task_query=query,callable_registry=registry)
          holder.update({'guidance':guidance,'provenance':prov,'query':query,'state_sha256':digest(state)})
          return guidance
         kwargs['memory_for_instruction']=conditioned_memory
        result=execute_trajectory(run=run,progress=run/'progress.jsonl',ledger=ledger,api_key=k,all_task_ids=m['evaluation']['task_ids'],arm=arm,task_id=task,trial_id=trial,seed=seed,max_actions=30,temperature=.7,phase='evaluation',artifact_path=path,execution_evidence={'registry_path':str(REG.resolve()),'registry_sha256':registry['registry_sha256']},**kwargs)
        # The artifact is the only admissible boundary between execution and a
        # task-batch state transition.  Reload it so a zero-action evidence
        # attestation and every scorer binding are interpreted identically on
        # first execution and restart.
        if not path.is_file(): raise RuntimeError('executor returned without a durable scored artifact')
        result=json.loads(path.read_text(encoding='utf-8'))
       if arm.startswith('copromem'):
        if not holder:raise RuntimeError('task-conditioned retrieval callback was not invoked')
        retrieval_payload={'pre_state_sha256':holder['state_sha256'],'guidance':holder['guidance'],'provenance':holder['provenance'],'task_query':holder['query'],
                          'copromem_callback_guidance_sha256':digest(holder['guidance']),'copromem_callback_guidance_nonempty':bool(holder['guidance']),
                          'prompt_injection_sha256':result.get('prompt_memory_injection_sha256',digest(holder['guidance'])),
                          'initial_prompt_messages_sha256':result.get('initial_prompt_messages_sha256')}
        if not retrieval_path.exists():write_json(retrieval_path,retrieval_payload)
        # The executor persists its scorer-bound artifact before this point.
        # Add only deterministic retrieval identities; this does not alter its
        # history, score, native actions, or model-visible prompt.
        result.update({'copromem_retrieval_record_sha256':digest(retrieval_payload),
                       'copromem_callback_guidance_sha256':digest(holder['guidance']),
                       'copromem_callback_guidance_nonempty':bool(holder['guidance']),
                       'prompt_memory_injection_sha256':result.get('prompt_memory_injection_sha256',digest(holder['guidance']))})
        write_json(path,result)
        if arm==COPRO_FIXED_ARM and digest(fixed_state)!=m['banks']['copromem_sha256']:raise RuntimeError('CoProMem Fixed state mutated')
       if arm==COPRO_DYNAMIC_ARM:copro.append(result)
       # The durable public status is refreshed immediately after every
       # artifact, never deferred to the end of a five-arm trial batch.
       summary(run,m)
    if len(copro)!=len(m['evaluation']['seeds']):raise RuntimeError('CoProMem Dynamic batch is incomplete after restart reconciliation')
    retrieval_hashes=[]
    for trial in range(1,len(m['evaluation']['seeds'])+1):
     record=json.loads((run/'retrievals'/task/f'{COPRO_DYNAMIC_ARM}-{trial}.json').read_text(encoding='utf-8'));retrieval_hashes.append(digest(record))
    copro_checkpoint.record(task,'retrievals_materialized',task_query_hashes=[str(json.loads((run/'retrievals'/task/f'{COPRO_DYNAMIC_ARM}-{trial}.json').read_text(encoding='utf-8'))['task_query']['query_sha256']) for trial in range(1,len(m['evaluation']['seeds'])+1)],retrieval_hashes=retrieval_hashes)
    copro_checkpoint.record(task,'trajectories_complete',artifact_hashes=[digest(item) for item in copro],scorer_evidence_hashes=[scorer_evidence_sha256(item) for item in copro])
    post,marker,audit=semantic_task_batch_update(artifacts=copro,registry=registry,pre_state=pre_dynamic_state,evidence_paths=[r['execution_evidence_path'] for r in copro],run_root=run)
    copro_checkpoint.record(task,'batch_ready',semantic_projection_hashes=[item['semantic_projection_sha256'] for item in audit['semantic_graph_audits']])
    plan=audit['plan'];validation=audit['validation'];copro_checkpoint.record(task,'semantic_plan_persisted',plan_sha256=plan['plan_sha256']);copro_checkpoint.record(task,'validation_persisted',validation_sha256=digest(validation),validation_passed=bool(validation['passed']))
    copro_checkpoint.record(task,'commit_persisted',marker_sha256=digest(marker),state=marker['state'],winner_schema_id=marker.get('winner_schema_id'))
    copro_checkpoint.snapshot_post_state(task,post,marker_sha256=digest(marker),plan_sha256=plan['plan_sha256'],validation_sha256=digest(validation));copro_checkpoint.record(task,'next_task_authorized',post_state_sha256=digest(post))
    write_json(run/'copromem-dynamic'/task/'update.json',{'pre_state_sha256':digest(pre_dynamic_state),'post_state_sha256':digest(post),'marker':marker,'audit':audit});dynamic_state=post
    if digest(fixed_state)!=m['banks']['copromem_sha256'] or fixed_state is dynamic_state:raise RuntimeError('CoProMem Fixed/Dynamic state isolation violated')
    fixed_marker=fixed_checkpoint.checkpoint(label=f'task-{task_position:04d}',predecessor_checkpoint_sha256=fixed_marker['checkpoint_sha256'])
    summary(run,m)
  _terminalize(run,m,copro_checkpoint,dynamic_checkpoint,fixed_checkpoint,owned_services)
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
