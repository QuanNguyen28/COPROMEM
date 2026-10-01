"""Strict scored-artifact-to-ReasoningBank-Dynamic update boundary."""
from __future__ import annotations

import hashlib
import json
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


class ReasoningBankDynamicRuntime:
    """Persist retrieval first, then issue only a strict post-score update.

    This is deliberately a thin adapter around the provider-agnostic lifecycle
    and checkpoint manager.  It neither uses an AppWorld official score for the
    self-judge nor substitutes a local lifecycle implementation.
    """

    def __init__(self, *, lifecycle: ReasoningBankLifecycle, initial_bank: ReasoningBank,
                 checkpoints: ReasoningBankDynamicCheckpoints, run_root: Path,
                 registry_sha256: str, manifest_sha256: str = "", runtime_identity_sha256: str = "",
                 embedding_identity: Mapping[str, Any] | None = None) -> None:
        self.lifecycle = lifecycle
        self.initial_bank = ReasoningBank.restore(initial_bank.state())
        self.checkpoints = checkpoints
        self.run_root = run_root.resolve()
        self.registry_sha256 = registry_sha256
        self.manifest_sha256 = manifest_sha256
        self.runtime_identity_sha256 = runtime_identity_sha256
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

    def strict_post_score_callback(self, retrieval_path: Path):
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
            verify(path=retrieval_path, store=self.store,
                   expected_bank_sha256=self.lifecycle.bank.state()["semantic_state_sha256"],
                   require_prompt_binding=True)
            try:
                identity = canonical_identity(retrieval.get("identity") or {})
            except RetrievalProvenanceError as exc:
                raise RuntimeError("ReasoningBank Dynamic retrieval identity is malformed") from exc
            for field, artifact_field in (("trajectory_id", "trajectory_id"), ("task_id", "task_id"),
                                          ("arm", "arm"), ("trial_id", "trial_id"), ("seed", "seed")):
                if identity[field] != durable.get(artifact_field):
                    raise RuntimeError(f"ReasoningBank Dynamic artifact identity mismatch: {field}")
            if durable.get("runtime_identity_sha256") != identity["runtime_identity_sha256"]:
                raise RuntimeError("ReasoningBank Dynamic artifact runtime identity mismatch")
            if durable.get("execution_evidence_registry_sha256") != identity["registry_sha256"]:
                raise RuntimeError("ReasoningBank Dynamic artifact registry identity mismatch")
            manifest_path = self.run_root / "manifest.json"
            if (not manifest_path.is_file() or
                    hashlib.sha256(manifest_path.read_bytes()).hexdigest() != identity["manifest_sha256"]):
                raise RuntimeError("ReasoningBank Dynamic artifact manifest identity mismatch")
            rendered_sha256 = str((retrieval.get("guidance") or {}).get("rendered_sha256") or "")
            if durable.get("injected_memory_sha256") != rendered_sha256:
                raise RuntimeError("ReasoningBank artifact did not receive provenance-bound rendered guidance")
            if bool(durable.get("injected_memory_nonempty")) != bool(retrieval.get("guidance_nonempty")):
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
            if retrieval.get("query", {}).get("sha256") != sha256(instruction):
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
