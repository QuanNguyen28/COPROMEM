"""Immutable held-out admission receipts for retrieval schemas."""
from __future__ import annotations
import hashlib, json
from collections.abc import Mapping, Sequence
from typing import Any

def canonical(value: Any)->bytes:
 return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def digest(value: Any)->str:return hashlib.sha256(canonical(value)).hexdigest()

def receipt(*, bank_sha256:str, schema_ids:Sequence[str], validation_task_id:str,
            artifact_sha256:str, scorer_evidence_sha256:str, journal_sha256:str,
            passed:bool, admission_kind:str|None=None)->dict[str,Any]:
 """Create a value-free, single external-task admission decision."""
 ids=sorted(set(str(x) for x in schema_ids))
 if not bank_sha256 or not ids or len(ids)!=len(schema_ids) or not validation_task_id:
  raise ValueError('external admission identity is incomplete')
 if not all(isinstance(x,str) and x for x in (artifact_sha256,scorer_evidence_sha256,journal_sha256)):
  raise ValueError('external admission evidence is incomplete')
 row={'version':'copromem-external-schema-admission-v1','bank_sha256':bank_sha256,
      'schema_ids':ids,'validation_task_id':validation_task_id,'artifact_sha256':artifact_sha256,
      'scorer_evidence_sha256':scorer_evidence_sha256,'journal_sha256':journal_sha256,
      'passed':passed}
 if admission_kind is not None:
  if admission_kind not in {'retrieval_execution_contract_v1'}:raise ValueError('unknown external admission kind')
  row['version']='copromem-external-schema-admission-v2';row['admission_kind']=admission_kind
 row['receipt_sha256']=digest(row);return row

def verify(value:Mapping[str,Any],*,bank_sha256:str)->None:
 row=dict(value); actual=row.pop('receipt_sha256',None)
 if actual!=digest(row):raise ValueError('external admission receipt hash mismatch')
 if row.get('version') not in {'copromem-external-schema-admission-v1','copromem-external-schema-admission-v2'} or row.get('bank_sha256')!=bank_sha256:
  raise ValueError('external admission receipt bank mismatch')
 if row.get('passed') is not True or not isinstance(row.get('schema_ids'),list) or not row['schema_ids']:
  raise ValueError('schema is not externally admitted')
 if row.get('version')=='copromem-external-schema-admission-v2' and row.get('admission_kind')!='retrieval_execution_contract_v1':
  raise ValueError('external admission kind is invalid')
 if row['schema_ids']!=sorted(set(row['schema_ids'])):raise ValueError('external admission schema order is invalid')
