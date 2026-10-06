import json
from pathlib import Path
import pytest
from copromem.experiments.reme_copromem.external_validation_admission import admit

def write(tmp,score=1.0):
 a=tmp/'a.json';j=tmp/'j.jsonl';a.write_text(json.dumps({'task_id':'held','after_score':score,'execution_evidence':{'registry_sha256':'r'},'official_scorer_evidence':{'sha256':'s'}}));j.write_text('{}\n');return a,j
def test_admit_only_successful_bound_external_artifact(tmp_path):
 a,j=write(tmp_path);x=admit(bank_sha256='b',schema_ids=['x'],validation_task_id='held',artifact_path=a,journal_path=j,expected_registry_sha256='r');assert x['passed']
def test_reject_failed_or_wrong_task(tmp_path):
 a,j=write(tmp_path,0.5)
 with pytest.raises(ValueError,match='did not pass'):admit(bank_sha256='b',schema_ids=['x'],validation_task_id='held',artifact_path=a,journal_path=j,expected_registry_sha256='r')
