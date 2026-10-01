"""Versioned, offline-verifiable provenance for ReasoningBank top-1 retrieval.

This module deliberately preserves the upstream no-abstention/top-1 algorithm.
It records the inputs and deterministic ranking required to prove that algorithm
later, without re-embedding a query or contacting any provider.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ...experiments.reme_copromem.prompt_memory import (
    count_exact_memory_slot,
    render_executor_memory_slot,
)
from .appworld import ReasoningBank, render_retrieval_guidance, sha256


VERSION = "reasoningbank-retrieval-provenance-v4"
DTYPE = "float64"
BYTE_ORDER = "little_endian"
NORMALIZATION = "unit_l2_float64_upstream_v1"
TIE_BREAK = "descending_cosine_then_append_order"
POLICY = "official_reasoningbank_top1_no_abstention_v1"


class RetrievalProvenanceError(RuntimeError):
    pass


_IDENTITY_FIELDS = (
    "trajectory_id", "task_id", "arm", "trial_id", "seed", "benchmark",
    "manifest_sha256", "runtime_identity_sha256", "registry_sha256",
)


def _sha256_field(value: Any, field: str) -> str:
    value = str(value or "")
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise RetrievalProvenanceError(f"retrieval identity has invalid {field}")
    return value


@dataclass(frozen=True)
class RetrievalIdentity:
    """The one immutable identity shared by retrieval, prompt sealing and update.

    This deliberately contains no instruction, memory, task payload, or provider
    response.  It is a public execution boundary: every field is frozen before
    the executor can make a request and is repeated in durable evidence.
    """
    trajectory_id: str
    task_id: str
    arm: str
    trial_id: int
    seed: int
    benchmark: str
    manifest_sha256: str
    runtime_identity_sha256: str
    registry_sha256: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RetrievalIdentity":
        if not isinstance(value, Mapping):
            raise RetrievalProvenanceError("retrieval identity is not a mapping")
        for field in ("trajectory_id", "task_id", "arm", "benchmark"):
            if not isinstance(value.get(field), str) or not str(value[field]).strip():
                raise RetrievalProvenanceError(f"retrieval identity lacks {field}")
        for field in _IDENTITY_FIELDS:
            if field not in value:
                raise RetrievalProvenanceError(f"retrieval identity lacks {field}")
        try:
            trial_id, seed = int(value["trial_id"]), int(value["seed"])
        except (TypeError, ValueError) as exc:
            raise RetrievalProvenanceError("retrieval identity has non-integer trial or seed") from exc
        if trial_id < 1:
            raise RetrievalProvenanceError("retrieval identity has invalid trial")
        return cls(
            trajectory_id=str(value["trajectory_id"]), task_id=str(value["task_id"]),
            arm=str(value["arm"]), trial_id=trial_id, seed=seed,
            benchmark=str(value["benchmark"]),
            manifest_sha256=_sha256_field(value["manifest_sha256"], "manifest_sha256"),
            runtime_identity_sha256=_sha256_field(value["runtime_identity_sha256"], "runtime_identity_sha256"),
            registry_sha256=_sha256_field(value["registry_sha256"], "registry_sha256"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in _IDENTITY_FIELDS}


def canonical_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and canonicalize identity before retrieval or prompt dispatch."""
    return RetrievalIdentity.from_mapping(value).as_dict()


