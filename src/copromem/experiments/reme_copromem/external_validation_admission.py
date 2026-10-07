"""Post-score admission gate for one isolated external validation trajectory."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from collections.abc import Mapping,Sequence
from typing import Any
from .schema_external_admission import receipt
from .contrastive_v6_runner import scorer_evidence_sha256

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def admit(*,bank_sha256:str,schema_ids:Sequence[str],validation_task_id:str,artifact_path:Path,journal_path:Path,expected_registry_sha256:str,
          retrieval_provenance_path:Path|None=None,retrieval_policy_sha256:str|None=None)->dict[str,Any]:
 """Admit only a durable successful held-out artifact and matching journal."""
 if not artifact_path.is_file() or not journal_path.is_file():raise ValueError('external validation evidence is missing')
 artifact=json.loads(artifact_path.read_text())
 if str(artifact.get('task_id'))!=validation_task_id:raise ValueError('external validation task identity mismatch')
 if artifact.get('termination')!='completed':raise ValueError('external validation did not complete')
 if artifact.get('copromem_callback_guidance_nonempty') is not True or artifact.get('injected_memory_nonempty') is not True:
  raise ValueError('external validation did not inject verified guidance')
 if artifact.get('injected_memory_visible_in_initial_prompt') is not True:
  raise ValueError('external validation guidance was not prompt-visible')
 evidence=artifact.get('execution_evidence')
 registry_sha = (evidence.get('registry_sha256') if isinstance(evidence, Mapping)
                 else artifact.get('execution_evidence_registry_sha256'))
 if registry_sha!=expected_registry_sha256:raise ValueError('external validation execution evidence mismatch')
 if (retrieval_provenance_path is None)!=(retrieval_policy_sha256 is None):
  raise ValueError('external validation retrieval policy binding is incomplete')
 if retrieval_provenance_path is not None:
  if not retrieval_provenance_path.is_file():raise ValueError('external validation retrieval provenance is missing')
  loaded=json.loads(retrieval_provenance_path.read_text())
  provenance=loaded.get('provenance',loaded) if isinstance(loaded, Mapping) else {}
  if provenance.get('policy_sha256')!=retrieval_policy_sha256 or provenance.get('guidance_nonempty') is not True:
   raise ValueError('external validation retrieval policy binding is invalid')
 scorer=scorer_evidence_sha256(artifact)
 return receipt(bank_sha256=bank_sha256,schema_ids=schema_ids,validation_task_id=validation_task_id,artifact_sha256=sha(artifact_path),scorer_evidence_sha256=scorer,journal_sha256=sha(journal_path),passed=True,admission_kind='retrieval_execution_contract_v1',retrieval_policy_sha256=retrieval_policy_sha256)
