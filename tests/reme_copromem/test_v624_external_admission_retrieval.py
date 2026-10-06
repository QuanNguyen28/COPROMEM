from __future__ import annotations
import pytest
from copromem.experiments.reme_copromem import task_conditioned_retrieval_v624 as v
from copromem.experiments.reme_copromem.public_operation_intent_registry import digest
from copromem.experiments.reme_copromem.schema_external_admission import receipt

def registry():
 return {'registry_sha256':'r','normalization':{'operation_aliases':{}},'operations':[{'operation':'apis.venmo.create_transaction','http_method':'POST','access_mode':'write'}]}
def intents():
 r={'version':'appworld-public-operation-intent-registry-v1','sources':[],'operations':[{'operation':'apis.venmo.create_transaction','app':'venmo','http_method':'POST','description':'Send money to a user.','description_tokens':['money','send','to','user']}]};r['intent_registry_sha256']=digest(r);return r
def state():
 s={'contrastive_v6_schemas':{'one':{'policy_version':'copromem-v6.1-semantic-graph-v1','registry_sha256':'r','required_operations':['apis.venmo.create_transaction'],'terminal_effect':'apis.venmo.create_transaction','typed_constraints':[{'operation':'apis.venmo.create_transaction','occurrence_index':1,'required':['amount','receiver_email'],'outputs':['message']}],'support':{'successes':2}}}};return s
def meta():return {'app_descriptions':{'venmo':'public'},'public_operation_intents':intents()}
def test_admitted_public_intent_injects_guidance():
 q=v.derive_task_query('Send $427 on Venmo to Anita.','appworld',meta(),registry())
 assert q['externally_documented_terminal_operations']==['apis.venmo.create_transaction']
 s=state(); a=receipt(bank_sha256=v.base.digest(s),schema_ids=['one'],validation_task_id='heldout',artifact_sha256='a',scorer_evidence_sha256='s',journal_sha256='j',passed=True)
 guidance,p=v.retrieve(s,q,registry(),a)
 assert guidance and p['selected_schema_id']=='one'
def test_unadmitted_schema_cannot_inject():
 q=v.derive_task_query('Send $427 on Venmo to Anita.','appworld',meta(),registry());s=state();a=receipt(bank_sha256=v.base.digest(s),schema_ids=['other'],validation_task_id='heldout',artifact_sha256='a',scorer_evidence_sha256='s',journal_sha256='j',passed=True)
 guidance,p=v.retrieve(s,q,registry(),a);assert guidance=='' and p['selected_schema_id'] is None
def test_tampered_admission_fails_closed():
 q=v.derive_task_query('Send $427 on Venmo to Anita.','appworld',meta(),registry());s=state();a=receipt(bank_sha256='wrong',schema_ids=['one'],validation_task_id='heldout',artifact_sha256='a',scorer_evidence_sha256='s',journal_sha256='j',passed=True)
 with pytest.raises(ValueError,match='bank mismatch'):v.retrieve(s,q,registry(),a)

def test_candidate_validation_is_isolated_and_not_admitted_provenance():
 q=v.derive_task_query('Send $427 on Venmo to Anita.','appworld',meta(),registry());s=state()
 guidance,p=v.candidate_validation_retrieve(s,q,registry(),schema_id='one',validation_task_id='held',current_task_id='held')
 assert guidance and p['retrieval_mode']=='isolated_external_candidate_validation'
 with pytest.raises(ValueError,match='task identity'):
  v.candidate_validation_retrieve(s,q,registry(),schema_id='one',validation_task_id='held',current_task_id='other')

def test_restart_reproduces_only_the_same_typed_provenance():
 q=v.derive_task_query('Send $427 on Venmo to Anita.','appworld',meta(),registry());s=state()
 a=receipt(bank_sha256=v.base.digest(s),schema_ids=['one'],validation_task_id='held',artifact_sha256='a',scorer_evidence_sha256='s',journal_sha256='j',passed=True)
 guidance,p=v.retrieve(s,q,registry(),a)
 assert v.reproduce_retrieval(s,q,registry(),p,a)==guidance
 p['guidance']='changed'
 with pytest.raises(ValueError,match='does not reproduce'):
  v.reproduce_retrieval(s,q,registry(),p,a)
