from pathlib import Path
import json
import pytest
from scripts.build_v627_multi_schema_admission import build
from copromem.experiments.reme_copromem import task_conditioned_retrieval_v627 as v
from copromem.experiments.reme_copromem.schema_external_admission import receipt


def schema():
    return {"policy_version":"copromem-v6.1-semantic-graph-v1","registry_sha256":"r","required_operations":["apis.phone.send_text_message"],"terminal_effect":"apis.phone.send_text_message","terminal_occurrence_id":"apis.phone.send_text_message#1","typed_constraints":[{"operation":"apis.phone.send_text_message","occurrence_index":1,"required":["body"],"outputs":["result"]}],"support":{"successes":2}}


def test_builds_and_rejects_unknown_schema(tmp_path: Path):
    bank=tmp_path/'bank.json'; bank.write_text(json.dumps({"contrastive_v6_schemas":{"one":schema()}}))
    good=receipt(bank_sha256='b',schema_ids=['one'],validation_task_id='held',artifact_sha256='a',scorer_evidence_sha256='s',journal_sha256='j',passed=True,admission_kind='retrieval_execution_contract_v1',retrieval_policy_sha256=v.frozen_policy()['policy_sha256'])
    rp=tmp_path/'good.json';rp.write_text(json.dumps(good)); result=build(bank_path=bank,receipt_paths=[rp])
    assert result['entries'][0]['schema_id']=='one'
    bad=dict(good);bad['schema_ids']=['missing'];bad['receipt_sha256']=receipt(bank_sha256='b',schema_ids=['missing'],validation_task_id='held',artifact_sha256='a',scorer_evidence_sha256='s',journal_sha256='j',passed=True,admission_kind='retrieval_execution_contract_v1',retrieval_policy_sha256=v.frozen_policy()['policy_sha256'])['receipt_sha256']
    bp=tmp_path/'bad.json';bp.write_text(json.dumps(bad))
    with pytest.raises(ValueError,match='absent'):
        build(bank_path=bank,receipt_paths=[bp])
