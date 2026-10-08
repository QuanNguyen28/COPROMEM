#!/usr/bin/env python3
"""No-replay recovery successor for a v6.2.7 multi-schema 100x3 prefix."""
from __future__ import annotations
import argparse, hashlib, json, math, os
from pathlib import Path
import sys
from typing import Any, Mapping
ROOT=Path(__file__).resolve().parents[1]; sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from copromem.experiments.reme_copromem.v627_semantic_update import semantic_spine_task_batch_update_v627 as semantic_spine_task_batch_update
from copromem.experiments.reme_copromem.public_operation_intent_registry import build as build_intents, verify as verify_intents
from copromem.experiments.reme_copromem.runner import write_json
from copromem.experiments.reme_copromem.runtime_identity_v3 import IDENTITY_VERSION as RUNTIME_IDENTITY_V3, build_evaluation_identity_v3
from copromem.experiments.reme_copromem.schema_multi_admission import verify as verify_bundle
from copromem.experiments.reme_copromem.task_conditioned_retrieval_v627 import POLICY_VERSION, derive_task_query, frozen_policy, reproduce_retrieval, retrieve, validate_task_query
from copromem.integrations.reme.transport import PROVIDER as CHAT_PROVIDER, verify_locked_chat_route_available
from scripts import run_v61_exploratory_evaluation as base
from scripts.v626_copromem_only_runtime import install as install_copromem_only_runtime
PROTOCOL='v6_2_7_multi_schema_100x3_recovery_001'; ARM='copromem_v6_2_7_dynamic'; ARMS=[ARM]; TRIAL_SEEDS=(11001,11002,11003); TASK_COUNT=100; HARD_CAP_USD=140.0; ALLOCATION_NAME='allocation-audit-v627-multi-schema-100x3.json'
REVIEW=Path(os.environ.get('COPROMEM_REVIEW_ROOT','/mnt/e/Project/AAMAS/COPROMEM-review')); _BANK: Path|None=None

def sha(v:Any)->str:return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def fsha(p:Path)->str:
 if not p.is_file():raise RuntimeError(f'missing immutable file: {p}')
 return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p:Path)->dict[str,Any]:
 v=json.loads(p.read_text(encoding='utf-8'))
 if not isinstance(v,dict):raise RuntimeError(f'expected object: {p}')
 return v
def bank_audit(bank:Path)->dict[str,Any]:
 state,gate=read(bank/'fixed-bank.json'),read(bank/'semantic-admission-gate.json')
 if gate.get('version')!='copromem-v6.2.7-seed-bank-promotion-v1' or gate.get('passed') is not True or gate.get('provider_calls')!=0 or gate.get('state_sha256')!=sha(state) or gate.get('recovery_report_sha256')!=fsha(bank/'recovery-report.json'):raise RuntimeError('v627 seed bank custody invalid')
 return {'path':str(bank.resolve()),'fixed_bank_file_sha256':fsha(bank/'fixed-bank.json'),'admission_gate_file_sha256':fsha(bank/'semantic-admission-gate.json'),'recovery_report_file_sha256':fsha(bank/'recovery-report.json'),'semantic_state_sha256':sha(state)}
def identities()->tuple[dict[str,Any],dict[str,Any]]:
 if _BANK is None:raise RuntimeError('bank not configured')
 report=read(base.CONSTRUCTION/'FINAL_CONSTRUCTION_REPORT.json')
 if report.get('shared_bank_sha256')!='6c3bc799ec0beb034fd2b81ee0d5cbf6e89a14f3a5a39ebf70d34853686b00a0':raise RuntimeError('shared construction drift')
 _=bank_audit(_BANK); return report,read(_BANK/'semantic-admission-gate.json')
def openapi()->Path:
 root=Path(os.environ.get('COPROMEM_APPWORLD_ROOT') or os.environ.get('APPWORLD_ROOT') or '')/'data/api_docs/openapi'
 if not root.is_dir():raise RuntimeError('native AppWorld OpenAPI root absent')
 return root