@dataclass(frozen=True)
class RetrievalResult:
    """Immutable, typed view of a persisted top-1 retrieval record.

    ``raw_memory`` and ``rendered_guidance`` are intentionally separate
    values.  Only ``rendered_guidance`` may cross the executor callback.
    """
    query_sha256: str
    bank_sha256: str
    candidate_ids: tuple[str, ...]
    selected_experience_id: str | None
    raw_memory: str
    raw_memory_sha256: str
    rendered_guidance: str
    rendered_guidance_sha256: str
    policy_version: str
    renderer_version: str
    runtime_identity_sha256: str
    manifest_sha256: str
    registry_sha256: str


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("xb") as handle:
        handle.write(payload); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, path)
    try:
        directory = os.open(str(path.parent), os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    except OSError:
        pass


def _normal(vector: Sequence[float]) -> tuple[float, ...]:
    values = tuple(float(item) for item in vector)
    if not values or any(not math.isfinite(item) for item in values):
        raise RetrievalProvenanceError("embedding vector is empty, NaN, or infinite")
    length = math.sqrt(sum(item * item for item in values))
    if length == 0.0: raise RetrievalProvenanceError("embedding vector is zero")
    normalized = tuple(item / length for item in values)
    normalized_norm = math.sqrt(sum(item * item for item in normalized))
    if not math.isclose(normalized_norm, 1.0, rel_tol=1e-12, abs_tol=1e-12):
        raise RetrievalProvenanceError("float64 normalization is invalid")
    return normalized


def _vector_bytes(vector: Sequence[float]) -> bytes:
    return struct.pack("<" + "d" * len(vector), *vector)


def _vector_from_bytes(payload: bytes, dimension: int) -> tuple[float, ...]:
    if len(payload) != dimension * 8: raise RetrievalProvenanceError("vector byte length is invalid")
    values = tuple(float(item) for item in struct.unpack("<" + "d" * dimension, payload))
    if any(not math.isfinite(item) for item in values): raise RetrievalProvenanceError("stored vector contains NaN or infinity")
    norm = math.sqrt(sum(item * item for item in values))
    if not math.isclose(norm, 1.0, rel_tol=1e-12, abs_tol=1e-12): raise RetrievalProvenanceError("stored vector is not normalized")
    return values


class ContentAddressedStore:
    """E-backed immutable UTF-8 and upstream-float64 vector objects."""
    def __init__(self, root: Path) -> None: self.root = root.resolve()

    def _put(self, category: str, suffix: str, payload: bytes) -> dict[str, Any]:
        digest = hashlib.sha256(payload).hexdigest(); path = self.root / category / f"{digest}{suffix}"
        if path.exists():
            if not path.is_file() or _file_sha(path) != digest: raise RetrievalProvenanceError("content-addressed object mismatch")
        else: _atomic(path, payload)
        if _file_sha(path) != digest: raise RetrievalProvenanceError("content-addressed reload verification failed")
        return {"relative_locator": path.relative_to(self.root).as_posix(), "sha256": digest, "byte_length": len(payload)}

    def put_text(self, category: str, text: str) -> dict[str, Any]: return self._put(category, ".utf8", text.encode("utf-8"))
    def put_vector(self, vector: Sequence[float]) -> dict[str, Any]:
        values = _normal(vector); locator = self._put("vectors", ".f64le", _vector_bytes(values))
        return {**locator, "dimension": len(values), "dtype": DTYPE, "byte_order": BYTE_ORDER, "normalization": NORMALIZATION}

    def load_text(self, locator: Mapping[str, Any]) -> str:
        return self._load(locator).decode("utf-8")
    def load_vector(self, locator: Mapping[str, Any]) -> tuple[float, ...]:
        if locator.get("dtype") != DTYPE or locator.get("byte_order") != BYTE_ORDER or locator.get("normalization") != NORMALIZATION:
            raise RetrievalProvenanceError("stored vector format identity mismatch")
        return _vector_from_bytes(self._load(locator), int(locator.get("dimension") or 0))

    def _load(self, locator: Mapping[str, Any]) -> bytes:
        relative = str(locator.get("relative_locator") or "")
        path = (self.root / relative).resolve()
        try: path.relative_to(self.root)
        except ValueError as exc: raise RetrievalProvenanceError("content-addressed locator escapes store") from exc
        if not path.is_file(): raise RetrievalProvenanceError("content-addressed object is missing")
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != locator.get("sha256") or len(payload) != locator.get("byte_length"):
            raise RetrievalProvenanceError("content-addressed object hash mismatch")
        return payload


def _score(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right): raise RetrievalProvenanceError("candidate dimensionality differs from query")
    return sum(a * b for a, b in zip(left, right))


def _score_record(value: float) -> dict[str, str]:
    return {"float64_hex": float(value).hex(), "decimal": format(float(value), ".17g")}


def _record_sha256(record: Mapping[str, Any]) -> str:
    """Hash a record without its self-referential checksum."""
    body = dict(record)
    body.pop("record_sha256", None)
    return sha256(body)


def _binding_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".prompt-binding.json")


