#!/usr/bin/env python3
"""No-replay continuation after a provider failure before any new score."""
from __future__ import annotations
import argparse, hashlib, json, shutil
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping
from copromem.contrastive_graph_v6 import digest
from copromem.experiments.reme_copromem.recovery_import import RecoveryImportError
from copromem.experiments.reme_copromem.runner import write_json
from copromem.experiments.reme_copromem.runtime_identity_v3 import build_evaluation_identity_v3
from scripts import run_v61_exploratory_evaluation as base
from scripts import run_v625_safe_terminal_slice_100x3 as overlay

PROTOCOL='v6_2_5_safe_terminal_slice_four_arm_overlay_recovery_004'
ORIGINAL=overlay.REVIEW/'artifacts/research/official_reme_copromem_pilot/v6_2_5_safe_terminal_slice_four_arm_overlay_001'
SOURCE=overlay.REVIEW/'artifacts/research/official_reme_copromem_pilot/v6_2_5_safe_terminal_slice_four_arm_overlay_005_recovery'
CUSTODY='recovery-custody.json'; ADMISSION='recovery-admission.json'; BANK='recovery-initial-bank'
def load(p:Path)->dict[str,Any]:
 try:v=json.loads(p.read_text(encoding='utf-8'))
 except (OSError,json.JSONDecodeError) as e:raise RecoveryImportError(f'unreadable evidence: {p}') from e
 if not isinstance(v,dict):raise RecoveryImportError('evidence is not a JSON object')
 return v
def sha(p:Path)->str:
 if not p.is_file():raise RecoveryImportError(f'evidence missing: {p}')
 return hashlib.sha256(p.read_bytes()).hexdigest()
def canon(v:Any)->str:return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def check_ref(item:Mapping[str,Any], pos:int)->None:
 if item.get('position')!=pos:raise RecoveryImportError('recovery artifact order changed')
 for key in ('artifact','journal','retrieval','binding'):
  path=Path(str(item.get(key,''))); expected=item.get(f'{key}_sha256')
  if sha(path)!=expected:raise RecoveryImportError(f'recovery artifact {key} hash mismatch')
def check_chain(chain:Mapping[str,Any], prior:str)->str:
 if chain.get('pre_state_sha256')!=prior:raise RecoveryImportError('Dynamic checkpoint predecessor mismatch')
 post=Path(str(chain.get('post_state',''))); row=load(post)
 if sha(post)!=chain.get('post_state_file_sha256') or row.get('semantic_state_sha256')!=chain.get('post_state_sha256') or row.get('semantic_state_sha256')!=digest(row.get('state')):raise RecoveryImportError('Dynamic checkpoint post-state mismatch')
 for rec in chain.get('records',[]):
  if sha(Path(str(rec.get('path',''))))!=rec.get('sha256'):raise RecoveryImportError('Dynamic checkpoint record mismatch')
 return str(row['semantic_state_sha256'])