def allocate(run:Path, source:Path, four:Path, bank:Path, bundle:Path)->None:
 if run.exists() and any(run.iterdir()):raise RuntimeError('allocation target must be empty')
 source_v,four_v,bundle_v=read(source),read(four),read(bundle); tasks=list(source_v.get('evaluation',{}).get('task_ids',()))
 selected=list(four_v.get('selected_task_ids',()))
 if len(tasks)!=TASK_COUNT or len(set(tasks))!=TASK_COUNT or tasks!=selected or four_v.get('version')!='v6.2.2-real-pilot-public-allocation-v1' or four_v.get('selected_task_ids_sha256')!=sha(selected):raise RuntimeError('E074 exact 100-task grid differs')
 state=read(bank/'fixed-bank.json'); schemas=__import__('copromem.experiments.reme_copromem.task_conditioned_retrieval_v627',fromlist=['base']).base._schema_rows(state)
 verify_bundle(bundle_v,policy_sha256=frozen_policy()['policy_sha256'],schemas=schemas)
 audit={'version':'v6.2.7-multi-schema-four-arm-overlay-allocation-v1','protocol':PROTOCOL,'phase':'four_arm_overlay','payloads_opened':False,'selected_task_ids':selected,'selected_task_ids_sha256':sha(selected),'split':str(source_v.get('evaluation',{}).get('split') or 'test_normal'),'trial_seeds':list(TRIAL_SEEDS),'arms':ARMS,'source_manifest_path':str(source.resolve()),'source_manifest_sha256':fsha(source),'four_arm_allocation_path':str(four.resolve()),'four_arm_allocation_sha256':fsha(four),'four_arm_selected_task_ids_sha256':four_v['selected_task_ids_sha256'],'copromem_bank':bank_audit(bank),'multi_schema_admission_file_sha256':fsha(bundle),'multi_schema_admission_sha256':bundle_v['bundle_sha256'],'historical_settled_exposure_usd':0.0,'cost_scope':'new v627 Dynamic overlay calls only; E074 historical costs separate'}
 run.mkdir(parents=True,exist_ok=False);write_json(run/ALLOCATION_NAME,audit);(run/'schema-multi-admission.json').write_bytes(bundle.read_bytes())
def audit(run:Path)->dict[str,Any]:
 a=read(run/ALLOCATION_NAME);tasks=a.get('selected_task_ids')
 if a.get('version')!='v6.2.7-multi-schema-four-arm-overlay-allocation-v1' or a.get('protocol')!=PROTOCOL or a.get('phase')!='four_arm_overlay' or a.get('payloads_opened') is not False or a.get('arms')!=ARMS or a.get('trial_seeds')!=list(TRIAL_SEEDS) or not isinstance(tasks,list) or len(tasks)!=TASK_COUNT or len(set(tasks))!=TASK_COUNT or a.get('selected_task_ids_sha256')!=sha(tasks):raise RuntimeError('pilot allocation invalid')
 source,four=Path(str(a.get('source_manifest_path')or'')),Path(str(a.get('four_arm_allocation_path')or''))
 if fsha(source)!=a.get('source_manifest_sha256') or fsha(four)!=a.get('four_arm_allocation_sha256'):raise RuntimeError('pilot source identity differs')
 if list(read(source).get('evaluation',{}).get('task_ids',()))!=tasks or list(read(four).get('selected_task_ids',()))!=tasks:raise RuntimeError('pilot grid differs')
 bank=Path(str(a.get('copromem_bank',{}).get('path')or''));
 if a.get('copromem_bank')!=bank_audit(bank):raise RuntimeError('pilot bank differs')
 bpath=run/'schema-multi-admission.json';bundle=read(bpath);state=read(bank/'fixed-bank.json');schemas=__import__('copromem.experiments.reme_copromem.task_conditioned_retrieval_v627',fromlist=['base']).base._schema_rows(state)
 if fsha(bpath)!=a.get('multi_schema_admission_file_sha256') or bundle.get('bundle_sha256')!=a.get('multi_schema_admission_sha256'):raise RuntimeError('bundle binding differs')
 verify_bundle(bundle,policy_sha256=frozen_policy()['policy_sha256'],schemas=schemas)
 if not math.isfinite(float(a.get('historical_settled_exposure_usd',-1))) or float(a['historical_settled_exposure_usd'])!=0:raise RuntimeError('cost boundary invalid')
 return a
