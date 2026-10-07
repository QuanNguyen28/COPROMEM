import json
from pathlib import Path
import pytest
from copromem.experiments.reme_copromem.external_validation_admission import admit

def write(tmp,score=1.0, injected=True):
 a=tmp/'a.json';j=tmp/'j.jsonl';a.write_text(json.dumps({'task_id':'held','after_score':score,'termination':'completed','copromem_callback_guidance_nonempty':injected,'injected_memory_nonempty':injected,'injected_memory_visible_in_initial_prompt':injected,'execution_evidence':{'registry_sha256':'r'},'official_scorer_evidence':{'sha256':'s'}}));j.write_text('{}\n');return a,j
def test_admit_verified_external_retrieval_contract_independent_of_task_score(tmp_path):
 a,j=write(tmp_path);x=admit(bank_sha256='b',schema_ids=['x'],validation_task_id='held',artifact_path=a,journal_path=j,expected_registry_sha256='r');assert x['passed']
 assert x['version']=='copromem-external-schema-admission-v2' and x['admission_kind']=='retrieval_execution_contract_v1'
def test_reject_missing_or_invisible_guidance(tmp_path):
 a,j=write(tmp_path,0.5,injected=False)
 with pytest.raises(ValueError,match='inject verified guidance'):admit(bank_sha256='b',schema_ids=['x'],validation_task_id='held',artifact_path=a,journal_path=j,expected_registry_sha256='r')

def test_accepts_versioned_top_level_execution_evidence_binding(tmp_path):
 a,j=write(tmp_path); value=json.loads(a.read_text()); value.pop('execution_evidence'); value['execution_evidence_registry_sha256']='r'; a.write_text(json.dumps(value))
 assert admit(bank_sha256='b',schema_ids=['x'],validation_task_id='held',artifact_path=a,journal_path=j,expected_registry_sha256='r')['passed']


def test_policy_bound_admission_requires_the_exact_retrieval_provenance(tmp_path):
 a,j=write(tmp_path); retrieval=tmp_path/'retrieval.json'
 policy='a'*64
 retrieval.write_text(json.dumps({'policy_sha256':policy,'guidance_nonempty':True}))
 value=admit(bank_sha256='b',schema_ids=['x'],validation_task_id='held',artifact_path=a,journal_path=j,
             expected_registry_sha256='r',retrieval_provenance_path=retrieval,retrieval_policy_sha256=policy)
 assert value['version']=='copromem-external-schema-admission-v3'
 assert value['retrieval_policy_sha256']==policy
 retrieval.write_text(json.dumps({'policy_sha256':'b'*64,'guidance_nonempty':True}))
 with pytest.raises(ValueError,match='policy binding'):
  admit(bank_sha256='b',schema_ids=['x'],validation_task_id='held',artifact_path=a,journal_path=j,
        expected_registry_sha256='r',retrieval_provenance_path=retrieval,retrieval_policy_sha256=policy)
