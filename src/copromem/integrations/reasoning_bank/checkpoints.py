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
UPDATE_PROVIDER_ROLES = (
    "reasoningbank_judge",
    "reasoningbank_extraction",
    "reasoningbank_embedding",
)


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

    def _ledger_records(self) -> tuple[bytes, list[tuple[int, int, dict[str, Any]]]]:
        """Return append-only JSONL records with exact byte boundaries.

        Checkpoint markers bind a closed byte interval.  Parsing only a slice
        would accidentally accept a boundary in the middle of a JSON record,
        so all validation starts from this full-ledger index.
        """
        if not self.ledger_path.exists():
            return b"", []
        payload = self.ledger_path.read_bytes()
        records: list[tuple[int, int, dict[str, Any]]] = []
        cursor = 0
        for raw in payload.splitlines(keepends=True):
            start, cursor = cursor, cursor + len(raw)
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise DynamicCheckpointError("ledger contains malformed durable JSONL") from exc
            if not isinstance(row, dict):
                raise DynamicCheckpointError("ledger contains a non-object record")
            records.append((start, cursor, row))
        if cursor != len(payload):
            raise DynamicCheckpointError("ledger has an incomplete final record")
        return payload, records

    def _interval_records(self, start: int, end: int) -> tuple[bytes, list[tuple[int, int, dict[str, Any]]]]:
        payload, records = self._ledger_records()
        boundaries = {0, len(payload)} | {point for record in records for point in record[:2]}
        if start not in boundaries or end not in boundaries or start < 0 or end < start:
            raise DynamicCheckpointError("ledger settlement boundary is not a durable record boundary")
        return payload[start:end], [record for record in records if record[0] >= start and record[1] <= end]

    @staticmethod
    def _validate_update_roles(rows: list[tuple[int, int, dict[str, Any]]], ids: list[str]) -> None:
        """Validate one strict judge -> extractor -> document-embedding interval."""
        reserve: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        settle: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        settlement_order: list[str] = []
        for start, _end, row in rows:
            event, call_id = row.get("event"), str(row.get("id") or "")
            if event == "reserve":
                reserve.setdefault(call_id, []).append((start, row))
            elif event == "settle":
                settle.setdefault(call_id, []).append((start, row))
                settlement_order.append(call_id)
        if ids != settlement_order or len(ids) != len(set(ids)):
            raise DynamicCheckpointError("Dynamic marker settlement binding mismatch")
        observed_roles: list[str] = []
        for call_id in ids:
            reserves, settlements = reserve.get(call_id, []), settle.get(call_id, [])
            if len(reserves) != 1 or len(settlements) != 1:
                raise DynamicCheckpointError("Dynamic marker settlement has missing or duplicate reservation/settlement")
            reserve_start, reservation = reserves[0]
            settle_start, settlement = settlements[0]
            if reserve_start >= settle_start:
                raise DynamicCheckpointError("Dynamic marker settlement ordering is invalid")
            role = str(reservation.get("role") or "")
            if role != str(settlement.get("role") or "") or role not in UPDATE_PROVIDER_ROLES:
                raise DynamicCheckpointError("Dynamic marker settlement role is invalid")
            observed_roles.append(role)
        # The frozen lifecycle performs exactly one self-judge, one extraction,
        # and one document embedding, in that order.  This also rejects an
        # unbound lifecycle settlement inside an otherwise plausible interval.
        if observed_roles != list(UPDATE_PROVIDER_ROLES):
            raise DynamicCheckpointError("Dynamic marker settlement lifecycle order is invalid")

    def _validate_settlement_interval(self, *, start: int, end: int, ids: list[str], expected_hash: str | None) -> None:
        payload, rows = self._interval_records(start, end)
        if expected_hash is not None and hashlib.sha256(payload).hexdigest() != expected_hash:
            raise DynamicCheckpointError("Dynamic marker ledger interval hash mismatch")
        self._validate_update_roles(rows, ids)

    def _legacy_settlement_end_offset(self, start: int, ids: list[str]) -> int:
        """Derive the only safe legacy boundary from named settlement records.

        The old marker omitted an end offset.  It can be read only when every
        named ID occurs exactly once and the final named settlement has a
        deterministic byte end.  Later executor/retrieval rows are therefore
        outside the recovered interval rather than silently accepted.
        """
        _payload, records = self._ledger_records()
        if not ids or len(ids) != len(set(ids)):
            raise DynamicCheckpointError("Dynamic legacy marker settlement binding is malformed")
        ends: dict[str, list[int]] = {call_id: [] for call_id in ids}
        for _record_start, record_end, row in records:
            if row.get("event") == "settle" and str(row.get("id") or "") in ends:
                ends[str(row["id"])].append(record_end)
        if any(len(positions) != 1 for positions in ends.values()):
            raise DynamicCheckpointError("Dynamic legacy marker cannot derive a unique settlement boundary")
        end = max(position[0] for position in ends.values())
        if end < start:
            raise DynamicCheckpointError("Dynamic legacy marker settlement precedes its intent")
        return end

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
            if (not isinstance(intent.get("runtime_identity_sha256"), str) or
                    not isinstance(intent.get("runtime_identity_record_sha256"), str) or
                    intent["runtime_identity_sha256"] == intent["runtime_identity_record_sha256"] or
                    marker.get("runtime_identity_sha256") != intent["runtime_identity_sha256"] or
                    marker.get("runtime_identity_record_sha256") != intent["runtime_identity_record_sha256"]):
                raise DynamicCheckpointError("Dynamic checkpoint runtime identity domains are inconsistent")
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
            start = int(intent["ledger_byte_offset"])
            end_value = marker.get("ledger_settlement_end_byte_offset")
            interval_hash = marker.get("ledger_settlement_interval_sha256")
            if end_value is None and interval_hash is None:
                # Legacy recovery is deliberately narrow: it validates the
                # prefix ending at the last *named* settlement, not ledger EOF.
                end = self._legacy_settlement_end_offset(start, ids)
                self._validate_settlement_interval(start=start, end=end, ids=ids, expected_hash=None)
            elif isinstance(end_value, int) and isinstance(interval_hash, str):
                self._validate_settlement_interval(start=start, end=end_value, ids=ids, expected_hash=interval_hash)
            else:
                raise DynamicCheckpointError("Dynamic marker settlement boundary is malformed")
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
        semantic = trajectory.get("runtime_identity_sha256")
        record = trajectory.get("runtime_identity_record_sha256")
        if (not isinstance(semantic, str) or not isinstance(record, str) or len(semantic) != 64 or len(record) != 64 or semantic == record):
            raise DynamicCheckpointError("Dynamic update requires distinct semantic and record runtime identities")
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
            "runtime_identity_sha256": semantic, "runtime_identity_record_sha256": record,
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
        settlement_end = self._ledger_offset()
        interval_payload, _rows = self._interval_records(int(intent["ledger_byte_offset"]), settlement_end)
        # Validate before writing the marker so an unexpected provider call can
        # never be hidden by a future restart boundary.
        settlement_ids = [str(row.get("id")) for _start, _end, row in self._interval_records(
            int(intent["ledger_byte_offset"]), settlement_end)[1] if row.get("event") == "settle"]
        self._validate_settlement_interval(start=int(intent["ledger_byte_offset"]), end=settlement_end,
                                           ids=settlement_ids, expected_hash=None)
        marker = {
            "version": VERSION, "ordered_update_index": index, "trajectory_id": trajectory_id,
            "update_intent_sha256": _bytes_hash(intent_path),
            "predecessor_completion_marker_sha256": predecessor,
            "scored_artifact_sha256": intent["scored_artifact_sha256"],
            "evidence_journal_sha256": evidence_journal_sha256,
            "retrieval_record_sha256": intent["retrieval_record_sha256"],
            "runtime_identity_sha256": semantic, "runtime_identity_record_sha256": record,
            "pre_update_semantic_state_sha256": intent["pre_update_semantic_state_sha256"],
            "post_update_semantic_state_sha256": post,
            "source_snapshot": snapshot_path.name, "source_snapshot_sha256": snapshot_hash,
            "verifier_dump": verifier_path.name, "verifier_dump_sha256": verifier_hash,
            "newly_settled_provider_ids": settlement_ids,
            "ledger_settlement_end_byte_offset": settlement_end,
            "ledger_settlement_interval_sha256": hashlib.sha256(interval_payload).hexdigest(),
            "update_result_sha256": sha256(getattr(update_result, "__dict__", str(update_result))),
        }
        marker_path = self._marker_path(index)
        marker_hash = _atomic_json(marker_path, marker)
        return UpdateCompletion(index, trajectory_id, marker_hash, post, snapshot_path)