def source()->dict[str,Any]:
 om=load(ORIGINAL/'manifest.json')
 if sha(ORIGINAL/'manifest.json')!=(ORIGINAL/'manifest.sha256').read_text().strip():raise RecoveryImportError('original manifest hash mismatch')
 tasks=list(om.get('evaluation',{}).get('task_ids',())); seeds=list(om.get('evaluation',{}).get('seeds',()))
 if om.get('protocol')!=overlay.PROTOCOL or om.get('arms')!=[overlay.ARM] or len(tasks)!=100 or seeds!=list(overlay.TRIAL_SEEDS):raise RecoveryImportError('wrong original schedule')
 sm=load(SOURCE/'manifest.json'); sc=load(SOURCE/CUSTODY); recorded=sc.pop('custody_sha256',None)
 if recorded!=canon(sc) or sm.get('protocol')!='v6_2_5_safe_terminal_slice_four_arm_overlay_recovery_003' or sm.get('evaluation',{}).get('task_ids')!=tasks[13:] or sc.get('next_task_id')!=tasks[13]:raise RecoveryImportError('source recovery identity/schedule mismatch')
 artifacts=list(sc.get('artifacts',()))
 if len(artifacts)!=38:raise RecoveryImportError('source scored prefix count mismatch')
 for i,item in enumerate(artifacts,1):check_ref(item,i)
 chains=list(sc.get('dynamic_checkpoint_chains',()))
 if len(chains)!=9:raise RecoveryImportError('source Dynamic chain count mismatch')
 prior=str(chains[0].get('pre_state_sha256',''))
 for chain in chains:prior=check_chain(chain,prior)
 if prior!=sc.get('restored_dynamic_state_sha256'):raise RecoveryImportError('source restored bank mismatch')
 if list((SOURCE/'artifacts').rglob('trial-*.json')):raise RecoveryImportError('source unexpectedly contains new scored artifacts')
 task=tasks[13]; tid=f'evaluation:{overlay.ARM}:{task}:trial=1:seed={seeds[0]}'
 journal=SOURCE/'journals'/f'evaluation_{overlay.ARM}_{task}_trial_1_seed_{seeds[0]}.jsonl'; evidence=journal.with_suffix('.execution-evidence.jsonl')
 if not journal.is_file() or not evidence.is_file() or (SOURCE/'artifacts'/task/overlay.ARM/'trial-1.json').exists():raise RecoveryImportError('expected unscored provider failure evidence missing')
 lp=SOURCE/'ledger.jsonl'
 try:ledger=[json.loads(x) for x in lp.read_text().splitlines() if x]
 except (OSError,json.JSONDecodeError) as e:raise RecoveryImportError('source ledger unreadable') from e
 rs={str(x.get('id')) for x in ledger if x.get('event')=='reserve'}; ss={str(x.get('id')) for x in ledger if x.get('event')=='settle'}
 if not rs or rs!=ss:raise RecoveryImportError('source ledger unresolved')
 history=Decimal(str(sc['historical_settled_exposure_usd']))+sum((Decimal(str(x.get('usd',0))) for x in ledger if x.get('event')=='settle'),Decimal('0'))
 excluded={'task_id':task,'arm':overlay.ARM,'failed_trial_id':1,'failed_seed':seeds[0],'skipped_trial_ids':[2,3],'trajectory_id':tid,'journal':str(journal.resolve()),'journal_sha256':sha(journal),'execution_evidence':str(evidence.resolve()),'execution_evidence_sha256':sha(evidence),'reason':'locked provider failure before official scorer/artifact; retry would replay settled calls','provider_calls_replayed':False}
 return {'original_manifest_sha256':sha(ORIGINAL/'manifest.json'),'source_manifest_sha256':sha(SOURCE/'manifest.json'),'source_runtime_identity_sha256':load(SOURCE/'runtime-identity.json')['runtime_identity_sha256'],'source_ledger_sha256':sha(lp),'source_ledger_rows':len(ledger),'historical_exposure':str(history),'artifacts':artifacts,'chains':chains,'state':load(Path(str(chains[-1]['post_state']))),'excluded':excluded,'remaining':tasks[14:]}
def copy_file(src:Path,dst:Path)->None:
 dst.parent.mkdir(parents=True,exist_ok=True)
 if dst.exists() and dst.read_bytes()!=src.read_bytes():raise RecoveryImportError(f'conflicting immutable successor input: {dst}')
 if not dst.exists():shutil.copyfile(src,dst)
def configure(run:Path,src:Mapping[str,Any])->None:
 overlay.configure(run); state=dict(src['state']['state']); rem=list(src['remaining'])
 base.COPRO=run/BANK;base.FROZEN_TASK_IDS=rem;base.ARMS=[overlay.ARM];base.COPRO_DYNAMIC_ARM=overlay.ARM;base.COPRO_FIXED_ARM='copromem_v6_2_5_fixed_unregistered';base.EVALUATION_SEEDS=tuple(overlay.TRIAL_SEEDS);base.CALL_LIMITS={**overlay.CALL_LIMITS,'executor':len(rem)*3*30};base.HARD_CAP_USD=overlay.HARD_CAP_USD;base.HISTORICAL_EXPOSURE=float(Decimal(str(src['historical_exposure'])));base.PROTOCOL=PROTOCOL;base.PREEXISTING_RUN_FILES={overlay.ALLOCATION_NAME,'public-operation-intents.json','external-admission-receipt.json',CUSTODY,BANK};base.identities=lambda:(load(base.CONSTRUCTION/'FINAL_CONSTRUCTION_REPORT.json'),{'state_sha256':digest(state)})
