"""Strict scored-artifact-to-ReasoningBank-Dynamic update boundary."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ...experiments.reme_copromem.evidence_contract import validate as validate_execution_evidence
from .appworld import ReasoningBank, sha256
from .checkpoints import ReasoningBankDynamicCheckpoints, UpdateCompletion
from .lifecycle import ReasoningBankLifecycle
from .retrieval_provenance import (
    ContentAddressedStore,
    RetrievalProvenanceError,
    bind_initial_prompt,
    canonical_identity,
    materialize,
    verify,
)
from .appworld import render_retrieval_guidance
from .recovery_admission import resolve_source_run
from ...experiments.reme_copromem.prompt_memory import (
    count_exact_memory_slot,
    render_executor_memory_slot,
)


@dataclass(frozen=True)
class VerifiedRetrievalReceipt:
    """Version-neutral verified retrieval facts consumed by dispatch/update."""
    mode: str
    identity: Mapping[str, Any]
    query_sha256: str
    pre_state_sha256: str
    candidate_order: tuple[str, ...]
    score_hex: tuple[str, ...]
    selected_experience_id: str | None
    rendered_guidance: str
    rendered_guidance_sha256: str
    source_vector_sha256s: tuple[str, ...]
    embedding_request_prohibited: bool
    provenance_path: Path
    provenance_sha256: str
    admission_reconstruction_sha256: str | None = None

    @property
    def receipt_sha256(self) -> str:
        return sha256({"mode": self.mode, "identity": dict(self.identity), "query_sha256": self.query_sha256,
                       "pre_state_sha256": self.pre_state_sha256, "candidate_order": self.candidate_order,
                       "score_hex": self.score_hex, "selected": self.selected_experience_id,
                       "guidance": self.rendered_guidance_sha256, "vectors": self.source_vector_sha256s,
                       "provenance": self.provenance_sha256, "admission": self.admission_reconstruction_sha256})


class ReasoningBankDynamicRuntime:
    """Persist retrieval first, then issue only a strict post-score update.

    This is deliberately a thin adapter around the provider-agnostic lifecycle
    and checkpoint manager.  It neither uses an AppWorld official score for the
    self-judge nor substitutes a local lifecycle implementation.
    """

    def __init__(self, *, lifecycle: ReasoningBankLifecycle, initial_bank: ReasoningBank,
                 checkpoints: ReasoningBankDynamicCheckpoints, run_root: Path,
                 registry_sha256: str, manifest_sha256: str = "", runtime_identity_sha256: str = "",
                 runtime_identity_record_sha256: str = "",
                 embedding_identity: Mapping[str, Any] | None = None) -> None:
        self.lifecycle = lifecycle
        self.initial_bank = ReasoningBank.restore(initial_bank.state())
        self.checkpoints = checkpoints
        self.run_root = run_root.resolve()
        self.registry_sha256 = registry_sha256
        self.manifest_sha256 = manifest_sha256
        self.runtime_identity_sha256 = runtime_identity_sha256
        self.runtime_identity_record_sha256 = runtime_identity_record_sha256
        self.embedding_identity = dict(embedding_identity or {})
        self.store = ContentAddressedStore(self.run_root / "reasoningbank-retrieval-objects")

    @staticmethod
    def _write_json(path: Path, value: Mapping[str, Any]) -> None:
        from .checkpoints import _atomic_json  # one atomic/fsync implementation
        _atomic_json(path, value)

    def retrieval_callback(self, path: Path, *, identity: Mapping[str, Any] | None = None):
        """Return the executor callback and durable retrieval-record writer."""
        path = path.resolve()
        # Validate the full frozen identity while the runner is still deciding
        # whether this trajectory may dispatch.  Do not wait until the prompt
        # is built (or an embedding/provider boundary has been reached).
        try:
            frozen_identity = canonical_identity(identity or {})
        except RetrievalProvenanceError as exc:
            raise RuntimeError("ReasoningBank retrieval identity is invalid before dispatch") from exc

        def retrieve(instruction: str, benchmark: str, metadata: Mapping[str, Any]) -> str:
            # Preserve the official lifecycle retrieval exactly, then persist
            # the normalized embedding and deterministic top-1 calculation it
            # consumed before the executor can observe any guidance.
            lifecycle_guidance = self.lifecycle.retrieve_for_instruction(instruction, benchmark, metadata)
            retrieval = self.lifecycle.last_retrieval
            vector = self.lifecycle.last_query_embedding
            if retrieval is None or vector is None:
                raise RuntimeError("ReasoningBank retrieval callback returned no provenance")
            if benchmark != frozen_identity["benchmark"]:
                raise RuntimeError("ReasoningBank retrieval benchmark differs from frozen identity")
            guidance, record = materialize(bank=self.lifecycle.bank, query=instruction, query_vector=vector,
                                            store=self.store, path=path, identity=frozen_identity,
                                            embedding=self.embedding_identity,
                                            rendered_guidance=lifecycle_guidance,
                                            lifecycle_provenance=retrieval.provenance)
            # Ensure an accidental pre-dispatch mutation is caught before the
            # executor receives model-visible memory text.
            if self.lifecycle.bank.state()["semantic_state_sha256"] != record["pre_state_sha256"]:
                raise RuntimeError("ReasoningBank retrieval mutated Dynamic state")
            if guidance != lifecycle_guidance:
                raise RuntimeError("ReasoningBank provenance altered lifecycle-rendered guidance")
            return guidance
        return retrieve

    def admission_precomputed_retrieval_callback(self, path: Path, *, admission: Mapping[str, Any],
                                                 identity: Mapping[str, Any]):
        """Use an admission-bound, persisted-vector retrieval without embedding.

        This is intentionally separate from the ordinary lifecycle callback.
        It is usable for exactly one frozen recovery key and treats the source
        objects as immutable read-only custody, never as new embedding input.
        """
        pending = admission.get("pending") if isinstance(admission, Mapping) else None
        if not isinstance(pending, Mapping) or not bool(pending.get("embedding_request_prohibited")):
            raise RuntimeError("precomputed retrieval is not bound by a validated admission")
        frozen = canonical_identity(identity); key = pending.get("key") or {}
        if (frozen["arm"], frozen["task_id"], frozen["trial_id"], frozen["seed"]) != (key.get("arm"), key.get("task_id"), key.get("trial_id"), key.get("seed")):
            raise RuntimeError("precomputed retrieval key differs from admission pending key")
        source = resolve_source_run(str(admission.get("source_run") or ""))
        source_path = source / str(pending.get("source_relative") or "")
        source_store = ContentAddressedStore(source / "reasoningbank-retrieval-objects")
        if not source_path.is_file(): raise RuntimeError("admission source retrieval is unavailable")
        def retrieve(instruction: str, benchmark: str, metadata: Mapping[str, Any]) -> str:
            if benchmark != frozen["benchmark"]: raise RuntimeError("precomputed retrieval benchmark differs")
            source_record = json.loads(source_path.read_text(encoding="utf-8"))
            if sha256(instruction) != source_record.get("query", {}).get("sha256"):
                raise RuntimeError("precomputed retrieval instruction differs from immutable source query")
            query = source_store.load_vector(source_record["query"]["vector"]); rebuilt = []
            for candidate in source_record.get("candidates") or []:
                item = dict(candidate); item["score"] = {"float64_hex": float(sum(a*b for a,b in zip(query, source_store.load_vector(item["vector"])))).hex(),
                                                           "decimal": format(float(sum(a*b for a,b in zip(query, source_store.load_vector(item["vector"])))), ".17g")}
                rebuilt.append(item)
            rebuilt.sort(key=lambda item: (-float.fromhex(item["score"]["float64_hex"]), int(item["append_order"])))
            if rebuilt != pending.get("candidates") or [x["experience_id"] for x in rebuilt] != pending.get("candidate_order"):
                raise RuntimeError("precomputed retrieval persisted-vector reconstruction differs from admission")
            if not rebuilt or rebuilt[0]["score"]["float64_hex"] != "0x1.0000000000001p+0":
                raise RuntimeError("precomputed retrieval corrected score differs from admission")
            if self.lifecycle.bank.state()["semantic_state_sha256"] != pending.get("pre_state_sha256"):
                raise RuntimeError("precomputed retrieval bank state differs from admission")
            guidance = source_record["guidance"]; raw = source_store.load_text(guidance["raw_memory_bytes"])
            rendered = source_store.load_text(guidance["rendered_bytes"])
            if render_retrieval_guidance(raw) != rendered or sha256(rendered) != pending.get("rendered_guidance_sha256"):
                raise RuntimeError("precomputed retrieval rendered guidance differs from canonical renderer")
            record = {"version": "reasoningbank-admission-precomputed-retrieval-v1",
                      "admission_reconstruction_sha256": pending.get("reconstruction_sha256"),
                      "source_retrieval_sha256": pending.get("source_sha256"), "identity": dict(frozen),
                      "query": {"sha256": source_record["query"]["sha256"], "vector": pending["query_vector"]},
                      "pre_state_sha256": pending.get("pre_state_sha256"), "candidates": rebuilt,
                      "candidate_order": pending.get("candidate_order"),
                      "selection": {"selected_experience_id": pending.get("selected_experience_id"),
                                    "selected_score": pending.get("selected_score")},
                      "guidance": {"raw_memory_sha256": pending.get("raw_memory_sha256"),
                                   "rendered_sha256": pending.get("rendered_guidance_sha256")},
                      "guidance_nonempty": bool(rendered),
                      "embedding_request_prohibited": True}
            record["pre_dispatch_record_sha256"] = sha256(record)
            record["record_sha256"] = sha256(record); self._write_json(path, record)
            return rendered
        return retrieve

    @staticmethod
    def _file_sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _admission_receipt(self, path: Path, admission: Mapping[str, Any], *, require_prompt_binding: bool) -> VerifiedRetrievalReceipt:
        """Verify a recovery retrieval independently from its callback result."""
        value = json.loads(path.read_text(encoding="utf-8")); body = dict(value); bound = body.pop("record_sha256", None)
        if value.get("version") != "reasoningbank-admission-precomputed-retrieval-v1" or bound != sha256(body):
            raise RuntimeError("precomputed retrieval record hash or version mismatch")
        pending = admission.get("pending") if isinstance(admission, Mapping) else None
        if not isinstance(pending, Mapping) or value.get("admission_reconstruction_sha256") != pending.get("reconstruction_sha256"):
            raise RuntimeError("precomputed retrieval is not bound to the admitted reconstruction")
        identity = canonical_identity(value.get("identity") or {})
        key = pending.get("key") or {}
        if (identity["arm"], identity["task_id"], identity["trial_id"], identity["seed"]) != (
                key.get("arm"), key.get("task_id"), key.get("trial_id"), key.get("seed")):
            raise RuntimeError("precomputed retrieval receipt key differs from admission")
        source = resolve_source_run(str(admission.get("source_run") or ""))
        source_path = source / str(pending.get("source_relative") or "")
        if not source_path.is_file() or self._file_sha256(source_path) != pending.get("source_sha256"):
            raise RuntimeError("precomputed retrieval source identity differs from admission")
        source_value = json.loads(source_path.read_text(encoding="utf-8"))
        source_store = ContentAddressedStore(source / "reasoningbank-retrieval-objects")
        query = source_store.load_vector(pending["query_vector"]); rebuilt = []
        for candidate in source_value.get("candidates") or []:
            item = dict(candidate); score = float(sum(a * b for a, b in zip(query, source_store.load_vector(item["vector"]))))
            item["score"] = {"float64_hex": score.hex(), "decimal": format(score, ".17g")}; rebuilt.append(item)
        rebuilt.sort(key=lambda item: (-float.fromhex(item["score"]["float64_hex"]), int(item["append_order"])))
        if rebuilt != pending.get("candidates") or value.get("candidates") != rebuilt:
            raise RuntimeError("precomputed retrieval candidate reconstruction differs")
        if value.get("candidate_order") != pending.get("candidate_order") or value.get("selection", {}).get("selected_experience_id") != pending.get("selected_experience_id"):
            raise RuntimeError("precomputed retrieval ordering or selection differs")
        if rebuilt and rebuilt[0]["score"]["float64_hex"] != "0x1.0000000000001p+0":
            raise RuntimeError("precomputed retrieval corrected score differs")
        rendered = self._admission_rendered_guidance(admission)
        if value.get("guidance", {}).get("rendered_sha256") != sha256(rendered):
            raise RuntimeError("precomputed retrieval guidance identity differs")
        reference = value.get("prompt_binding")
        if require_prompt_binding and not isinstance(reference, Mapping):
            raise RuntimeError("precomputed retrieval lacks sealed prompt binding")
        if isinstance(reference, Mapping):
            binding_path = path.parent / str(reference.get("relative_locator") or "")
            if not binding_path.is_file() or self._file_sha256(binding_path) != reference.get("sha256"):
                raise RuntimeError("precomputed retrieval prompt binding is missing or changed")
            binding = json.loads(binding_path.read_text(encoding="utf-8")); binding_body = dict(binding)
            binding_hash = binding_body.pop("binding_sha256", None)
            if binding_hash != sha256(binding_body) or binding_hash != reference.get("binding_sha256"):
                raise RuntimeError("precomputed retrieval prompt binding hash differs")
            if binding.get("retrieval_pre_dispatch_sha256") != value.get("pre_dispatch_record_sha256"):
                raise RuntimeError("precomputed prompt binding retrieval identity differs")
            if binding.get("receipt_sha256") != self._receipt_from_admission_value(path, value, pending, rendered).receipt_sha256:
                raise RuntimeError("precomputed prompt binding receipt identity differs")
        return self._receipt_from_admission_value(path, value, pending, rendered)

    def _receipt_from_admission_value(self, path: Path, value: Mapping[str, Any], pending: Mapping[str, Any], rendered: str) -> VerifiedRetrievalReceipt:
        vectors = [str(pending["query_vector"]["sha256"])] + [str(item["vector"]["sha256"]) for item in value.get("candidates") or []]
        return VerifiedRetrievalReceipt(
            mode="admission_precomputed", identity=canonical_identity(value.get("identity") or {}),
            query_sha256=str(value.get("query", {}).get("sha256") or ""),
            pre_state_sha256=str(value.get("pre_state_sha256") or ""),
            candidate_order=tuple(str(item) for item in value.get("candidate_order") or []),
            score_hex=tuple(str(item.get("score", {}).get("float64_hex") or "") for item in value.get("candidates") or []),
            selected_experience_id=value.get("selection", {}).get("selected_experience_id"),
            rendered_guidance=rendered, rendered_guidance_sha256=sha256(rendered),
            source_vector_sha256s=tuple(vectors), embedding_request_prohibited=True,
            provenance_path=path, provenance_sha256=str(value.get("pre_dispatch_record_sha256") or ""),
            admission_reconstruction_sha256=str(pending.get("reconstruction_sha256") or ""),
        )

    def _ordinary_receipt(self, path: Path, *, require_prompt_binding: bool) -> VerifiedRetrievalReceipt:
        value = verify(path=path, store=self.store,
                       expected_bank_sha256=self.lifecycle.bank.state()["semantic_state_sha256"],
                       require_prompt_binding=require_prompt_binding)
        rendered = self.store.load_text(value["guidance"]["rendered_bytes"])
        vectors = [str(value["query"]["vector"]["sha256"])] + [str(item["vector"]["sha256"]) for item in value.get("candidates") or []]
        return VerifiedRetrievalReceipt(
            mode="ordinary", identity=canonical_identity(value.get("identity") or {}),
            query_sha256=str(value["query"]["sha256"]), pre_state_sha256=str(value["pre_state_sha256"]),
            candidate_order=tuple(str(item["experience_id"]) for item in value.get("candidates") or []),
            score_hex=tuple(str(item["score"]["float64_hex"]) for item in value.get("candidates") or []),
            selected_experience_id=(value.get("selection") or {}).get("selected_experience_id"),
            rendered_guidance=rendered, rendered_guidance_sha256=sha256(rendered),
            source_vector_sha256s=tuple(vectors), embedding_request_prohibited=False,
            provenance_path=path, provenance_sha256=str(value.get("pre_dispatch_record_sha256") or ""),
        )

    def admission_prompt_binding_callback(self, path: Path, *, admission: Mapping[str, Any], identity: Mapping[str, Any]):
        """Seal a precomputed-recovery receipt before executor reservation."""
        frozen = canonical_identity(identity); path = path.resolve()
        pending = admission.get("pending") if isinstance(admission, Mapping) else None
        if not isinstance(pending, Mapping): raise RuntimeError("admission prompt binding lacks pending receipt")
        target = path.with_suffix(path.suffix + ".prompt-binding.json")
        def bind(messages: list[dict[str, Any]], callback_guidance: str) -> None:
            receipt = self._admission_receipt(path, admission, require_prompt_binding=False)
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("version") != "reasoningbank-admission-precomputed-retrieval-v1" or record.get("identity") != dict(frozen):
                raise RuntimeError("precomputed prompt binding provenance identity differs")
            if callback_guidance != self._admission_rendered_guidance(admission):
                raise RuntimeError("precomputed prompt callback guidance differs from receipt")
            slot = render_executor_memory_slot(callback_guidance)
            occurrences = count_exact_memory_slot(messages, slot)
            if occurrences != (1 if callback_guidance else 0):
                raise RuntimeError("precomputed prompt has an unexpected memory-slot occurrence count")
            payload = {"version": "reasoningbank-admission-prompt-binding-v1", "receipt_sha256": receipt.receipt_sha256,
                       "provenance_sha256": receipt.provenance_sha256,
                       "retrieval_pre_dispatch_sha256": record.get("pre_dispatch_record_sha256"),
                       "rendered_guidance_sha256": sha256(callback_guidance),
                       "callback_guidance_sha256": sha256(callback_guidance),
                       "executor_memory_slot_sha256": sha256(slot), "memory_slot_occurrences": occurrences,
                       "initial_prompt_messages_sha256": sha256(messages), "trajectory_identity": dict(frozen)}
            payload["binding_sha256"] = sha256(payload)
            if target.exists():
                if json.loads(target.read_text(encoding="utf-8")) != payload: raise RuntimeError("precomputed prompt binding conflicts")
            else: self._write_json(target, payload)
            if json.loads(target.read_text(encoding="utf-8")) != payload: raise RuntimeError("precomputed prompt binding reload differs")
            reference = {"relative_locator": target.relative_to(path.parent).as_posix(),
                         "sha256": self._file_sha256(target), "binding_sha256": payload["binding_sha256"]}
            current = json.loads(path.read_text(encoding="utf-8"))
            if current.get("prompt_binding") not in (None, reference): raise RuntimeError("precomputed retrieval prompt binding conflicts")
            if current.get("prompt_binding") is None:
                current["prompt_binding"] = reference; current.pop("record_sha256", None); current["record_sha256"] = sha256(current)
                self._write_json(path, current)
            self._admission_receipt(path, admission, require_prompt_binding=True)
        return bind

    @staticmethod
    def _admission_rendered_guidance(admission: Mapping[str, Any]) -> str:
        pending = admission["pending"]; source = resolve_source_run(str(admission["source_run"])); path = source / str(pending["source_relative"])
        record = json.loads(path.read_text(encoding="utf-8")); store = ContentAddressedStore(source / "reasoningbank-retrieval-objects")
        rendered = store.load_text(record["guidance"]["rendered_bytes"])
        if sha256(rendered) != pending["rendered_guidance_sha256"]: raise RuntimeError("admission rendered guidance hash differs")
        return rendered

    def strict_post_score_callback(self, retrieval_path: Path, *, admission: Mapping[str, Any] | None = None):
        """Return an ``execute_trajectory`` callback that propagates failures."""
        retrieval_path = retrieval_path.resolve()
        def callback(_agent: Any, result: Mapping[str, Any], world: Any) -> UpdateCompletion:
            # The executor already wrote its artifact. Reload and validate the
            # same durable evidence contract, never its transient return value.
            artifact_path = self.run_root / "artifacts" / str(result["task_id"]) / str(result["arm"]) / f"trial-{result['trial_id']}.json"
            if not artifact_path.is_file():
                raise RuntimeError("ReasoningBank Dynamic update lacks a durable scored artifact")
            durable = json.loads(artifact_path.read_text(encoding="utf-8"))
            validate_execution_evidence(durable, run_root=self.run_root,
                                        expected_registry_sha256=self.registry_sha256)
            if durable.get("trajectory_id") != result.get("trajectory_id"):
                raise RuntimeError("ReasoningBank Dynamic scored artifact identity drift")
            if not retrieval_path.is_file():
                raise RuntimeError("ReasoningBank Dynamic update lacks durable retrieval provenance")
            retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
            receipt = (self._admission_receipt(retrieval_path, admission, require_prompt_binding=True)
                       if admission is not None else self._ordinary_receipt(retrieval_path, require_prompt_binding=True))
            identity = dict(receipt.identity)
            for field, artifact_field in (("trajectory_id", "trajectory_id"), ("task_id", "task_id"),
                                          ("arm", "arm"), ("trial_id", "trial_id"), ("seed", "seed")):
                if identity[field] != durable.get(artifact_field):
                    raise RuntimeError(f"ReasoningBank Dynamic artifact identity mismatch: {field}")
            if durable.get("runtime_identity_sha256") != identity["runtime_identity_sha256"]:
                raise RuntimeError("ReasoningBank Dynamic artifact runtime identity mismatch")
            if durable.get("runtime_identity_record_sha256") != self.runtime_identity_record_sha256:
                raise RuntimeError("ReasoningBank Dynamic artifact runtime record identity mismatch")
            if durable.get("runtime_identity_sha256") == durable.get("runtime_identity_record_sha256"):
                raise RuntimeError("ReasoningBank Dynamic artifact substituted runtime identity domains")
            if durable.get("execution_evidence_registry_sha256") != identity["registry_sha256"]:
                raise RuntimeError("ReasoningBank Dynamic artifact registry identity mismatch")
            manifest_path = self.run_root / "manifest.json"
            if (not manifest_path.is_file() or
                    hashlib.sha256(manifest_path.read_bytes()).hexdigest() != identity["manifest_sha256"]):
                raise RuntimeError("ReasoningBank Dynamic artifact manifest identity mismatch")
            rendered_sha256 = receipt.rendered_guidance_sha256
            if durable.get("injected_memory_sha256") != rendered_sha256:
                raise RuntimeError("ReasoningBank artifact did not receive provenance-bound rendered guidance")
            if bool(durable.get("injected_memory_nonempty")) != bool(receipt.rendered_guidance):
                raise RuntimeError("ReasoningBank artifact guidance-presence binding mismatch")
            binding = retrieval.get("prompt_binding") or {}
            binding_path = retrieval_path.parent / str(binding.get("relative_locator") or "")
            try:
                binding_value = json.loads(binding_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError("ReasoningBank Dynamic prompt binding is unavailable") from exc
            if binding_value.get("initial_prompt_messages_sha256") != durable.get("initial_prompt_messages_sha256"):
                raise RuntimeError("ReasoningBank artifact initial prompt differs from sealed binding")
            if binding_value.get("callback_guidance_sha256") != durable.get("injected_memory_sha256"):
                raise RuntimeError("ReasoningBank artifact callback differs from sealed binding")
            if binding_value.get("receipt_sha256") not in (None, receipt.receipt_sha256):
                raise RuntimeError("ReasoningBank artifact receipt differs from sealed binding")
            # Seal the pre-dispatch retrieval with the artifact and exact
            # model-visible prompt binding before any provider-backed update.
            retrieval["execution_binding"] = {"scored_artifact_sha256": sha256(dict(durable)),
                "history_sha256": durable.get("history_sha256"), "execution_evidence_sha256": durable.get("execution_evidence_sha256"),
                "initial_prompt_messages_sha256": durable.get("initial_prompt_messages_sha256"),
                "model_visible_prompt_sha256": durable.get("model_visible_prompt_sha256"),
                "model_visible_memory_binding_sha256": durable.get("model_visible_memory_binding_sha256"),
                "injected_memory_sha256": durable.get("injected_memory_sha256")}
            copy = dict(retrieval); copy.pop("record_sha256", None); retrieval["record_sha256"] = sha256(copy)
            self._write_json(retrieval_path, retrieval)
            evidence_hash = str(durable.get("execution_evidence_sha256") or "")
            if not evidence_hash:
                raise RuntimeError("ReasoningBank Dynamic update lacks evidence-journal binding")
            instruction = str(world.task.instruction)
            if receipt.query_sha256 != sha256(instruction):
                raise RuntimeError("ReasoningBank Dynamic retrieval instruction mismatch")
            return self.checkpoints.update(
                bank=self.lifecycle.bank, initial_bank=self.initial_bank,
                trajectory=durable, retrieval_record=retrieval,
                evidence_journal_sha256=evidence_hash,
                update=lambda: self.lifecycle.update(task_id=str(durable["task_id"]), query=instruction,
                                                     trajectory=durable["history"]),
            )
        return callback

    def prompt_binding_callback(self, retrieval_path: Path, *, identity: Mapping[str, Any]):
        """Return the pre-LLM seal callback for one exact trajectory."""
        retrieval_path = retrieval_path.resolve()
        try:
            frozen_identity = canonical_identity(identity)
        except RetrievalProvenanceError as exc:
            raise RuntimeError("ReasoningBank prompt-binding identity is invalid before dispatch") from exc

        def bind(messages: list[dict[str, Any]], callback_guidance: str) -> None:
            bind_initial_prompt(path=retrieval_path, store=self.store, messages=messages,
                                callback_guidance=callback_guidance, identity=frozen_identity)

        return bind