def typed_result(*, record: Mapping[str, Any], store: ContentAddressedStore) -> RetrievalResult:
    """Build the immutable retrieval view only after full offline validation."""
    guidance = record.get("guidance") or {}
    raw = store.load_text(guidance["raw_memory_bytes"])
    rendered = store.load_text(guidance["rendered_bytes"])
    identity = RetrievalIdentity.from_mapping(record.get("identity") or {})
    return RetrievalResult(
        query_sha256=str(record["query"]["sha256"]), bank_sha256=str(record["pre_state_sha256"]),
        candidate_ids=tuple(str(item["experience_id"]) for item in record.get("candidates") or []),
        selected_experience_id=(record.get("selection") or {}).get("selected_experience_id"),
        raw_memory=raw, raw_memory_sha256=str(guidance["raw_memory_sha256"]),
        rendered_guidance=rendered, rendered_guidance_sha256=str(guidance["rendered_sha256"]),
        policy_version=str(record["policy_version"]), renderer_version="reasoningbank-official-renderer-v1",
        runtime_identity_sha256=identity.runtime_identity_sha256,
        manifest_sha256=identity.manifest_sha256,
        registry_sha256=identity.registry_sha256,
    )


def materialize(*, bank: ReasoningBank, query: str, query_vector: Sequence[float], store: ContentAddressedStore,
                path: Path, identity: Mapping[str, Any], embedding: Mapping[str, Any],
                rendered_guidance: str, lifecycle_provenance: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Persist and reload-verify retrieval inputs before executor dispatch."""
    if path.exists(): raise RetrievalProvenanceError("duplicate retrieval provenance path")
    identity = canonical_identity(identity)
    # Scores are defined over immutable f64le payloads.  Never score a vector
    # before the store has applied its one normalization and we have reloaded
    # the exact bytes that restart verification will consume.
    query_object = store.put_text("queries", query); query_locator = store.put_vector(query_vector)
    query_norm = store.load_vector(query_locator)
    candidates = []
    for append_order, item in enumerate(bank.experiences):
        vector = store.put_vector(item.query_embedding); persisted_vector = store.load_vector(vector)
        text = "\n\n".join(item.memory_items); text_locator = store.put_text("memories", text)
        candidates.append({"append_order": append_order, "experience_id": item.experience_id,
                           "experience_sha256": sha256(item.as_dict()), "source_task_id": item.task_id,
                           "source_trajectory_sha256": item.source_trajectory_sha256,
                           "memory": text_locator, "vector": vector, "score": _score_record(_score(query_norm, persisted_vector))})
    ranked = sorted(candidates, key=lambda item: (-float.fromhex(item["score"]["float64_hex"]), int(item["append_order"])))
    selected = ranked[0] if ranked else None
    raw_memory = store.load_text(selected["memory"]) if selected else ""
    expected_rendered = render_retrieval_guidance(raw_memory)
    lifecycle_selected = list(lifecycle_provenance.get("selected_experience_ids") or [])
    expected_selected = [selected["experience_id"]] if selected else []
    if lifecycle_selected != expected_selected:
        raise RetrievalProvenanceError("lifecycle and provenance selected different memories")
    if lifecycle_provenance.get("pre_state_sha256") != bank.state()["semantic_state_sha256"]:
        raise RetrievalProvenanceError("lifecycle retrieval bank identity mismatch")
    if lifecycle_provenance.get("query_sha256") != sha256(query):
        raise RetrievalProvenanceError("lifecycle retrieval query identity mismatch")
    if lifecycle_provenance.get("guidance_sha256") != sha256(raw_memory):
        raise RetrievalProvenanceError("lifecycle raw-memory identity mismatch")
    if rendered_guidance != expected_rendered:
        raise RetrievalProvenanceError("lifecycle rendered guidance differs from the pinned renderer")
    if lifecycle_provenance.get("rendered_prompt_memory_sha256") != sha256(rendered_guidance):
        raise RetrievalProvenanceError("lifecycle rendered-guidance identity mismatch")
    lifecycle_record = dict(lifecycle_provenance)
    record = {"version": VERSION, "policy_version": POLICY, "tie_break_rule": TIE_BREAK,
              "identity": identity, "embedding": {**dict(embedding), "normalization": NORMALIZATION, "dtype": DTYPE, "byte_order": BYTE_ORDER, "dimension": len(query_norm)},
              "query": {"sha256": sha256(query), "object": query_object, "vector": query_locator},
              "pre_state_sha256": bank.state()["semantic_state_sha256"], "candidates": ranked,
              "lifecycle_provenance": lifecycle_record,
              "selection": {"empty_bank": not bool(ranked), "selected_experience_id": selected["experience_id"] if selected else None,
                            "selected_rank": 1 if selected else None, "selected_score": selected["score"] if selected else None},
              "guidance": {
                  "raw_memory_bytes": store.put_text("raw-memory", raw_memory),
                  "raw_memory_sha256": sha256(raw_memory),
                  "rendered_bytes": store.put_text("rendered-guidance", rendered_guidance),
                  "rendered_sha256": sha256(rendered_guidance),
                  "executor_memory_slot_sha256": sha256(render_executor_memory_slot(rendered_guidance)),
                  "lifecycle_provenance_sha256": sha256(lifecycle_record),
              }}
    # Retain earlier reader fields as explicit aliases; v3 verification uses the
    # structured objects above rather than these convenience values.
    record.update({"guidance_nonempty": bool(rendered_guidance), "guidance_sha256": sha256(rendered_guidance),
                   "bank_pre_state_sha256": record["pre_state_sha256"]})
    record["pre_dispatch_record_sha256"] = sha256(record)
    record["record_sha256"] = _record_sha256(record)
    _atomic(path, _canonical(record) + b"\n")
    verify(path=path, store=store, expected_bank_sha256=bank.state()["semantic_state_sha256"])
    return rendered_guidance, record


def bind_initial_prompt(*, path: Path, store: ContentAddressedStore, messages: Any,
                        callback_guidance: str, identity: Mapping[str, Any]) -> dict[str, Any]:
    """Seal exact post-prompt construction before the first executor call.

    A valid existing binding is immutable and idempotent; a conflicting one is
    a pre-dispatch integrity error rather than an opportunity to rewrite it.
    """
    record = verify(path=path, store=store)
    guidance = record["guidance"]
    rendered = store.load_text(guidance["rendered_bytes"])
    if callback_guidance != rendered:
        raise RetrievalProvenanceError("executor callback did not receive rendered guidance")
    expected_identity = canonical_identity(record.get("identity") or {})
    identity = canonical_identity(identity)
    if identity != expected_identity:
        mismatch = next(key for key in _IDENTITY_FIELDS if identity.get(key) != expected_identity.get(key))
        raise RetrievalProvenanceError(f"prompt binding identity mismatch: {mismatch}")
    slot = render_executor_memory_slot(rendered)
    occurrences = count_exact_memory_slot(messages, slot)
    expected_occurrences = 1 if rendered else 0
    if occurrences != expected_occurrences:
        raise RetrievalProvenanceError("executor prompt has an unexpected memory-slot occurrence count")
    binding = {
        "version": "reasoningbank-initial-prompt-binding-v1",
        "trajectory_identity": identity,
        "retrieval_pre_dispatch_sha256": record["pre_dispatch_record_sha256"],
        "raw_memory_sha256": guidance["raw_memory_sha256"],
        "rendered_guidance_sha256": guidance["rendered_sha256"],
        "callback_guidance_sha256": sha256(callback_guidance),
        "executor_memory_slot_sha256": sha256(slot),
        "memory_slot_occurrences": occurrences,
        "initial_prompt_messages_sha256": sha256(messages),
        "runtime_identity_sha256": identity["runtime_identity_sha256"],
        "manifest_sha256": identity["manifest_sha256"],
        "registry_sha256": identity["registry_sha256"],
    }
    binding["binding_sha256"] = sha256(binding)
    target = _binding_path(path)
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RetrievalProvenanceError("existing prompt binding is unreadable") from exc
        if existing != binding:
            raise RetrievalProvenanceError("existing prompt binding conflicts with immutable retrieval")
    else:
        _atomic(target, _canonical(binding) + b"\n")
    if json.loads(target.read_text(encoding="utf-8")) != binding:
        raise RetrievalProvenanceError("prompt binding reload verification failed")
    updated = dict(record)
    reference = {"relative_locator": target.relative_to(path.parent).as_posix(),
                 "sha256": _file_sha(target), "binding_sha256": binding["binding_sha256"]}
    prior = updated.get("prompt_binding")
    if prior is not None and prior != reference:
        raise RetrievalProvenanceError("retrieval record prompt binding conflicts")
    if prior is None:
        updated["prompt_binding"] = reference
        updated["record_sha256"] = _record_sha256(updated)
        _atomic(path, _canonical(updated) + b"\n")
    verified = verify(path=path, store=store, require_prompt_binding=True)
    return dict(verified["prompt_binding"])


def verify(*, path: Path, store: ContentAddressedStore, expected_bank_sha256: str | None = None,
           require_prompt_binding: bool = False) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8")); copy = dict(value); bound = copy.pop("record_sha256", None)
    if bound != sha256(copy) or value.get("version") != VERSION or value.get("policy_version") != POLICY: raise RetrievalProvenanceError("retrieval record hash or version mismatch")
    if expected_bank_sha256 is not None and value.get("pre_state_sha256") != expected_bank_sha256: raise RetrievalProvenanceError("retrieval bank snapshot mismatch")
    identity = canonical_identity(value.get("identity") or {})
    query = store.load_vector(value["query"]["vector"]); candidates = list(value.get("candidates") or [])
    reconstructed = []
    for candidate in candidates:
        vector = store.load_vector(candidate["vector"]); score = _score(query, vector)
        if candidate.get("score") != _score_record(score): raise RetrievalProvenanceError("recorded cosine score mismatch")
        if store.load_text(candidate["memory"]) == "": raise RetrievalProvenanceError("candidate memory is empty")
        reconstructed.append(candidate)
    expected = sorted(reconstructed, key=lambda item: (-float.fromhex(item["score"]["float64_hex"]), int(item["append_order"])))
    if candidates != expected: raise RetrievalProvenanceError("candidate ordering/tie-break mismatch")
    selected = expected[0] if expected else None; selection = value.get("selection") or {}
    if selection.get("empty_bank") != (not bool(expected)) or selection.get("selected_experience_id") != (selected["experience_id"] if selected else None): raise RetrievalProvenanceError("selected top-1 identity mismatch")
    lifecycle = value.get("lifecycle_provenance") or {}
    expected_selected = [selected["experience_id"]] if selected else []
    if list(lifecycle.get("selected_experience_ids") or []) != expected_selected:
        raise RetrievalProvenanceError("lifecycle selected-memory identity mismatch")
    if lifecycle.get("pre_state_sha256") != value.get("pre_state_sha256") or lifecycle.get("query_sha256") != value.get("query", {}).get("sha256"):
        raise RetrievalProvenanceError("lifecycle query or bank identity mismatch")
    if value.get("guidance", {}).get("lifecycle_provenance_sha256") != sha256(dict(lifecycle)):
        raise RetrievalProvenanceError("lifecycle provenance binding mismatch")
    raw_memory = store.load_text(value["guidance"]["raw_memory_bytes"])
    rendered = store.load_text(value["guidance"]["rendered_bytes"])
    expected_raw = store.load_text(selected["memory"]) if selected else ""
    if value["guidance"].get("raw_memory_sha256") != sha256(raw_memory) or raw_memory != expected_raw:
        raise RetrievalProvenanceError("raw selected-memory bytes mismatch")
    if value["guidance"].get("rendered_sha256") != sha256(rendered) or rendered != render_retrieval_guidance(raw_memory):
        raise RetrievalProvenanceError("rendered lifecycle guidance bytes mismatch")
    if lifecycle.get("guidance_sha256") != sha256(raw_memory) or lifecycle.get("rendered_prompt_memory_sha256") != sha256(rendered):
        raise RetrievalProvenanceError("lifecycle raw/rendered guidance binding mismatch")
    if value.get("guidance_sha256") != sha256(rendered):
        raise RetrievalProvenanceError("rendered guidance alias mismatch")
    if value["guidance"].get("executor_memory_slot_sha256") != sha256(render_executor_memory_slot(rendered)):
        raise RetrievalProvenanceError("executor prompt-memory rendering mismatch")
    if value.get("pre_dispatch_record_sha256") is None:
        raise RetrievalProvenanceError("retrieval record lacks pre-dispatch identity")
    binding_ref = value.get("prompt_binding")
    if binding_ref is None:
        if require_prompt_binding:
            raise RetrievalProvenanceError("retrieval record lacks sealed initial prompt binding")
    else:
        if not isinstance(binding_ref, Mapping):
            raise RetrievalProvenanceError("retrieval prompt binding is malformed")
        relative = str(binding_ref.get("relative_locator") or "")
        target = (path.parent / relative).resolve()
        try:
            target.relative_to(path.parent.resolve())
        except ValueError as exc:
            raise RetrievalProvenanceError("retrieval prompt binding escapes provenance directory") from exc
        if not target.is_file() or _file_sha(target) != binding_ref.get("sha256"):
            raise RetrievalProvenanceError("retrieval prompt binding is missing or hash-inconsistent")
        try:
            binding = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RetrievalProvenanceError("retrieval prompt binding is unreadable") from exc
        bound_hash = binding.pop("binding_sha256", None)
        if bound_hash != sha256(binding) or bound_hash != binding_ref.get("binding_sha256"):
            raise RetrievalProvenanceError("retrieval prompt binding hash mismatch")
        if binding.get("retrieval_pre_dispatch_sha256") != value.get("pre_dispatch_record_sha256"):
            raise RetrievalProvenanceError("retrieval prompt binding pre-dispatch record mismatch")
        if canonical_identity(binding.get("trajectory_identity") or {}) != identity:
            raise RetrievalProvenanceError("retrieval prompt binding identity mismatch")
        if binding.get("rendered_guidance_sha256") != sha256(rendered):
            raise RetrievalProvenanceError("retrieval prompt binding rendered guidance mismatch")
        if binding.get("executor_memory_slot_sha256") != sha256(render_executor_memory_slot(rendered)):
            raise RetrievalProvenanceError("retrieval prompt binding slot mismatch")
        expected_occurrences = 1 if rendered else 0
        if binding.get("memory_slot_occurrences") != expected_occurrences:
            raise RetrievalProvenanceError("retrieval prompt binding occurrence mismatch")
        if binding.get("initial_prompt_messages_sha256") in {None, ""}:
            raise RetrievalProvenanceError("retrieval prompt binding lacks prompt identity")
    typed_result(record=value, store=store)
    return value
