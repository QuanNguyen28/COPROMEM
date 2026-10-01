"""Immutable retrieval-to-prompt binding for CoProMem v6.2.2."""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from ...contrastive_graph_v6 import digest
from .runtime_identity_binding import RuntimeIdentityBindingError, artifact_domains


VERSION = "copromem-v6.2.2-retrieval-execution-binding-v1"


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("retrieval binding input has wrong shape")
    return value


def _atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    try:
        descriptor = os.open(str(path.parent), os.O_RDONLY)
    except OSError:
        descriptor = None
    if descriptor is not None:
        try: os.fsync(descriptor)
        except OSError: pass
        finally: os.close(descriptor)


def expected(*, artifact_path: Path, retrieval_path: Path,
             runtime_identity_record_path: Path) -> dict[str, Any]:
    artifact, retrieval = _load(artifact_path), _load(retrieval_path)
    guidance = retrieval.get("guidance")
    provenance = retrieval.get("provenance")
    query = retrieval.get("task_query")
    if not isinstance(guidance, str) or not isinstance(provenance, Mapping) or not isinstance(query, Mapping):
        raise ValueError("retrieval record is incomplete")
    if artifact.get("copromem_callback_guidance_sha256") != digest(guidance):
        raise ValueError("artifact callback guidance differs from retrieval")
    if artifact.get("copromem_callback_guidance_nonempty") is not bool(guidance):
        raise ValueError("artifact callback emptiness differs from retrieval")
    if artifact.get("injected_memory_sha256") != digest(guidance):
        raise ValueError("artifact injected-memory identity differs from retrieval")
    prompt_hash = artifact.get("initial_prompt_messages_sha256")
    visible_hash = artifact.get("model_visible_prompt_sha256")
    if not isinstance(prompt_hash, str) or prompt_hash != visible_hash:
        raise ValueError("artifact prompt identity is missing or inconsistent")
    if not runtime_identity_record_path.is_file():
        raise ValueError("runtime identity record is absent")
    runtime_record_sha = _file_sha(runtime_identity_record_path)
    runtime_record = _load(runtime_identity_record_path)
    runtime_semantic_sha = runtime_record.get("runtime_identity_sha256")
    try:
        artifact_runtime = artifact_domains(artifact)
    except RuntimeIdentityBindingError as exc:
        raise ValueError("artifact runtime identity domains are invalid") from exc
    if (artifact_runtime["runtime_identity_record_sha256"] != runtime_record_sha
            or artifact_runtime["runtime_identity_sha256"] != runtime_semantic_sha):
        raise ValueError("artifact runtime identity domains differ from frozen runtime")
    record = {
        "version": VERSION,
        "trajectory_id": artifact.get("trajectory_id"),
        "task_id": artifact.get("task_id"), "arm": artifact.get("arm"),
        "trial_id": artifact.get("trial_id"), "seed": artifact.get("seed"),
        "artifact_sha256": _file_sha(artifact_path),
        "artifact_history_sha256": artifact.get("history_sha256"),
        "retrieval_record_sha256": _file_sha(retrieval_path),
        "retrieval_semantic_sha256": digest(retrieval),
        "task_query_sha256": query.get("query_sha256"),
        "retrieval_provenance_sha256": provenance.get("retrieval_sha256"),
        "guidance_sha256": digest(guidance),
        "guidance_nonempty": bool(guidance),
        "initial_prompt_messages_sha256": prompt_hash,
        "model_visible_memory_binding_sha256": artifact.get("model_visible_memory_binding_sha256"),
        "runtime_identity_record_sha256": runtime_record_sha,
        "runtime_identity_semantic_sha256": runtime_semantic_sha,
    }
    record["binding_sha256"] = digest(record)
    return record


def create(*, artifact_path: Path, retrieval_path: Path, binding_path: Path,
           runtime_identity_record_path: Path) -> dict[str, Any]:
    record = expected(artifact_path=artifact_path, retrieval_path=retrieval_path,
                      runtime_identity_record_path=runtime_identity_record_path)
    if binding_path.exists():
        existing = _load(binding_path)
        if existing != record:
            raise ValueError("immutable retrieval execution binding conflict")
        return existing
    _atomic(binding_path, record)
    loaded = _load(binding_path)
    if loaded != record:
        raise ValueError("retrieval execution binding reload mismatch")
    return loaded


def validate(*, artifact_path: Path, retrieval_path: Path, binding_path: Path,
             runtime_identity_record_path: Path, state: Mapping[str, Any],
             registry: Mapping[str, Any],
             reproduce: Callable[[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]], str]) -> dict[str, Any]:
    binding = _load(binding_path)
    canonical_bytes = (json.dumps(binding, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":")) + "\n").encode("utf-8")
    if binding_path.read_bytes() != canonical_bytes:
        raise ValueError("retrieval execution binding bytes are non-canonical")
    observed = expected(artifact_path=artifact_path, retrieval_path=retrieval_path,
                        runtime_identity_record_path=runtime_identity_record_path)
    if binding != observed:
        raise ValueError("retrieval execution binding does not match immutable inputs")
    retrieval = _load(retrieval_path)
    guidance = reproduce(state, retrieval["task_query"], registry, retrieval["provenance"])
    if guidance != retrieval["guidance"] or digest(guidance) != binding["guidance_sha256"]:
        raise ValueError("retrieval cannot reproduce before restart admission")
    return binding
