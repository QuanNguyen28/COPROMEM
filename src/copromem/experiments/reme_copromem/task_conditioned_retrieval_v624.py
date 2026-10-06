"""v6.2.4 retrieval: public intent + externally admitted schemas only."""
from __future__ import annotations
import re
from collections.abc import Mapping
from typing import Any
from . import task_conditioned_retrieval_v623 as base
from .public_operation_intent_registry import verify as verify_intents
from .schema_external_admission import verify as verify_admission

POLICY_VERSION='copromem-v6.2.4-external-admission-intent-retrieval'
_STOP=frozenset({'a','an','the','to','for','of','in','on','with','and','or','from','your','you'})
_CURRENCY=re.compile(r'[$€£]\s*\d')
_RECIPIENT=re.compile(r'\bto\s+[A-Z][\w-]*')

def _evidence_tokens(instruction:str)->set[str]:
 t=set(base.v621._tokens(instruction))
 if _CURRENCY.search(instruction): t.update({'money','amount'})
 if _RECIPIENT.search(instruction): t.update({'user','receiver','recipient'})
 return t

def derive_task_query(instruction:str,domain:str,public_tool_metadata:Mapping[str,Any],callable_registry:Mapping[str,Any])->dict[str,Any]:
 q=base.derive_task_query(instruction,domain,public_tool_metadata,callable_registry)
 intents=public_tool_metadata.get('public_operation_intents')
 if not isinstance(intents,Mapping): raise ValueError('v6.2.4 requires frozen public operation intents')
 verify_intents(intents); named=set(q['derived_public_descriptor']['relevant_public_apps']); tokens=_evidence_tokens(instruction)
 extra=[]
 for item in intents['operations']:
  if item['app'] not in named: continue
  required=set(item['description_tokens'])-_STOP
  if required and required <= tokens:
   extra.append({'operation':item['operation'],'app':item['app'],'verb':base.v621._operation_tokens(item['operation'])[1],
                 'matched_nouns':sorted(required),'matched_action_terms':[], 'match_strength':len(required),
                 'public_access_mode':'intent_documented','match_mode':'public_openapi_intent_full_match'})
 # An intent must uniquely identify a public callable. No id/order tie breaking.
 unique=[x for x in extra if sum(y['operation']!=x['operation'] and set(y['matched_nouns'])==set(x['matched_nouns']) for y in extra)==0]
 old={x['operation'] for x in q['operation_evidence']}; additions=[x for x in unique if x['operation'] not in old]
 ev=sorted([*q['operation_evidence'],*additions],key=lambda x:x['operation']); ops=[x['operation'] for x in ev]
 out={**q,'policy_version':POLICY_VERSION,'operation_evidence':ev,'canonical_query_operations':ops,'query_operations':ops,
      'intent_registry_sha256':intents['intent_registry_sha256'],'externally_documented_terminal_operations':[x['operation'] for x in additions]}
 out['derived_public_descriptor']={**q['derived_public_descriptor'],'candidate_operations':ops}
 out['query_sha256']=base.digest({k:v for k,v in out.items() if k!='query_sha256'});return out

def validate_task_query(record:Mapping[str,Any],*,instruction:str,public_tool_metadata:Mapping[str,Any],callable_registry:Mapping[str,Any])->None:
 expected=derive_task_query(instruction,str(record['derived_public_descriptor']['domain']),public_tool_metadata,callable_registry)
 if dict(record)!=expected:raise ValueError('v6.2.4 query does not reproduce')

def retrieve(state:Mapping[str,Any],task_query:Mapping[str,Any],callable_registry:Mapping[str,Any],admission:Mapping[str,Any])->tuple[str,dict[str,Any]]:
 bank=base.digest(state); verify_admission(admission,bank_sha256=bank); allowed=set(admission['schema_ids']); candidates=[]
 for sid,schema in sorted(base._schema_rows(state).items()):
  if sid not in allowed: continue
  item=base._features(sid,schema,task_query,callable_registry)
  if item['terminal_effect'] in task_query.get('externally_documented_terminal_operations',[]):
   unsafe=[x for x in item['unsupported_public_inputs'] if x['operation']!=item['terminal_effect']]
   if not unsafe:
    item={**item,'unsupported_public_inputs':[],'rejection_reasons':[x for x in item['rejection_reasons'] if x!='prerequisite_input_not_supported_by_public_query_or_dataflow']}
    item['rejection_reason']=item['rejection_reasons'][0] if item['rejection_reasons'] else None;item['compatible']=not item['rejection_reasons'];item['score']=item['semantic_evidence'] if item['compatible'] else [0]
  candidates.append(item)
 compatible=[x for x in candidates if x['compatible']]; top=compatible if len(compatible)==1 else []
 selected=top[0] if top else None; guidance=base._guidance(selected) if selected else ''
 prov={'policy_version':POLICY_VERSION,'pre_state_semantic_sha256':bank,'task_query':dict(task_query),'task_query_sha256':task_query['query_sha256'],'registry_sha256':callable_registry['registry_sha256'],'external_admission_receipt_sha256':admission['receipt_sha256'],'candidate_schema_ids':[x['schema_id'] for x in candidates],'candidate_scores':candidates,'selected_schema_id':selected['schema_id'] if selected else None,'selection_decision':'external_admission_unique_winner' if selected else 'external_admission_abstention','guidance':guidance,'guidance_sha256':base.digest(guidance),'guidance_nonempty':bool(guidance)}
 prov['retrieval_sha256']=base.digest(prov);return guidance,prov


