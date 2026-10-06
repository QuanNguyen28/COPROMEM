"""Post-score admission gate for one isolated external validation trajectory."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from collections.abc import Mapping,Sequence
from typing import Any
from .schema_external_admission import receipt
from .contrastive_v6_runner import scorer_evidence_sha256

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def admit(*,bank_sha256:str,schema_ids:Sequence[str],validation_task_id:str,artifact_path:Path,journal_path:Path,expected_registry_sha256:str)->dict[str,Any]:
 """Admit only a durable successful held-out artifact and matching journal."""
 if not artifact_path.is_file() or not journal_path.is_file():raise ValueError('external validation evidence is missing')
 artifact=json.loads(artifact_path.read_text())
 if str(artifact.get('task_id'))!=validation_task_id:raise ValueError('external validation task identity mismatch')
 if float(artifact.get('after_score',-1))!=1.0:raise ValueError('external validation did not pass')
 evidence=artifact.get('execution_evidence')
 if not isinstance(evidence,Mapping) or evidence.get('registry_sha256')!=expected_registry_sha256:raise ValueError('external validation execution evidence mismatch')
 scorer=scorer_evidence_sha256(artifact)
 return receipt(bank_sha256=bank_sha256,schema_ids=schema_ids,validation_task_id=validation_task_id,artifact_sha256=sha(artifact_path),scorer_evidence_sha256=scorer,journal_sha256=sha(journal_path),passed=True)
