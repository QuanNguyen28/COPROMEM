#!/usr/bin/env python3
"""Frozen v6.2.7 multi-schema Dynamic overlay on the E074 100x3 grid."""
from __future__ import annotations
import argparse, hashlib, json, math, os
from pathlib import Path
import sys
from typing import Any, Mapping
ROOT=Path(__file__).resolve().parents[1]; sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from copromem.experiments.reme_copromem.contrastive_v6_runner import semantic_spine_task_batch_update
from copromem.experiments.reme_copromem.public_operation_intent_registry import build as build_intents, verify as verify_intents
from copromem.experiments.reme_copromem.runner import write_json
from copromem.experiments.reme_copromem.runtime_identity_v3 import IDENTITY_VERSION as RUNTIME_IDENTITY_V3, build_evaluation_identity_v3
from copromem.experiments.reme_copromem.schema_multi_admission import verify as verify_bundle
from copromem.experiments.reme_copromem.task_conditioned_retrieval_v627 import POLICY_VERSION, derive_task_query, frozen_policy, reproduce_retrieval, retrieve, validate_task_query
from copromem.integrations.reme.transport import PROVIDER as CHAT_PROVIDER, verify_locked_chat_route_available
from scripts import run_v61_exploratory_evaluation as base
from scripts.v626_copromem_only_runtime import install as install_copromem_only_runtime
PROTOCOL='v6_2_7_multi_schema_100x3_engineering_pilot_001'; ARM='copromem_v6_2_7_dynamic'; ARMS=[ARM]; TRIAL_SEEDS=(11001,11002,11003); TASK_COUNT=100; HARD_CAP_USD=140.0; ALLOCATION_NAME='allocation-audit-v627-multi-schema-100x3.json'
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
 p=argparse.ArgumentParser();p.add_argument('command',choices=['allocate','prepare','freeze','preflight','run']);p.add_argument('--run',type=Path,required=True);p.add_argument('--source-manifest',type=Path);p.add_argument('--four-arm-allocation',type=Path);p.add_argument('--seed-bank',type=Path);p.add_argument('--multi-schema-admission',type=Path);x=p.parse_args();run=x.run.resolve()
 if x.command=='allocate':
  if not all((x.source_manifest,x.four_arm_allocation,x.seed_bank,x.multi_schema_admission)):raise SystemExit('allocate requires --source-manifest --four-arm-allocation --seed-bank --multi-schema-admission')
  allocate(run,x.source_manifest.resolve(),x.four_arm_allocation.resolve(),x.seed_bank.resolve(),x.multi_schema_admission.resolve());return
 if x.command=='prepare':prepare(run);return
 configure(run)
 if x.command=='freeze':base.freeze(run)
 elif x.command=='preflight':
  base.load(run);route=verify_locked_chat_route_available()
  if route.get('provider')!=CHAT_PROVIDER:raise RuntimeError('locked provider route differs')
  write_json(run/'provider-route-preflight.json',route);base.st(run,'preflight_passed',provider_route=route)
 else:base.run(run)
if __name__=='__main__':main()
