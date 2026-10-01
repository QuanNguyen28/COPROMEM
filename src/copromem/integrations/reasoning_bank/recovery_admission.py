"""Atomic admission of an immutable, ordered ReasoningBank recovery prefix."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from .appworld import ReasoningBank, sha256
from .checkpoints import CheckpointPrefix
from .recovery import RecoveryIntegrityError, build_envelope
from .retrieval_provenance import ContentAddressedStore, RetrievalProvenanceError, _score, _score_record, verify
from copromem.experiments.reme_copromem.runtime_identity_binding import read as runtime_binding

VERSION = "reasoningbank-recovery-admission-v1"
MARKER_VERSION = "reasoningbank-recovery-admission-marker-v1"


def _canonical(value: Any) -> bytes: return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
def _digest(value: Any) -> str: return hashlib.sha256(_canonical(value)).hexdigest()
def _file(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()

def _read(path: Path) -> dict[str, Any]:
    try: value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise RecoveryIntegrityError("admission record is unreadable") from exc
    if not isinstance(value, dict): raise RecoveryIntegrityError("admission record is not an object")
    return value

def _atomic(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists(): raise RecoveryIntegrityError("admission staging record already exists")
    temporary = path.with_suffix(path.suffix + ".tmp")
    if temporary.exists(): raise RecoveryIntegrityError("partial recovery admission staging exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("x", encoding="utf-8") as handle:
        handle.write(_canonical(value).decode() + "\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, path)
    try:
        fd = os.open(str(path.parent), os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)
    except OSError: pass

def _schedule(manifest: Mapping[str, Any]) -> list[tuple[str,str,int,int]]:
    return [(str(arm),str(task),trial,int(seed)) for task in manifest["evaluation"]["task_ids"]
            for arm in manifest["arms"] for trial,seed in enumerate(manifest["evaluation"]["seeds"],1)]

def _ledger(source: Path) -> dict[str, Any]:
    path=source/"ledger.jsonl"; reserve=[]; settle=[]
    for raw in path.read_bytes().splitlines():
        try: row=json.loads(raw)
        except json.JSONDecodeError as exc: raise RecoveryIntegrityError("source ledger is malformed") from exc
        if row.get("event")=="reserve": reserve.append(str(row.get("id") or ""))
        elif row.get("event")=="settle": settle.append(str(row.get("id") or ""))
    if not reserve or len(reserve)!=len(set(reserve)) or set(reserve)!=set(settle): raise RecoveryIntegrityError("source ledger does not reconcile")
    return {"relative_locator":"ledger.jsonl","sha256":_file(path),"reservations":len(reserve),"settlements":len(settle),"unresolved":0}

def _pending(source: Path, key: tuple[str,str,int,int], bank_sha: str) -> dict[str, Any]:
    arm,task,trial,seed=key; path=source/"retrievals"/task/f"{arm}-trial-{trial}.json"
    if not path.is_file() or path.with_suffix(path.suffix+".prompt-binding.json").exists(): raise RecoveryIntegrityError("pending retrieval is absent or prompt-bound")
    record=_read(path); store=ContentAddressedStore(source/"reasoningbank-retrieval-objects")
    try: verify(path=path,store=store,expected_bank_sha256=bank_sha)
    except RetrievalProvenanceError as exc:
        if str(exc)!="recorded cosine score mismatch": raise RecoveryIntegrityError("pending retrieval has a non-score integrity failure") from exc
    else: raise RecoveryIntegrityError("pending retrieval has no score-domain defect")
    query=store.load_vector(record["query"]["vector"]); candidates=[]
    for value in record["candidates"]:
        item=dict(value); item["score"]=_score_record(_score(query,store.load_vector(item["vector"]))); candidates.append(item)
    candidates.sort(key=lambda x:(-float.fromhex(x["score"]["float64_hex"]),int(x["append_order"])))
    selected=candidates[0] if candidates else None
    if [x["experience_id"] for x in candidates] != [x["experience_id"] for x in record["candidates"]] or (selected or {}).get("experience_id") != record["selection"].get("selected_experience_id"):
        raise RecoveryIntegrityError("persisted-vector score reconstruction changes ordering or selection")
    guide=record["guidance"]; raw=store.load_text(guide["raw_memory_bytes"]); rendered=store.load_text(guide["rendered_bytes"])
    if sha256(raw)!=guide["raw_memory_sha256"] or sha256(rendered)!=guide["rendered_sha256"]: raise RecoveryIntegrityError("pending guidance bytes are inconsistent")
    body={"source_relative":path.relative_to(source).as_posix(),"source_sha256":_file(path),
          "key":{"arm":arm,"task_id":task,"trial_id":trial,"seed":seed,"trajectory_id":record["identity"]["trajectory_id"]},
          "pre_state_sha256":record["pre_state_sha256"],"query_vector":record["query"]["vector"],"candidates":candidates,
          "candidate_order":[x["experience_id"] for x in candidates],"selected_experience_id":selected["experience_id"] if selected else None,
          "selected_score":selected["score"] if selected else None,"raw_memory_sha256":guide["raw_memory_sha256"],"rendered_guidance_sha256":guide["rendered_sha256"],
          "embedding_request_prohibited":True,"prompt_binding_absent":True,"executor_dispatch_absent":True}
    return {**body,"reconstruction_sha256":_digest(body)}

def build_spec(source_run: Path, *, imported_keys: Sequence[tuple[str,str,int,int]], pending_key: tuple[str,str,int,int], checkpoint_count: int) -> dict[str,Any]:
    source=source_run.resolve(); manifest=_read(source/"manifest.json")
    if (source/"manifest.sha256").read_text().strip()!=_file(source/"manifest.json"): raise RecoveryIntegrityError("source manifest is hash-inconsistent")
    keys=list(imported_keys); schedule=_schedule(manifest)
    if not keys or keys!=schedule[:len(keys)] or len(keys)!=len(set(keys)) or len(keys)>=len(schedule) or pending_key!=schedule[len(keys)]: raise RecoveryIntegrityError("recovery keys are not an exact ordered prefix plus next key")
    envelopes=[build_envelope(source,task_id=t,arm=a,trial_id=i,seed=s) for a,t,i,s in keys]
    ids=[f"evaluation:reasoningbank_dynamic:{t}:trial={i}:seed={s}" for t in manifest["evaluation"]["task_ids"] for i,s in enumerate(manifest["evaluation"]["seeds"],1)]
    prefix=CheckpointPrefix.from_source(root=source/"reasoningbank-dynamic-checkpoints",expected_trajectory_ids=ids,ledger_path=source/"ledger.jsonl",count=checkpoint_count,initial_bank=ReasoningBank.restore(manifest["initial_bank"]))
    body={"version":VERSION,"source_run":str(source),"source_manifest_sha256":_file(source/"manifest.json"),"source_runtime_identity":runtime_binding(source),"source_ledger":_ledger(source),
          "imported_envelopes":envelopes,"progress":{"imported":len(keys),"pending":1,"expected":len(schedule)},
          "checkpoint_prefix":{"identity_sha256":prefix.identity_sha256,"count":len(prefix.completed),"restored_bank_sha256":prefix.restored_bank.state()["semantic_state_sha256"],"last_marker_sha256":prefix.completed[-1].marker_sha256},
          "pending":_pending(source,pending_key,prefix.restored_bank.state()["semantic_state_sha256"]),"next_key":{"arm":pending_key[0],"task_id":pending_key[1],"trial_id":pending_key[2],"seed":pending_key[3]}}
    return {**body,"recovery_spec_sha256":_digest(body)}

def validate_spec(spec: Mapping[str,Any]) -> dict[str,Any]:
    source=Path(str(spec.get("source_run") or "")); keys=[(str(x["key"]["arm"]),str(x["key"]["task_id"]),int(x["key"]["trial_id"]),int(x["key"]["seed"])) for x in spec.get("imported_envelopes",[])]
    n=spec.get("next_key") or {}; actual=build_spec(source,imported_keys=keys,pending_key=(str(n.get("arm")),str(n.get("task_id")),int(n.get("trial_id")),int(n.get("seed"))),checkpoint_count=int((spec.get("checkpoint_prefix") or {}).get("count") or 0))
    if dict(spec)!=actual: raise RecoveryIntegrityError("reconstructed source evidence differs from frozen admission specification")
    return actual

def admit(successor: Path, *, spec: Mapping[str,Any]) -> dict[str,Any]:
    actual=validate_spec(spec); marker=successor/"recovery-admission-completed.json"
    payload={"version":MARKER_VERSION,"transition":"recovery_admitted","recovery_spec_sha256":actual["recovery_spec_sha256"],"recovery_spec":actual}; payload["marker_sha256"]=_digest(payload)
    if marker.exists():
        if _read(marker)!=payload: raise RecoveryIntegrityError("existing admission marker conflicts")
        return payload
    stage=successor/".recovery-admission-staging"/actual["recovery_spec_sha256"]
    if stage.exists(): raise RecoveryIntegrityError("partial admission staging exists")
    stage.mkdir(parents=True); _atomic(stage/"spec.json",actual); _atomic(stage/"references.json",{"envelopes":actual["imported_envelopes"],"prefix":actual["checkpoint_prefix"],"pending":actual["pending"]}); _atomic(marker,payload)
    if _read(marker)!=payload: raise RecoveryIntegrityError("admission marker reload differs")
    return payload