def candidate_validation_retrieve(state: Mapping[str, Any], task_query: Mapping[str, Any],
                                  callable_registry: Mapping[str, Any], *, schema_id: str,
                                  validation_task_id: str, current_task_id: str) -> tuple[str, dict[str, Any]]:
 """One isolated pre-admission retrieval, forbidden outside its held-out task.

 It has a distinct provenance mode and cannot be mistaken for an admitted
 retrieval.  Its scored artifact is the sole input to the admission receipt.
 """
 if current_task_id != validation_task_id:
  raise ValueError('candidate validation task identity mismatch')
 rows=base._schema_rows(state)
 if schema_id not in rows: raise ValueError('candidate validation schema is absent')
 item=base._features(schema_id,rows[schema_id],task_query,callable_registry)
 if item['terminal_effect'] not in task_query.get('externally_documented_terminal_operations',[]):
  raise ValueError('candidate terminal lacks public intent evidence')
 unsafe=[x for x in item['unsupported_public_inputs'] if x['operation']!=item['terminal_effect']]
 if unsafe or any(x not in {'prerequisite_input_not_supported_by_public_query_or_dataflow'} for x in item['rejection_reasons']):
  raise ValueError('candidate validation has an unproven prerequisite or incompatible schema')
 guidance=base._guidance(item)
 provenance={'policy_version':POLICY_VERSION,'retrieval_mode':'isolated_external_candidate_validation',
  'validation_task_id':validation_task_id,'candidate_schema_id':schema_id,'pre_state_semantic_sha256':base.digest(state),
  'task_query':dict(task_query),'task_query_sha256':task_query['query_sha256'],'registry_sha256':callable_registry['registry_sha256'],
  'candidate_score':item,'guidance':guidance,'guidance_sha256':base.digest(guidance),'guidance_nonempty':bool(guidance)}
 provenance['retrieval_sha256']=base.digest(provenance);return guidance,provenance

def frozen_policy() -> dict[str, Any]:
 value={'policy_version':POLICY_VERSION,'base_policy':base.POLICY_VERSION,
 'terminal_evidence':'frozen_public_openapi_description_full_intent_match',
 'admission':'one_isolated_external_scored_artifact_with_scorer_and_journal_hashes',
 'selection':'externally_admitted_unique_schema_only_no_id_or_support_tie_break',
 'cross_app_guard':'retained','unproven_prerequisite_guard':'retained','dynamic':'exact_durable_pre_task_prefix_only'}
 return {**value,'policy_sha256':base.digest(value)}


def reproduce_retrieval(state: Mapping[str, Any], task_query: Mapping[str, Any],
                        callable_registry: Mapping[str, Any],
                        provenance: Mapping[str, Any],
                        admission: Mapping[str, Any] | None = None) -> str:
 """Rebuild one v6.2.4 retrieval and reject provenance-mode substitution.

 A candidate-validation record is deliberately not interchangeable with an
 admitted record: the former has no admission receipt and can only describe
 the held-out validation task.  This is used by restart custody validation.
 """
 if base.digest(state) != provenance.get('pre_state_semantic_sha256'):
  raise ValueError('v6.2.4 retrieval pre-state mismatch')
 if dict(task_query) != provenance.get('task_query') or task_query.get('query_sha256') != provenance.get('task_query_sha256'):
  raise ValueError('v6.2.4 retrieval query mismatch')
 mode = provenance.get('retrieval_mode')
 if mode == 'isolated_external_candidate_validation':
  guidance, expected = candidate_validation_retrieve(
   state, task_query, callable_registry,
   schema_id=str(provenance.get('candidate_schema_id') or ''),
   validation_task_id=str(provenance.get('validation_task_id') or ''),
   current_task_id=str(provenance.get('validation_task_id') or ''),
  )
 elif mode is None:
  if admission is None:
   raise ValueError('admitted retrieval restart lacks external admission receipt')
  guidance, expected = retrieve(state, task_query, callable_registry, admission)
 else:
  raise ValueError('unknown v6.2.4 retrieval provenance mode')
 if dict(provenance) != expected:
  raise ValueError('v6.2.4 retrieval provenance does not reproduce exactly')
 return guidance
