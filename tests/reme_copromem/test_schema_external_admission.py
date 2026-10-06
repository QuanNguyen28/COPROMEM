import pytest
from copromem.experiments.reme_copromem.schema_external_admission import receipt,verify

def valid():return receipt(bank_sha256='bank',schema_ids=['b','a'],validation_task_id='heldout',artifact_sha256='a',scorer_evidence_sha256='s',journal_sha256='j',passed=True)
def test_external_receipt_binds_heldout_evidence_and_bank():
 r=valid();verify(r,bank_sha256='bank');assert r['schema_ids']==['a','b']
def test_external_receipt_rejects_tamper_or_unpassed():
 r=valid();r['schema_ids']=['x']
 with pytest.raises(ValueError):verify(r,bank_sha256='bank')
 r=receipt(bank_sha256='bank',schema_ids=['a'],validation_task_id='heldout',artifact_sha256='a',scorer_evidence_sha256='s',journal_sha256='j',passed=False)
 with pytest.raises(ValueError):verify(r,bank_sha256='bank')