def prepare(run:Path)->None:
 src=source()
 if run.exists() and any(run.iterdir()):raise RecoveryImportError('successor target must be empty')
 run.mkdir(parents=True)
 for n in (overlay.ALLOCATION_NAME,'public-operation-intents.json','external-admission-receipt.json'):copy_file(ORIGINAL/n,run/n)
 c={'version':PROTOCOL,'original_run':str(ORIGINAL.resolve()),'source_run':str(SOURCE.resolve()),'original_manifest_sha256':src['original_manifest_sha256'],'source_manifest_sha256':src['source_manifest_sha256'],'source_runtime_identity_sha256':src['source_runtime_identity_sha256'],'source_ledger_sha256':src['source_ledger_sha256'],'source_ledger_rows':src['source_ledger_rows'],'historical_settled_exposure_usd':src['historical_exposure'],'imported_trajectory_count':38,'imported_task_count':12,'artifacts':src['artifacts'],'dynamic_checkpoint_chains':src['chains'],'restored_dynamic_state_sha256':src['chains'][-1]['post_state_sha256'],'excluded_provider_failure':src['excluded'],'next_task_id':src['remaining'][0],'remaining_task_count':len(src['remaining']),'composite_expected_scored_trajectories':38+len(src['remaining'])*3,'source_immutable':True,'provider_calls_replayed':False};c['custody_sha256']=canon(c);write_json(run/CUSTODY,c)
 b=run/BANK;b.mkdir();write_json(b/'fixed-bank.json',src['state']['state']);write_json(b/'semantic-admission-gate.json',{'state_sha256':c['restored_dynamic_state_sha256']});write_json(b/'recovery-report.json',{'version':PROTOCOL,'custody_sha256':c['custody_sha256']})
 configure(run,src);base.prepare(run);t=load(run/'template.json');t.update({'protocol':PROTOCOL,'method':{'copromem':overlay.POLICY_VERSION,'retrieval':'v6.2.5 admitted retrieval; no-replay continuation after provider failure','analysis_scope':'continuation only; source evidence remains immutable'},'method_policy':overlay.frozen_policy(),'runtime_identity_version':'runtime-content-identity-v3','recovery':{'custody_file_sha256':sha(run/CUSTODY),'source_manifest_sha256':src['source_manifest_sha256'],'source_ledger_sha256':src['source_ledger_sha256'],'imported_trajectory_count':38,'excluded_provider_failure':src['excluded']['trajectory_id'],'remaining_trajectory_count':len(src['remaining'])*3,'restored_dynamic_state_sha256':c['restored_dynamic_state_sha256'],'next_task_id':c['next_task_id']}});t['evaluation'].update({'task_ids':list(src['remaining']),'task_count':len(src['remaining']),'expected_trajectories':len(src['remaining'])*3,'recovery_imported_trajectories':38,'composite_expected_scored_trajectories':c['composite_expected_scored_trajectories'],'allocation_audit_sha256':sha(run/overlay.ALLOCATION_NAME)});t['banks']['copromem_sha256']=c['restored_dynamic_state_sha256'];t['budget'].update({'historical_settled_exposure':float(Decimal(src['historical_exposure'])),'hard_cap_usd':overlay.HARD_CAP_USD,'call_limits':dict(base.CALL_LIMITS)});t['execution'].update({'provider_only':overlay.CHAT_PROVIDER,'call_limits':dict(base.CALL_LIMITS)});r,inputs=build_evaluation_identity_v3(root=overlay.ROOT,manifest=t);write_json(run/'runtime-identity.json',r);write_json(run/'runtime-identity.binding.json',{'runtime_identity_sha256':r['runtime_identity_sha256'],'runtime_identity_record_sha256':sha(run/'runtime-identity.json')});t['runtime_identity_inputs']=inputs;t['runtime_identity_sha256']=r['runtime_identity_sha256'];t['runtime_identity_file_sha256']=sha(run/'runtime-identity.json');write_json(run/'template.json',t)
def verify(run:Path)->dict[str,Any]:
 src=source();c=load(run/CUSTODY);got=c.pop('custody_sha256',None)
 if got!=canon(c) or c.get('source_ledger_sha256')!=src['source_ledger_sha256'] or c.get('artifacts')!=src['artifacts'] or c.get('dynamic_checkpoint_chains')!=src['chains'] or c.get('excluded_provider_failure')!=src['excluded'] or c.get('next_task_id')!=src['remaining'][0]:raise RecoveryImportError('recovery custody differs from immutable source')
 if digest(load(run/BANK/'fixed-bank.json'))!=src['chains'][-1]['post_state_sha256']:raise RecoveryImportError('successor bank differs from last complete Dynamic state')
 return src
def freeze(run:Path)->None:src=verify(run);configure(run,src);base.freeze(run)
def preflight(run:Path)->None:
 src=verify(run);configure(run,src);m=base.load(run)
 if m['evaluation']['task_ids']!=src['remaining']:raise RecoveryImportError('successor schedule differs from frozen suffix')
 route=overlay.verify_locked_chat_route_available()
 if route.get('provider')!=overlay.CHAT_PROVIDER:raise RecoveryImportError('provider route changed')
 write_json(run/'provider-route-preflight.json',route);write_json(run/ADMISSION,{'version':PROTOCOL,'custody_file_sha256':sha(run/CUSTODY),'source_ledger_sha256':src['source_ledger_sha256'],'imported_trajectory_count':38,'excluded_provider_failure':src['excluded']['trajectory_id'],'next_task_id':src['remaining'][0],'provider_calls_replayed':False});base.st(run,'preflight_passed',imported_completed_trajectories=38,next_task_id=src['remaining'][0])
def run(run:Path)->None:src=verify(run);configure(run,src);preflight(run);base.run(run)
def main()->None:
 p=argparse.ArgumentParser();p.add_argument('command',choices=('prepare','freeze','preflight','run'));p.add_argument('--run',required=True,type=Path);a=p.parse_args();{'prepare':prepare,'freeze':freeze,'preflight':preflight,'run':run}[a.command](a.run.resolve())
if __name__=='__main__':main()