"""Durable, fail-closed checkpoints for official ReMe Dynamic updates.

This boundary is intentionally independent of an AppWorld worker.  The runner
supplies the already-durable scored artifact, the pinned official lifecycle
call, and local service dump/load functions.  It never retries a lifecycle
call: an intent without a reload-tested completion marker is ambiguous and
therefore terminal until an operator makes an explicit protocol decision.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from .bank import _assert_clone_equivalent, _fsync_directory, _fsync_file, canonical_hash, file_hash, semantic_bank_hash


class DynamicCheckpointError(RuntimeError):
    """A Dynamic update cannot safely be continued without replaying state."""


def _atomic_json(path: pathlib.Path, value: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    _fsync_directory(path.parent)
    return file_hash(path)


def _read_json(path: pathlib.Path, kind: str) -> dict[str, Any]:
    if not path.is_file():
        raise DynamicCheckpointError(f"ReMe Dynamic {kind} is absent: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DynamicCheckpointError(f"ReMe Dynamic {kind} is unreadable") from exc
    if not isinstance(value, dict):
        raise DynamicCheckpointError(f"ReMe Dynamic {kind} has the wrong shape")
    return value


def _sha256(path: pathlib.Path, label: str) -> str:
    if not path.is_file():
        raise DynamicCheckpointError(f"ReMe Dynamic {label} is absent")
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class DynamicUpdateIdentity:
    trajectory_id: str
    task_id: str
    trial_id: int
    seed: int

    @classmethod
    def from_result(cls, result: dict[str, Any]) -> "DynamicUpdateIdentity":
        try:
            return cls(str(result["trajectory_id"]), str(result["task_id"]), int(result["trial_id"]), int(result["seed"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise DynamicCheckpointError("scored ReMe Dynamic result lacks a stable identity") from exc

    def value(self) -> str:
        return f"{self.task_id}:trial={self.trial_id}:seed={self.seed}"


class ReMeDynamicCheckpointManager:
    """Persist and reconcile the exact ordered prefix of Dynamic updates.

    ``dump_current`` and ``load_current`` are local official-service operations.
    ``dump_verifier`` must use a separate clean verifier service.  They are
    injectable so all invariants can be tested without a service or provider.
    """

    VERSION = 1

    def __init__(self, *, root: pathlib.Path, ordered_updates: Iterable[DynamicUpdateIdentity],
                 dump_current: Callable[[pathlib.Path], None],
                 load_current: Callable[[pathlib.Path], None],
                 dump_verifier: Callable[[pathlib.Path, pathlib.Path], None],
                 official_update: Callable[[Any, float, Callable[[dict[str, Any]], None]], Any],
                 settled_ids: Callable[[int], list[str]] | None = None,
                 validate_settlements: Callable[[int, list[str]], None] | None = None,
                 validate_marker_settlements: Callable[[dict[str, Any]], None] | None = None,
                 verify_no_provider_calls: Callable[[int], None] | None = None,
                 ledger_offset: Callable[[], int] | None = None,
                 initial_semantic_hash: str | None = None,
                 validate_evidence: Callable[[dict[str, Any]], pathlib.Path] | None = None,
                 event: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.root = root.resolve()
        self.ordered = list(ordered_updates)
        if len({item.value() for item in self.ordered}) != len(self.ordered):
            raise ValueError("frozen ReMe Dynamic update order contains duplicate identities")
        self.dump_current, self.load_current, self.dump_verifier = dump_current, load_current, dump_verifier
        self.official_update = official_update
        self.settled_ids = settled_ids or (lambda _offset: [])
        self.validate_settlements = validate_settlements or (lambda _offset, _ids: None)
        self.validate_marker_settlements = validate_marker_settlements or (lambda _marker: None)
        self.verify_no_provider_calls = verify_no_provider_calls or (lambda _offset: None)
        self.ledger_offset = ledger_offset or (lambda: 0)
        self.initial_semantic_hash = initial_semantic_hash
        self.validate_evidence = validate_evidence
        self.event = event or (lambda _record: None)
        self.intents = self.root / "intents"
        self.markers = self.root / "markers"
        self.snapshots = self.root / "snapshots"
        for path in (self.intents, self.markers, self.snapshots):
            path.mkdir(parents=True, exist_ok=True)
        _fsync_directory(self.root)

    def _path(self, directory: pathlib.Path, index: int) -> pathlib.Path:
        return directory / f"update-{index:04d}.json"

    def _snapshot(self, index: int) -> pathlib.Path:
        return self.snapshots / f"update-{index:04d}.jsonl"

    def _verifier_dump(self, index: int, verifier: int) -> pathlib.Path:
        return self.snapshots / f"verify-{index:04d}-{verifier}.jsonl"

    def _expected(self, identity: DynamicUpdateIdentity, index: int) -> None:
        if index < 1 or index > len(self.ordered) or self.ordered[index - 1] != identity:
            raise DynamicCheckpointError("ReMe Dynamic update is outside the frozen order")

    def _journal(self, result: dict[str, Any]) -> tuple[pathlib.Path, str]:
        if self.validate_evidence is not None:
            path = self.validate_evidence(result)
            return path, _sha256(path, "execution-evidence journal")
        raw = result.get("execution_evidence_path")
        if not isinstance(raw, str) or not raw:
            raise DynamicCheckpointError("ReMe Dynamic scored artifact has no execution-evidence path")
        path = pathlib.Path(raw)
        if not path.is_absolute():
            raise DynamicCheckpointError("ReMe Dynamic execution-evidence path is not absolute")
        observed = _sha256(path, "execution-evidence journal")
        expected = result.get("execution_evidence_sha256")
        if not isinstance(expected, str) or expected != observed:
            raise DynamicCheckpointError("ReMe Dynamic execution-evidence journal hash mismatch")
        return path, observed

    @staticmethod
    def _retrieval_identity(result: dict[str, Any]) -> str:
        explicit = result.get("reme_retrieval_record_sha256") or result.get("upstream_retrieval_identity")
        if isinstance(explicit, str) and explicit:
            return explicit
        # The pinned upstream executor owns retrieval.  Persisting this stable
        # identity is preferable to manufacturing a local retrieval record.
        return canonical_hash({"kind": "official_upstream_retrieval", "trajectory_id": result.get("trajectory_id"),
                               "history_sha256": result.get("history_sha256")})

    def _validate_intent(self, intent: dict[str, Any], path: pathlib.Path, index: int,
                         identity: DynamicUpdateIdentity) -> None:
        if intent.get("version") != self.VERSION or intent.get("ordered_update_index") != index:
            raise DynamicCheckpointError("ReMe Dynamic intent order/version mismatch")
        if intent.get("identity") != identity.__dict__:
            raise DynamicCheckpointError("ReMe Dynamic intent identity mismatch")
        artifact = pathlib.Path(str(intent.get("scored_artifact_path", "")))
        journal = pathlib.Path(str(intent.get("execution_evidence_path", "")))
        if (not artifact.is_absolute() or not journal.is_absolute()
                or intent.get("scored_artifact_sha256") != _sha256(artifact, "scored artifact")
                or intent.get("execution_evidence_sha256") != _sha256(journal, "execution-evidence journal")):
            raise DynamicCheckpointError("ReMe Dynamic intent artifact/journal binding mismatch")
        if intent.get("intent_sha256") != file_hash(path):
            raise DynamicCheckpointError("ReMe Dynamic intent self-hash mismatch")

    def _write_intent(self, *, index: int, identity: DynamicUpdateIdentity, result: dict[str, Any],
                      artifact: pathlib.Path, pre_hash: str) -> tuple[pathlib.Path, dict[str, Any], str]:
        journal, journal_hash = self._journal(result)
        intent_path = self._path(self.intents, index)
        if intent_path.exists():
            raise DynamicCheckpointError("ReMe Dynamic duplicate update intent")
        provisional = {
            "version": self.VERSION, "ordered_update_index": index, "identity": identity.__dict__,
            "scored_artifact_path": str(artifact.resolve()), "scored_artifact_sha256": _sha256(artifact, "scored artifact"),
            "execution_evidence_path": str(journal.resolve()), "execution_evidence_sha256": journal_hash,
            "retrieval_identity": self._retrieval_identity(result), "pre_update_semantic_sha256": pre_hash,
            "predecessor_completion_marker_sha256": self._predecessor_hash(index),
            "ledger_byte_offset": int(self.ledger_offset()),
        }
        # The self hash covers the bytes that will be written.  It is stored in
        # a sibling attestation to avoid a self-referential JSON fixed point.
        _atomic_json(intent_path, provisional)
        intent_hash = file_hash(intent_path)
        _atomic_json(intent_path.with_suffix(".sha256.json"), {"intent_sha256": intent_hash})
        value = _read_json(intent_path, "intent")
        value["intent_sha256"] = intent_hash
        return intent_path, value, intent_hash

    def _predecessor_hash(self, index: int) -> str | None:
        if index == 1:
            return None
        path = self._path(self.markers, index - 1)
        if not path.is_file():
            raise DynamicCheckpointError("ReMe Dynamic predecessor completion marker is absent")
        return file_hash(path)

    def complete(self, *, agent: Any, result: dict[str, Any], artifact_path: pathlib.Path) -> dict[str, Any]:
        """Execute one official post-score update exactly once after durable score."""
        artifact = artifact_path.resolve()
        identity = DynamicUpdateIdentity.from_result(result)
        try:
            index = self.ordered.index(identity) + 1
        except ValueError as exc:
            raise DynamicCheckpointError("ReMe Dynamic trajectory is absent from frozen update order") from exc
        self._expected(identity, index)
        state = self.reconcile()
        if index <= state["completed_count"]:
            raise DynamicCheckpointError("ReMe Dynamic callback would replay a completed update")
        if index != state["completed_count"] + 1:
            raise DynamicCheckpointError("ReMe Dynamic callback is out of order")
        pre_dump = self.snapshots / f"pre-{index:04d}.jsonl"
        self.dump_current(pre_dump)
        if not pre_dump.is_file():
            raise DynamicCheckpointError("ReMe Dynamic pre-update dump is absent")
        _fsync_file(pre_dump)
        pre_hash = semantic_bank_hash(pre_dump)
        if index == 1 and self.initial_semantic_hash is not None and pre_hash != self.initial_semantic_hash:
            raise DynamicCheckpointError("ReMe Dynamic first update does not start from the frozen initial bank")
        intent_path, intent, intent_hash = self._write_intent(index=index, identity=identity, result=result,
                                                               artifact=artifact, pre_hash=pre_hash)
        try:
            self.official_update(agent, float(result["after_score"]),
                                 lambda row: self.event({**row, "trajectory_id": identity.trajectory_id,
                                                         "service_identity": "reme-dynamic"}))
        except Exception:
            self.event({"event": "reme_dynamic_update_ambiguous", "ordered_update_index": index,
                        "intent_sha256": intent_hash})
            raise
        snapshot = self._snapshot(index)
        self.dump_current(snapshot)
        if not snapshot.is_file():
            raise DynamicCheckpointError("ReMe Dynamic post-update snapshot is absent")
        _fsync_file(snapshot)
        post_hash = semantic_bank_hash(snapshot)
        verifier = self._verifier_dump(index, 1)
        verifier_ledger_boundary = int(self.ledger_offset())
        self.dump_verifier(snapshot, verifier)
        self.verify_no_provider_calls(verifier_ledger_boundary)
        if not verifier.is_file():
            raise DynamicCheckpointError("ReMe Dynamic verifier dump is absent")
        _fsync_file(verifier)
        try:
            _assert_clone_equivalent(snapshot, verifier)
        except RuntimeError as exc:
            raise DynamicCheckpointError("ReMe Dynamic verifier bank equivalence failed") from exc
        if semantic_bank_hash(verifier) != post_hash:
            raise DynamicCheckpointError("ReMe Dynamic verifier semantic hash mismatch")
        marker_path = self._path(self.markers, index)
        newly_settled = list(self.settled_ids(int(intent["ledger_byte_offset"])))
        self.validate_settlements(int(intent["ledger_byte_offset"]), newly_settled)
        marker = {
            "version": self.VERSION, "ordered_update_index": index, "identity": identity.__dict__,
            "update_intent_sha256": intent_hash, "predecessor_completion_marker_sha256": self._predecessor_hash(index),
            "scored_artifact_sha256": intent["scored_artifact_sha256"],
            "execution_evidence_sha256": intent["execution_evidence_sha256"],
            "retrieval_identity": intent["retrieval_identity"], "pre_update_semantic_sha256": pre_hash,
            "post_update_semantic_sha256": post_hash, "source_snapshot": snapshot.name,
            "source_snapshot_sha256": file_hash(snapshot), "verifier_dump": verifier.name,
            "verifier_dump_sha256": file_hash(verifier),
            "newly_settled_lifecycle_or_embedding_ids": newly_settled,
        }
        _atomic_json(marker_path, marker)
        self.event({"event": "reme_dynamic_update_completed", "ordered_update_index": index,
                    "post_update_semantic_sha256": post_hash, "completion_marker_sha256": file_hash(marker_path)})
        return marker

    @staticmethod
    def verify_fixed_bank(snapshot: pathlib.Path, frozen_semantic_hash: str) -> None:
        """Reject a Fixed arm whose semantic state differs from its frozen clone."""
        if semantic_bank_hash(snapshot) != frozen_semantic_hash:
            raise DynamicCheckpointError("ReMe Fixed bank mutated outside the read-only contract")

    def callback(self, artifact_path: pathlib.Path) -> Callable[[Any, dict[str, Any], Any], None]:
        """Return the strict three-argument executor callback for one artifact."""
        def post_score(agent: Any, result: dict[str, Any], _world: Any = None) -> None:
            self.complete(agent=agent, result=result, artifact_path=artifact_path)
        return post_score

    def reconcile(self) -> dict[str, Any]:
        """Validate checkpoints read-only and expose the exact next update."""
        intents = sorted(path for path in self.intents.glob("update-*.json")
                         if not path.name.endswith(".sha256.json"))
        markers = sorted(self.markers.glob("update-*.json"))
        snapshots = sorted(self.snapshots.glob("update-*.jsonl"))
        if len(intents) != len({path.name for path in intents}) or len(markers) != len({path.name for path in markers}):
            raise DynamicCheckpointError("duplicate ReMe Dynamic checkpoint filename")
        if len(markers) > len(self.ordered) or len(intents) > len(self.ordered):
            raise DynamicCheckpointError("ReMe Dynamic checkpoint exceeds frozen order")
        completed = 0
        for index, identity in enumerate(self.ordered, 1):
            intent_path = self._path(self.intents, index)
            marker_path = self._path(self.markers, index)
            snapshot = self._snapshot(index)
            has_intent, has_marker, has_snapshot = intent_path.is_file(), marker_path.is_file(), snapshot.is_file()
            if not has_intent and not has_marker and not has_snapshot:
                break
            if not has_intent or not has_marker or not has_snapshot:
                raise DynamicCheckpointError("ReMe Dynamic checkpoint is ambiguous (intent/marker/snapshot mismatch)")
            intent = _read_json(intent_path, "intent")
            attestation = _read_json(intent_path.with_suffix(".sha256.json"), "intent attestation")
            if attestation.get("intent_sha256") != file_hash(intent_path):
                raise DynamicCheckpointError("ReMe Dynamic intent attestation mismatch")
            intent = {**intent, "intent_sha256": attestation["intent_sha256"]}
            self._validate_intent(intent, intent_path, index, identity)
            marker = _read_json(marker_path, "completion marker")
            if (marker.get("version") != self.VERSION or marker.get("ordered_update_index") != index
                    or marker.get("identity") != identity.__dict__
                    or marker.get("update_intent_sha256") != file_hash(intent_path)
                    or marker.get("predecessor_completion_marker_sha256") != self._predecessor_hash(index)
                    or marker.get("pre_update_semantic_sha256") != intent.get("pre_update_semantic_sha256")):
                raise DynamicCheckpointError("ReMe Dynamic completion marker binding mismatch")
            if (marker.get("source_snapshot") != snapshot.name or marker.get("source_snapshot_sha256") != file_hash(snapshot)
                    or marker.get("post_update_semantic_sha256") != semantic_bank_hash(snapshot)):
                raise DynamicCheckpointError("ReMe Dynamic completion snapshot mismatch")
            verifier = self.snapshots / str(marker.get("verifier_dump", ""))
            if not verifier.is_file() or marker.get("verifier_dump_sha256") != file_hash(verifier):
                raise DynamicCheckpointError("ReMe Dynamic verifier dump binding mismatch")
            try:
                _assert_clone_equivalent(snapshot, verifier)
            except RuntimeError as exc:
                raise DynamicCheckpointError("ReMe Dynamic verifier bank equivalence failed") from exc
            self.validate_marker_settlements(marker)
            completed = index
        # Files after the completed prefix are malformed even if their names sort later.
        expected_intents = {self._path(self.intents, index).name for index in range(1, completed + 1)}
        expected_markers = {self._path(self.markers, index).name for index in range(1, completed + 1)}
        expected_snapshots = {self._snapshot(index).name for index in range(1, completed + 1)}
        if {path.name for path in intents} != expected_intents or {path.name for path in markers} != expected_markers or {path.name for path in snapshots} != expected_snapshots:
            raise DynamicCheckpointError("ReMe Dynamic checkpoint contains an out-of-order or orphaned file")
        return {"completed_count": completed,
                "next_identity": self.ordered[completed].__dict__ if completed < len(self.ordered) else None,
                "latest_snapshot": str(self._snapshot(completed)) if completed else None,
                "latest_completion_marker_sha256": self._predecessor_hash(completed + 1) if completed else None}

    def restore_latest(self) -> dict[str, Any]:
        """Restore only a valid, reload-tested completed prefix; never replay."""
        state = self.reconcile()
        if not state["completed_count"]:
            return state
        snapshot = self._snapshot(int(state["completed_count"]))
        self.load_current(snapshot)
        # Two independent verifier dumps protect restart equivalence from a
        # process-local vector-store cache.
        first = self.snapshots / "restore-verifier-a.jsonl"
        second = self.snapshots / "restore-verifier-b.jsonl"
        verifier_ledger_boundary = int(self.ledger_offset())
        self.dump_verifier(snapshot, first)
        self.dump_verifier(snapshot, second)
        self.verify_no_provider_calls(verifier_ledger_boundary)
        _fsync_file(first); _fsync_file(second)
        try:
            _assert_clone_equivalent(snapshot, first)
            _assert_clone_equivalent(snapshot, second)
            _assert_clone_equivalent(first, second)
        except RuntimeError as exc:
            raise DynamicCheckpointError("ReMe Dynamic restored verifier equivalence failed") from exc
        return state
