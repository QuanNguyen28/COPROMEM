"""Strict scored-artifact-to-ReasoningBank-Dynamic update boundary."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ...experiments.reme_copromem.evidence_contract import validate as validate_execution_evidence
from .appworld import ReasoningBank, sha256
from .checkpoints import ReasoningBankDynamicCheckpoints, UpdateCompletion
from .lifecycle import ReasoningBankLifecycle
from .retrieval_provenance import ContentAddressedStore, materialize, verify


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
        def retrieve(instruction: str, benchmark: str, metadata: Mapping[str, Any]) -> str:
            # Preserve the official lifecycle retrieval exactly, then persist
            # the normalized embedding and deterministic top-1 calculation it
            # consumed before the executor can observe any guidance.
            self.lifecycle.retrieve_for_instruction(instruction, benchmark, metadata)
            retrieval = self.lifecycle.last_retrieval
            vector = self.lifecycle.last_query_embedding
            if retrieval is None or vector is None:
                raise RuntimeError("ReasoningBank retrieval callback returned no provenance")
            base = {"task_id": str((identity or {}).get("task_id") or ""), "arm": str((identity or {}).get("arm") or ""),
                    "trial_id": (identity or {}).get("trial_id"), "seed": (identity or {}).get("seed"),
                    "trajectory_id": str((identity or {}).get("trajectory_id") or ""), "benchmark": benchmark,
                    "manifest_sha256": self.manifest_sha256, "runtime_identity_sha256": self.runtime_identity_sha256,
                    "registry_sha256": self.registry_sha256}
            guidance, record = materialize(bank=self.lifecycle.bank, query=instruction, query_vector=vector,
                                            store=self.store, path=path, identity=base,
                                            embedding=self.embedding_identity)
            # Ensure an accidental pre-dispatch mutation is caught before the
            # executor receives model-visible memory text.
            if self.lifecycle.bank.state()["semantic_state_sha256"] != record["pre_state_sha256"]:
                raise RuntimeError("ReasoningBank retrieval mutated Dynamic state")
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
                   expected_bank_sha256=self.lifecycle.bank.state()["semantic_state_sha256"])
            if retrieval.get("identity", {}).get("trajectory_id") != durable.get("trajectory_id"):
                raise RuntimeError("ReasoningBank Dynamic retrieval trajectory identity mismatch")
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