def retrieval_record(*,state:Mapping[str,Any],query_operations:list[str],registry_sha256:str,task_query:Mapping[str,Any]|None=None,callable_registry:Mapping[str,Any]|None=None)->tuple[str,dict[str,Any]]:
 if callable_registry is None or task_query is None or registry_sha256!=callable_registry.get('registry_sha256') or list(query_operations)!=list(task_query.get('canonical_query_operations',())):raise RuntimeError('retrieval authority mismatch')
 bundle=read(Path(getattr(retrieval_record,'bundle_path','')));return retrieve(state,task_query,callable_registry,bundle)
SOURCE: Path|None=None
CUSTODY='recovery-custody.json'; RECOVERY_BANK='recovery-bank'
def source_state(source:Path, continuation:Path|None=None)->dict[str,Any]:
 m=read(source/'manifest.json'); tasks=list(m.get('evaluation',{}).get('task_ids',()))
 if len(tasks)!=100 or list(m.get('evaluation',{}).get('seeds',()))!=list(TRIAL_SEEDS): raise RuntimeError('source schedule differs')
 ledger=source/'ledger.jsonl'; rows=[json.loads(x) for x in ledger.read_text(encoding='utf-8').splitlines() if x]
 reserved={str(x.get('id')) for x in rows if x.get('event')=='reserve'}; settled={str(x.get('id')) for x in rows if x.get('event')=='settle'}
 if not reserved or reserved!=settled: raise RuntimeError('source ledger unresolved')
 dirs=sorted((source/'copromem-dynamic-checkpoints/tasks').glob('*'))
 complete=[d for d in dirs if (d/'post-state.json').is_file()]
 if len(complete)!=38: raise RuntimeError('source completed checkpoint prefix differs')
 failed=dirs[-1]
 if failed.name!='0039-b6d1104_1' or not (failed/'03-trajectories_complete.json').is_file(): raise RuntimeError('source failed boundary differs')
 pre=read(failed/'pre-state.json')['state']; arm=ARM; task='b6d1104_1'
 arts=[read(source/'artifacts'/task/arm/f'trial-{i}.json') for i in (1,2,3)]
 from copromem.experiments.reme_copromem.contrastive_v6_runner import semantic_spine_task_batch_update
 registry=read(base.REG)
 post,marker,audit=semantic_spine_task_batch_update(artifacts=arts,registry=registry,pre_state=pre,evidence_paths=[a['execution_evidence_path'] for a in arts],run_root=source,discard_schema_invalid_unsuccessful_calls=True)
 if audit['post_state_sha256']!=sha(post) or [x['ingestion']['discarded_schema_invalid_unsuccessful_call_rows'] for x in audit['semantic_graph_audits']] != [1,0,0]: raise RuntimeError('source recovery update does not reproduce exact rejected-call boundary')
 refs=[]
 for path in sorted((source/'artifacts').glob('**/trial-*.json')):
  a=read(path); refs.append({'trajectory_id':a.get('trajectory_id'),'artifact':str(path.resolve()),'artifact_sha256':fsha(path),'journal':str(Path(a['execution_evidence_path']).resolve()),'journal_sha256':fsha(Path(a['execution_evidence_path'])),'task_id':a.get('task_id'),'trial_id':a.get('trial_id'),'seed':a.get('seed')})
 if len(refs)!=117:raise RuntimeError('source artifact prefix differs')
 exposure=sum(float(x.get('usd',0)) for x in rows if x.get('event')=='settle' and x.get('role')!='historical_carry_forward')
 result={'source_manifest_sha256':fsha(source/'manifest.json'),'source_ledger_sha256':fsha(ledger),'source_ledger_rows':len(rows),'historical_settled_exposure_usd':exposure,'artifacts':refs,'completed_checkpoint_count':38,'failed_task':task,'reconstructed_marker_sha256':sha(marker),'reconstructed_audit_sha256':sha(audit),'restored_state':post,'restored_state_sha256':sha(post),'remaining':tasks[39:]}
 if continuation is None:return result
 cm=read(continuation/'manifest.json'); cr=read(continuation/'recovery-custody.json')
 if cm.get('recovery',{}).get('imported_trajectory_count')!=117 or cr.get('source_manifest_sha256')!=result['source_manifest_sha256']:raise RuntimeError('continuation custody source differs')
 cledger=continuation/'ledger.jsonl'; crows=[json.loads(x) for x in cledger.read_text(encoding='utf-8').splitlines() if x]
 creserved={str(x.get('id')) for x in crows if x.get('event')=='reserve'}; csettled={str(x.get('id')) for x in crows if x.get('event')=='settle'}
 if not creserved or creserved!=csettled:raise RuntimeError('continuation ledger unresolved')
 ctask=result['remaining'][0]
 cdir=continuation/'copromem-dynamic-checkpoints'/'tasks'/f'0001-{ctask}'
 if not cdir.is_dir() or not (cdir/'pre-state.json').is_file() or (cdir/'post-state.json').exists():raise RuntimeError('continuation failed boundary differs')
 cpre=read(cdir/'pre-state.json').get('state')
 if sha(cpre)!=result['restored_state_sha256']:raise RuntimeError('continuation pre-state differs')
 carts=[read(continuation/'artifacts'/ctask/ARM/f'trial-{i}.json') for i in (1,2,3)]
 cpost,cmarker,caudit=semantic_spine_task_batch_update(artifacts=carts,registry=registry,pre_state=cpre,evidence_paths=[a['execution_evidence_path'] for a in carts],run_root=continuation,discard_schema_invalid_reads=True,discard_schema_invalid_unsuccessful_calls=True)
 reads=[x['ingestion']['discarded_schema_invalid_read_rows'] for x in caudit['semantic_graph_audits']]; unsuccessful=[x['ingestion']['discarded_schema_invalid_unsuccessful_call_rows'] for x in caudit['semantic_graph_audits']]
 if reads!=[1,0,0] or unsuccessful!=[1,0,0] or caudit['post_state_sha256']!=sha(cpost):raise RuntimeError('continuation read-only recovery does not reproduce exact boundary')
 crefs=[]
 for path in sorted((continuation/'artifacts'/ctask/ARM).glob('trial-*.json')):
  a=read(path);crefs.append({'trajectory_id':a.get('trajectory_id'),'artifact':str(path.resolve()),'artifact_sha256':fsha(path),'journal':str(Path(a['execution_evidence_path']).resolve()),'journal_sha256':fsha(Path(a['execution_evidence_path'])),'task_id':a.get('task_id'),'trial_id':a.get('trial_id'),'seed':a.get('seed')})
 if len(crefs)!=3 or len({x['trajectory_id'] for x in refs+crefs})!=120:raise RuntimeError('continuation artifact prefix differs')
 result.update({'continuation_run':str(continuation.resolve()),'continuation_manifest_sha256':fsha(continuation/'manifest.json'),'continuation_ledger_sha256':fsha(cledger),'continuation_ledger_rows':len(crows),'historical_settled_exposure_usd':exposure+sum(float(x.get('usd',0)) for x in crows if x.get('event')=='settle'),'artifacts':refs+crefs,'completed_checkpoint_count':39,'failed_task':ctask,'reconstructed_marker_sha256':sha(cmarker),'reconstructed_audit_sha256':sha(caudit),'restored_state':cpost,'restored_state_sha256':sha(cpost),'remaining':result['remaining'][1:]})
 return result
