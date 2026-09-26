"""Durable, fail-closed acquisition evidence for a successor AppWorld run.

The journal is intentionally write-once.  It records every native action before
the next model request can be made, so an interrupted controller cannot leave a
charged acquisition call without an auditable trajectory terminal record.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .checkpoints import RunStore, digest


class AcquisitionIncomplete(RuntimeError):
    """Evaluation was requested without complete, method-specific acquisition."""


@dataclass(frozen=True)
class AcquisitionRef:
    task_id: str
    seed: int
    trajectory_index: int

    @property
    def key(self) -> str:
        return f"{self.task_id}--seed-{self.seed}--trajectory-{self.trajectory_index}"


class AcquisitionJournal:
    """Append-only per-trajectory records plus a strict evaluation admission gate."""

    def __init__(self, store: RunStore, ref: AcquisitionRef) -> None:
        self.store, self.ref = store, ref

    def start(self, *, task_manifest_sha256: str, base_prompt_sha256: str, tool_schema_sha256: str) -> None:
        self.store.write("acquisition_start", self.ref.key, {
            "task_id": self.ref.task_id, "seed": self.ref.seed,
            "trajectory_index": self.ref.trajectory_index,
            "task_manifest_sha256": task_manifest_sha256,
            "base_prompt_sha256": base_prompt_sha256,
            "tool_schema_sha256": tool_schema_sha256,
        })

    def action(self, index: int, *, code: str, native_output: Mapping[str, Any], completed: bool) -> None:
        # Action source is the reproducible raw trajectory.  Native output is
        # represented by a digest/status only: it may contain private task data.
        self.store.write("acquisition_actions", f"{self.ref.key}--{index:02d}", {
            "task_id": self.ref.task_id, "index": index, "code": code,
            "native_output_sha256": digest(dict(native_output)),
            "native_ok": bool(native_output.get("ok")), "completed": bool(completed),
        })

    def plan_action(self, index: int, *, code: str) -> None:
        """Persist returned tool arguments before crossing the native boundary."""
        self.store.write("acquisition_action_plans", f"{self.ref.key}--{index:02d}", {
            "task_id": self.ref.task_id, "index": index, "code": code,
        })

    def pending_plans(self) -> list[dict[str, Any]]:
        if self.store.root is None:
            return []
        completed = {path.stem for path in (self.store.root / "acquisition_actions").glob(f"{self.ref.key}--*.json")}
        return [self.store.read("acquisition_action_plans", path.stem)
                for path in sorted((self.store.root / "acquisition_action_plans").glob(f"{self.ref.key}--*.json"))
                if path.stem not in completed]

    def finish(self, *, official_score: Mapping[str, Any]) -> str | None:
        actions = []
        if self.store.root:
            paths = sorted((self.store.root / "acquisition_actions").glob(f"{self.ref.key}--*.json"))
            actions = [self.store.read("acquisition_actions", path.stem) for path in paths]
        trace_sha256 = digest({"start": self.store.read("acquisition_start", self.ref.key), "actions": actions})
        self.store.write("acquisition_scores", self.ref.key, {
            "task_id": self.ref.task_id, "official_score": dict(official_score),
            "raw_trajectory_sha256": trace_sha256, "action_count": len(actions),
        })
        return trace_sha256

    def admit_memory(self, *, method: str, provenance: str, memory_text: str) -> None:
        if method not in {"reme_fixed_faithful_adaptation", "reme_dynamic_faithful_adaptation", "copromem_v2"}:
            raise ValueError("unregistered memory method")
        if not provenance or not memory_text.strip() or memory_text.strip() in {"Shared acquisition evidence available.", "Shared acquisition failures retained."}:
            raise AcquisitionIncomplete("generic or unprovenanced memory is forbidden")
        if self.store.read("acquisition_scores", self.ref.key) is None:
            raise AcquisitionIncomplete("official acquisition score required before memory admission")
        self.store.write("acquisition_memories", f"{self.ref.key}--{method}", {
            "method": method, "provenance": provenance,
            "memory_sha256": digest(memory_text),
        })

    def approve_evaluation(self) -> dict[str, str]:
        score = self.store.read("acquisition_scores", self.ref.key)
        if score is None or not score.get("raw_trajectory_sha256") or not score.get("action_count"):
            raise AcquisitionIncomplete("complete trace and official score required")
        memories = {}
        for method in ("reme_fixed_faithful_adaptation", "reme_dynamic_faithful_adaptation", "copromem_v2"):
            item = self.store.read("acquisition_memories", f"{self.ref.key}--{method}")
            if item is None or not item.get("provenance"):
                raise AcquisitionIncomplete(f"missing method-specific {method} memory")
            memories[method] = item["memory_sha256"]
        if len(set(memories.values())) < 2:
            raise AcquisitionIncomplete("ReMe and CoProMem provenance/memory must be distinct")
        return {"raw_trajectory_sha256": score["raw_trajectory_sha256"], **memories}
