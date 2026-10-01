"""Durable, fail-closed checkpoints for online ReasoningBank updates.

The ReasoningBank paper's online lifecycle is append-only.  This boundary adds
the missing custody rule for an AppWorld process: a scored trajectory is never
replayed, and an update that could have reached a provider is never guessed or
replayed after a crash.  It is intentionally provider-agnostic; callers inject
the official self-judge/extractor lifecycle and this class owns only durable
state transitions.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .appworld import ReasoningBank, load_state, sha256, write_state


VERSION = "reasoningbank-appworld-dynamic-checkpoint-v1"


class DynamicCheckpointError(RuntimeError):
    """A Dynamic update is missing, inconsistent, or ambiguous."""


def _bytes_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _atomic_json(path: Path, value: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(_canonical(dict(value)) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    try:
        descriptor = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:  # Windows fixture filesystems do not support directory fsync.
        pass
    return _bytes_hash(path)


def _fsync_parent(path: Path) -> None:
    try:
        descriptor = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:  # Windows fixture filesystems do not support directory fsync.
        pass


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DynamicCheckpointError(f"checkpoint is unreadable: {path.name}") from exc
    if not isinstance(value, dict):
        raise DynamicCheckpointError(f"checkpoint has wrong shape: {path.name}")
    return value


def _artifact_hash(artifact: Mapping[str, Any]) -> str:
    return sha256(dict(artifact))


@dataclass(frozen=True)
class UpdateCompletion:
    update_index: int
    trajectory_id: str
    marker_sha256: str
    post_state_sha256: str
    snapshot: Path


@dataclass(frozen=True)
class Reconciliation:
    completed: tuple[UpdateCompletion, ...]
    next_index: int
    next_trajectory_id: str | None
    restored_bank: ReasoningBank


class ReasoningBankDynamicCheckpoints:
    """Own ordered intent/snapshot/marker files for one Dynamic bank stream."""

    def __init__(self, *, root: Path, expected_trajectory_ids: Sequence[str], ledger_path: Path) -> None:
        self.root = root.resolve()
        self.expected = tuple(str(item) for item in expected_trajectory_ids)
        if len(self.expected) != len(set(self.expected)):
            raise ValueError("Dynamic update order has duplicate trajectory IDs")
        self.ledger_path = ledger_path.resolve()
        self.intents = self.root / "intents"
        self.snapshots = self.root / "snapshots"
        self.markers = self.root / "completion-markers"
        for directory in (self.intents, self.snapshots, self.markers):
            directory.mkdir(parents=True, exist_ok=True)

    def _intent_path(self, index: int) -> Path:
        return self.intents / f"{index:04d}.json"

    def _snapshot_path(self, index: int) -> Path:
        return self.snapshots / f"{index:04d}.json"

    def _marker_path(self, index: int) -> Path:
        return self.markers / f"{index:04d}.json"

    def _ledger_offset(self) -> int:
        return self.ledger_path.stat().st_size if self.ledger_path.exists() else 0

    def _settlements_between(self, offset: int, end_offset: int | None = None) -> list[str]:
        if not self.ledger_path.exists():
            return []
        payload = self.ledger_path.read_bytes()
        end = len(payload) if end_offset is None else end_offset
        if offset < 0 or end < offset or end > len(payload):
            raise DynamicCheckpointError("ledger offset is outside the durable ledger")
        settled: list[str] = []
        reserved: set[str] = set()
        for raw in payload[offset:end].splitlines():
            row = json.loads(raw)
            if row.get("event") == "reserve":
                reserved.add(str(row.get("id")))
            elif row.get("event") == "settle":
                call_id = str(row.get("id"))
                if call_id in reserved:
                    settled.append(call_id)
        if reserved - set(settled):
            raise DynamicCheckpointError("Dynamic update has an unresolved reservation")
        return settled

    @staticmethod
    def _semantic_equal(left: ReasoningBank, right: ReasoningBank) -> bool:
        return left.state()["semantic_state_sha256"] == right.state()["semantic_state_sha256"]

    def _verify_snapshot(self, path: Path, expected_hash: str) -> ReasoningBank:
        if not path.is_file() or _bytes_hash(path) != expected_hash:
            raise DynamicCheckpointError("Dynamic snapshot is missing or hash-inconsistent")
        try:
            first = load_state(path)
            # A separate restore models a clean verifier process and rejects
            # accidental dependence on an in-memory service object.
            second = ReasoningBank.restore(first.state())
        except Exception as exc:
            raise DynamicCheckpointError("Dynamic snapshot cannot be restored cleanly") from exc
        if not self._semantic_equal(first, second):
            raise DynamicCheckpointError("Dynamic verifier semantic mismatch")
        return second

    def reconcile(self, initial_bank: ReasoningBank) -> Reconciliation:
        """Read only durable records and restore the longest verified prefix."""
        bank = ReasoningBank.restore(initial_bank.state())
        predecessor: str | None = None
        completed: list[UpdateCompletion] = []
        for index, trajectory_id in enumerate(self.expected, 1):
            intent_path, snapshot_path, marker_path = (self._intent_path(index), self._snapshot_path(index), self._marker_path(index))
            present = tuple(path.exists() for path in (intent_path, snapshot_path, marker_path))
            if not any(present):
                # No later files may occur after the first absent update.
                later = [self._intent_path(i).exists() or self._snapshot_path(i).exists() or self._marker_path(i).exists()
                         for i in range(index + 1, len(self.expected) + 1)]
                if any(later):
                    raise DynamicCheckpointError("Dynamic marker order is not a contiguous prefix")
                return Reconciliation(tuple(completed), index, trajectory_id, bank)
            if not all(present):
                raise DynamicCheckpointError("Dynamic update is ambiguous: intent, snapshot, and marker must co-exist")
            intent, marker = _read_json(intent_path), _read_json(marker_path)
            if intent.get("version") != VERSION or marker.get("version") != VERSION:
                raise DynamicCheckpointError("Dynamic checkpoint version mismatch")
            if intent.get("ordered_update_index") != index or intent.get("trajectory_id") != trajectory_id:
                raise DynamicCheckpointError("Dynamic intent has wrong order or trajectory")
            if intent.get("pre_update_semantic_state_sha256") != bank.state()["semantic_state_sha256"]:
                raise DynamicCheckpointError("Dynamic intent predecessor state mismatch")
            if intent.get("predecessor_completion_marker_sha256") != predecessor:
                raise DynamicCheckpointError("Dynamic intent predecessor marker mismatch")
            intent_hash = _bytes_hash(intent_path)
            if marker.get("update_intent_sha256") != intent_hash or marker.get("predecessor_completion_marker_sha256") != predecessor:
                raise DynamicCheckpointError("Dynamic completion marker does not bind its intent/predecessor")
            if marker.get("ordered_update_index") != index or marker.get("trajectory_id") != trajectory_id:
                raise DynamicCheckpointError("Dynamic completion marker has wrong order or trajectory")
            snapshot = self._verify_snapshot(snapshot_path, str(marker.get("source_snapshot_sha256") or ""))
            if snapshot.state()["semantic_state_sha256"] != marker.get("post_update_semantic_state_sha256"):
                raise DynamicCheckpointError("Dynamic completion marker post-state mismatch")
            if marker.get("pre_update_semantic_state_sha256") != bank.state()["semantic_state_sha256"]:
                raise DynamicCheckpointError("Dynamic completion marker pre-state mismatch")
            # A marker is only valid after the provider settlements it names
            # are visibly settled in the append-only ledger.
            ids = marker.get("newly_settled_provider_ids")
            if not isinstance(ids, list) or len(ids) != len(set(ids)):
                raise DynamicCheckpointError("Dynamic marker settlement binding is malformed")
            next_intent = self._intent_path(index + 1)
            next_offset = None
            if next_intent.exists():
                next_offset = int(_read_json(next_intent).get("ledger_byte_offset", -1))
            if set(ids) != set(self._settlements_between(int(intent["ledger_byte_offset"]), next_offset)):
                raise DynamicCheckpointError("Dynamic marker settlement binding mismatch")
            bank = snapshot
            marker_hash = _bytes_hash(marker_path)
            completed.append(UpdateCompletion(index, trajectory_id, marker_hash,
                                              bank.state()["semantic_state_sha256"], snapshot_path))
            predecessor = marker_hash
        return Reconciliation(tuple(completed), len(self.expected) + 1, None, bank)

    def update(self, *, bank: ReasoningBank, initial_bank: ReasoningBank, trajectory: Mapping[str, Any],
               retrieval_record: Mapping[str, Any], evidence_journal_sha256: str,
               update: Callable[[], Any]) -> UpdateCompletion:
        """Write intent, invoke exactly one injected lifecycle call, then verify/mark."""
        state = self.reconcile(initial_bank)
        if state.next_trajectory_id is None:
            raise DynamicCheckpointError("all frozen Dynamic updates are already complete")
        trajectory_id = str(trajectory.get("trajectory_id") or "")
        if trajectory_id != state.next_trajectory_id:
            raise DynamicCheckpointError("attempted Dynamic update is not the next frozen trajectory")
        if not evidence_journal_sha256:
            raise DynamicCheckpointError("Dynamic update requires an evidence-journal hash")
        if state.restored_bank.state()["semantic_state_sha256"] != bank.state()["semantic_state_sha256"]:
            raise DynamicCheckpointError("in-memory Dynamic bank differs from its verified durable prefix")
        index = state.next_index
        intent_path = self._intent_path(index)
        if intent_path.exists():
            raise DynamicCheckpointError("duplicate Dynamic update intent")
        predecessor = state.completed[-1].marker_sha256 if state.completed else None
        intent = {
            "version": VERSION, "ordered_update_index": index, "trajectory_id": trajectory_id,
            "task_id": str(trajectory.get("task_id") or ""), "trial_id": int(trajectory.get("trial_id")),
            "seed": int(trajectory.get("seed")), "scored_artifact_sha256": _artifact_hash(trajectory),
            "evidence_journal_sha256": evidence_journal_sha256,
            "retrieval_record_sha256": sha256(dict(retrieval_record)),
            "pre_update_semantic_state_sha256": bank.state()["semantic_state_sha256"],
            "predecessor_completion_marker_sha256": predecessor,
            "ledger_byte_offset": self._ledger_offset(),
        }
        _atomic_json(intent_path, intent)
        # Any exception below leaves an intent and deliberately makes a restart
        # fail closed; a provider-backed update must never be reissued blindly.
        update_result = update()
        post = bank.state()["semantic_state_sha256"]
        snapshot_path = self._snapshot_path(index)
        write_state(snapshot_path, bank)
        _fsync_parent(snapshot_path)
        snapshot_hash = _bytes_hash(snapshot_path)
        verified = self._verify_snapshot(snapshot_path, snapshot_hash)
        verifier_path = self.root / "verifier" / f"{index:04d}.json"
        write_state(verifier_path, verified)
        _fsync_parent(verifier_path)
        verifier_hash = _bytes_hash(verifier_path)
        if verified.state()["semantic_state_sha256"] != post:
            raise DynamicCheckpointError("clean verifier has a different Dynamic semantic state")
        settlements = self._settlements_between(int(intent["ledger_byte_offset"]))
        marker = {
            "version": VERSION, "ordered_update_index": index, "trajectory_id": trajectory_id,
            "update_intent_sha256": _bytes_hash(intent_path),
            "predecessor_completion_marker_sha256": predecessor,
            "scored_artifact_sha256": intent["scored_artifact_sha256"],
            "evidence_journal_sha256": evidence_journal_sha256,
            "retrieval_record_sha256": intent["retrieval_record_sha256"],
            "pre_update_semantic_state_sha256": intent["pre_update_semantic_state_sha256"],
            "post_update_semantic_state_sha256": post,
            "source_snapshot": snapshot_path.name, "source_snapshot_sha256": snapshot_hash,
            "verifier_dump": verifier_path.name, "verifier_dump_sha256": verifier_hash,
            "newly_settled_provider_ids": settlements,
            "update_result_sha256": sha256(getattr(update_result, "__dict__", str(update_result))),
        }
        marker_path = self._marker_path(index)
        marker_hash = _atomic_json(marker_path, marker)
        return UpdateCompletion(index, trajectory_id, marker_hash, post, snapshot_path)