def recovery_configure(run:Path,src:Mapping[str,Any])->None:
 overlay=__import__('scripts.run_v627_multi_schema_100x3',fromlist=['configure'])
 overlay.configure(run)
 global _BANK; _BANK=run/RECOVERY_BANK
 base.COPRO=_BANK;base.FROZEN_TASK_IDS=list(src['remaining']);base.EVALUATION_SEEDS=TRIAL_SEEDS;base.CALL_LIMITS={'executor':len(src['remaining'])*len(TRIAL_SEEDS)*30,'reme_lifecycle':0,'reme_embedding':0,'copromem_decomposition':0};base.HISTORICAL_EXPOSURE=float(src['historical_settled_exposure_usd']);base.PROTOCOL=PROTOCOL;base.PREEXISTING_RUN_FILES={ALLOCATION_NAME,'public-operation-intents.json','schema-multi-admission.json',CUSTODY,RECOVERY_BANK}
 report=read(base.CONSTRUCTION/'FINAL_CONSTRUCTION_REPORT.json');base.identities=lambda:(report,{'state_sha256':src['restored_state_sha256']})
 base.semantic_task_batch_update=lambda **kwargs:semantic_spine_task_batch_update(**kwargs,discard_schema_invalid_reads=True)
def recovery_prepare(run:Path,source:Path,continuation:Path|None=None)->None:
 src=source_state(source,continuation)
 if run.exists() and any(run.iterdir()):raise RuntimeError('recovery target must be empty')
 run.mkdir(parents=True)
 for name in (ALLOCATION_NAME,'public-operation-intents.json','schema-multi-admission.json'): (run/name).write_bytes((source/name).read_bytes())
 imported=len(src['artifacts']);custody={'version':PROTOCOL,'source_run':str(source.resolve()),**{k:v for k,v in src.items() if k!='restored_state'},'source_immutable':True,'provider_calls_replayed':False,'composite_expected_scored_trajectories':imported+len(src['remaining'])*3};custody['custody_sha256']=sha(custody);write_json(run/CUSTODY,custody)
 bank=run/RECOVERY_BANK;bank.mkdir();write_json(bank/'fixed-bank.json',src['restored_state']);write_json(bank/'semantic-admission-gate.json',{'version':PROTOCOL,'state_sha256':src['restored_state_sha256'],'source_custody_sha256':custody['custody_sha256']})
 recovery_configure(run,src);base.prepare(run)
 t=read(run/'template.json');t.update({'protocol':PROTOCOL,'method':{'copromem':POLICY_VERSION,'retrieval':'v627 multi-schema recovery continuation','analysis_scope':'no-replay continuation; immutable source evidence referenced'},'method_policy':frozen_policy(),'recovery':{'custody_file_sha256':fsha(run/CUSTODY),'imported_trajectory_count':imported,'reconstructed_failed_task':src['failed_task'],'next_task_id':src['remaining'][0],'provider_calls_replayed':False}});t['evaluation'].update({'allocation_audit_sha256':fsha(run/ALLOCATION_NAME),'task_ids':src['remaining'],'task_count':len(src['remaining']),'trial_count':len(TRIAL_SEEDS),'expected_trajectories':len(src['remaining'])*3,'recovery_imported_trajectories':imported,'composite_expected_scored_trajectories':custody['composite_expected_scored_trajectories']});t['banks']['copromem_sha256']=src['restored_state_sha256'];t['budget']['historical_settled_exposure']=src['historical_settled_exposure_usd'];t['runtime_identity_version']=RUNTIME_IDENTITY_V3
 runtime,inputs=build_evaluation_identity_v3(root=ROOT,manifest=t);write_json(run/'runtime-identity.json',runtime);write_json(run/'runtime-identity.binding.json',{'runtime_identity_sha256':runtime['runtime_identity_sha256'],'runtime_identity_record_sha256':base.file_sha(run/'runtime-identity.json')});t['runtime_identity_inputs']=inputs;t['runtime_identity_sha256']=runtime['runtime_identity_sha256'];t['runtime_identity_file_sha256']=base.file_sha(run/'runtime-identity.json');write_json(run/'template.json',t)
