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
import struct
from pathlib import Path
from typing import Any, Mapping, Sequence

from .appworld import MEMORY_PROMPT, ReasoningBank, sha256


VERSION = "reasoningbank-retrieval-provenance-v2"
DTYPE = "float32"
BYTE_ORDER = "little_endian"
NORMALIZATION = "unit_l2_float32_v1"
TIE_BREAK = "descending_cosine_then_append_order"
POLICY = "official_reasoningbank_top1_no_abstention_v1"


class RetrievalProvenanceError(RuntimeError):
    pass


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
    packed = struct.pack("<" + "f" * len(values), *(item / length for item in values))
    rounded = struct.unpack("<" + "f" * len(values), packed)
    rounded_norm = math.sqrt(sum(item * item for item in rounded))
    if not math.isclose(rounded_norm, 1.0, abs_tol=2e-6):
        raise RetrievalProvenanceError("float32 normalization is invalid")
    return tuple(float(item) for item in rounded)


def _vector_bytes(vector: Sequence[float]) -> bytes:
    return struct.pack("<" + "f" * len(vector), *vector)


def _vector_from_bytes(payload: bytes, dimension: int) -> tuple[float, ...]:
    if len(payload) != dimension * 4: raise RetrievalProvenanceError("vector byte length is invalid")
    values = tuple(float(item) for item in struct.unpack("<" + "f" * dimension, payload))
    if any(not math.isfinite(item) for item in values): raise RetrievalProvenanceError("stored vector contains NaN or infinity")
    norm = math.sqrt(sum(item * item for item in values))
    if not math.isclose(norm, 1.0, abs_tol=2e-6): raise RetrievalProvenanceError("stored vector is not normalized")
    return values


class ContentAddressedStore:
    """E-backed immutable UTF-8 and float32 objects with reload verification."""
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
        values = _normal(vector); locator = self._put("vectors", ".f32le", _vector_bytes(values))
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


def _prompt_memory(guidance: str) -> str:
    return "" if not guidance else "Experience 1:\n When to use: Retrieved procedural guidance\n Content: " + guidance + "\n"


def materialize(*, bank: ReasoningBank, query: str, query_vector: Sequence[float], store: ContentAddressedStore,
                path: Path, identity: Mapping[str, Any], embedding: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Persist and reload-verify retrieval inputs before executor dispatch."""
    if path.exists(): raise RetrievalProvenanceError("duplicate retrieval provenance path")
    query_norm = _normal(query_vector); query_object = store.put_text("queries", query); query_locator = store.put_vector(query_norm)
    candidates = []
    for append_order, item in enumerate(bank.experiences):
        vector = store.put_vector(item.query_embedding); text = "\n\n".join(item.memory_items); text_locator = store.put_text("memories", text)
        candidates.append({"append_order": append_order, "experience_id": item.experience_id,
                           "experience_sha256": sha256(item.as_dict()), "source_task_id": item.task_id,
                           "source_trajectory_sha256": item.source_trajectory_sha256,
                           "memory": text_locator, "vector": vector, "score": _score_record(_score(query_norm, store.load_vector(vector)))})
    ranked = sorted(candidates, key=lambda item: (-float.fromhex(item["score"]["float64_hex"]), int(item["append_order"])))
    selected = ranked[0] if ranked else None
    guidance = store.load_text(selected["memory"]) if selected else ""
    record = {"version": VERSION, "policy_version": POLICY, "tie_break_rule": TIE_BREAK,
              "identity": dict(identity), "embedding": {**dict(embedding), "normalization": NORMALIZATION, "dtype": DTYPE, "byte_order": BYTE_ORDER, "dimension": len(query_norm)},
              "query": {"sha256": sha256(query), "object": query_object, "vector": query_locator},
              "pre_state_sha256": bank.state()["semantic_state_sha256"], "candidates": ranked,
              "selection": {"empty_bank": not bool(ranked), "selected_experience_id": selected["experience_id"] if selected else None,
                            "selected_rank": 1 if selected else None, "selected_score": selected["score"] if selected else None},
              "guidance": {"bytes": store.put_text("guidance", guidance), "sha256": sha256(guidance), "prompt_memory_sha256": sha256(_prompt_memory(guidance))}}
    # Retain v1 reader fields as explicit aliases; v2 verification uses the
    # structured objects above rather than these convenience values.
    record.update({"guidance_nonempty": bool(guidance), "guidance_sha256": sha256(guidance),
                   "bank_pre_state_sha256": record["pre_state_sha256"]})
    record["record_sha256"] = sha256(record)
    _atomic(path, _canonical(record) + b"\n")
    verify(path=path, store=store, expected_bank_sha256=bank.state()["semantic_state_sha256"])
    return guidance, record


def verify(*, path: Path, store: ContentAddressedStore, expected_bank_sha256: str | None = None) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8")); copy = dict(value); bound = copy.pop("record_sha256", None)
    if bound != sha256(copy) or value.get("version") != VERSION or value.get("policy_version") != POLICY: raise RetrievalProvenanceError("retrieval record hash or version mismatch")
    if expected_bank_sha256 is not None and value.get("pre_state_sha256") != expected_bank_sha256: raise RetrievalProvenanceError("retrieval bank snapshot mismatch")
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
    guidance = store.load_text(value["guidance"]["bytes"])
    if value["guidance"].get("sha256") != sha256(guidance) or guidance != (store.load_text(selected["memory"]) if selected else ""):
        raise RetrievalProvenanceError("guidance bytes mismatch")
    return value