def configure(run:Path)->None:
 global _BANK
 a=audit(run);_BANK=Path(str(a['copromem_bank']['path']));base.SOURCE=REVIEW/'artifacts/research/official_reme_copromem_pilot/v6_shared_acquisition_001';base.CONSTRUCTION=REVIEW/'artifacts/research/official_reme_copromem_pilot/v6_1_exploratory_diagnostic_construction_003';base.PROTOCOL=PROTOCOL;base.ARMS=list(ARMS);install_copromem_only_runtime(base,base.ARMS);base.FROZEN_TASK_IDS=list(a['selected_task_ids']);base.EVALUATION_SPLIT=str(a['split']);base.EVALUATION_SEEDS=TRIAL_SEEDS;base.HARD_CAP_USD=HARD_CAP_USD;base.CALL_LIMITS={'executor':TASK_COUNT*len(TRIAL_SEEDS)*30,'reme_lifecycle':0,'reme_embedding':0,'copromem_decomposition':0};base.HISTORICAL_EXPOSURE=0.0;base.COPRO_FIXED_ARM='copromem_v6_2_7_fixed_unregistered';base.COPRO_DYNAMIC_ARM=ARM;base.TASK_MAJOR_ARM_FIRST=True;base.PREEXISTING_RUN_FILES={ALLOCATION_NAME,'public-operation-intents.json','schema-multi-admission.json'};base.COPRO=_BANK;base.identities=identities
 intents=read(run/'public-operation-intents.json');verify_intents(intents);retrieval_record.bundle_path=run/'schema-multi-admission.json'
 base.derive_task_query=lambda instruction,domain,meta,callable_registry=None:derive_task_query(instruction,domain,{**meta,'public_operation_intents':intents},callable_registry or read(base.REG))
 base.validate_task_query=lambda record,*,instruction,public_tool_metadata,callable_registry:validate_task_query(record,instruction=instruction,public_tool_metadata={**public_tool_metadata,'public_operation_intents':intents},callable_registry=callable_registry)
 base.retrieval_record=retrieval_record;base.reproduce_retrieval=lambda state,task_query,callable_registry,provenance:reproduce_retrieval(state,task_query,callable_registry,provenance,read(run/'schema-multi-admission.json'));base.semantic_task_batch_update=semantic_spine_task_batch_update
def prepare(run:Path)->None:
 run.mkdir(parents=True,exist_ok=True);ip=run/'public-operation-intents.json'
 if not ip.exists():write_json(ip,build_intents(openapi()))
 configure(run);base.prepare(run);p=run/'template.json';t=read(p);a=audit(run);t['method']={'copromem':POLICY_VERSION,'retrieval':'independently admitted multi-schema relevant-app terminal slice','analysis_scope':'v627 Dynamic overlay on exact E074 grid; engineering pilot only'};t['method_policy']=frozen_policy();t['execution']['provider_only']=CHAT_PROVIDER;t['evaluation'].update({'allocation_audit_sha256':fsha(run/ALLOCATION_NAME),'expected_trajectories':TASK_COUNT*len(TRIAL_SEEDS),'task_count':TASK_COUNT,'trial_count':len(TRIAL_SEEDS),'phase':'four_arm_overlay','overlay_four_arm_allocation_sha256':a['four_arm_allocation_sha256']});t['external_admission']={'mode':'multi_schema_admitted_retrieval','bundle_file_sha256':fsha(run/'schema-multi-admission.json'),'bundle_sha256':a['multi_schema_admission_sha256']};t['budget'].update({'historical_settled_exposure':0.0,'hard_cap_usd':HARD_CAP_USD});t['runtime_identity_version']=RUNTIME_IDENTITY_V3;runtime,inputs=build_evaluation_identity_v3(root=ROOT,manifest=t);write_json(run/'runtime-identity.json',runtime);write_json(run/'runtime-identity.binding.json',{'runtime_identity_sha256':runtime['runtime_identity_sha256'],'runtime_identity_record_sha256':base.file_sha(run/'runtime-identity.json')});t['runtime_identity_inputs']=inputs;t['runtime_identity_sha256']=runtime['runtime_identity_sha256'];t['runtime_identity_file_sha256']=base.file_sha(run/'runtime-identity.json');write_json(p,t)
def main()->None:
 p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','freeze','preflight','run']);p.add_argument('--run',type=Path,required=True);p.add_argument('--source-run',type=Path);p.add_argument('--continuation-run',type=Path);x=p.parse_args();run=x.run.resolve()
 if x.command=='prepare':
  if x.source_run is None:raise SystemExit('prepare requires --source-run')
  recovery_prepare(run,x.source_run.resolve(),x.continuation_run.resolve() if x.continuation_run else None);return
 custody=read(run/CUSTODY);src=source_state(Path(str(custody['source_run'])),Path(str(custody['continuation_run'])) if custody.get('continuation_run') else None)
 recovery_configure(run,src)
 if x.command=='freeze':base.freeze(run)
 elif x.command=='preflight':base.load(run);base.st(run,'preflight_passed',imported_completed_trajectories=len(src['artifacts']),next_task_id=src['remaining'][0])
 else:base.run(run)
if __name__=='__main__':main()
