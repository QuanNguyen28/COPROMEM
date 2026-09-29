"""Content-addressed, offline restart checkpoints for CoProMem v6.2 Dynamic.

This module deliberately has no executor, scorer, AppWorld, or provider
dependency.  It records only already-durable evidence and pure semantic
transaction outputs.  A restart therefore either loads one exact committed
prefix or fails closed; it never infers a state or repeats a call.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from ...contrastive_graph_v6 import digest


class CoProMemDynamicCheckpointError(RuntimeError):
    """A v6.2 Dynamic checkpoint chain is incomplete or inconsistent."""


VERSION = "copromem-v6.2-dynamic-prefix-v1"
TRANSITIONS = (
    "task_pre_state_frozen", "retrievals_materialized", "trajectories_complete",
    "batch_ready", "semantic_plan_persisted", "validation_persisted",
    "commit_persisted", "post_state_snapshot_persisted", "next_task_authorized",
    "run_reconciled",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _file_hash(path: Path) -> str:
    if not path.is_file():
        raise CoProMemDynamicCheckpointError(f"checkpoint file is absent: {path.name}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        # Directory fsync is not available on every supported Windows path;
        # the file itself is always flushed before replace.
        pass


def _atomic(path: Path, value: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = _canonical(value) + b"\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    _fsync_dir(path.parent)
    return hashlib.sha256(body).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CoProMemDynamicCheckpointError(f"checkpoint record is unreadable: {path.name}") from exc
    if not isinstance(value, dict):
        raise CoProMemDynamicCheckpointError("checkpoint record has wrong shape")
    record_hash = value.pop("record_sha256", None)
    if not isinstance(record_hash, str) or record_hash != digest(value):
        raise CoProMemDynamicCheckpointError("checkpoint record content hash mismatch")
    value["record_sha256"] = record_hash
    return value


class CoProMemDynamicCheckpointManager:
    """Own the exact ordered Dynamic task-state prefix.

    Callers supply hashes of already-validated retrievals, artifacts, evidence,
    plans, and validations.  The only persisted semantic content here is the
    canonical pre/post state needed for a restart.
    """

    def __init__(self, *, root: Path, manifest_sha256: str, source_identity_sha256: str,
                 registry_sha256: str, ordered_tasks: Iterable[str], fixed_initial_state: Mapping[str, Any],
                 dynamic_initial_state: Mapping[str, Any]) -> None:
        self.root = root.resolve()
        self.manifest_sha256 = str(manifest_sha256)
        self.source_identity_sha256 = str(source_identity_sha256)
        self.registry_sha256 = str(registry_sha256)
        self.tasks = tuple(str(item) for item in ordered_tasks)
        if not self.tasks or len(set(self.tasks)) != len(self.tasks):
            raise ValueError("frozen Dynamic task order must be nonempty and unique")
        self.fixed_initial_state = json.loads(json.dumps(fixed_initial_state, ensure_ascii=False, sort_keys=True))
        self.dynamic_initial_state = json.loads(json.dumps(dynamic_initial_state, ensure_ascii=False, sort_keys=True))
        self.root.mkdir(parents=True, exist_ok=True)
        self._initialise()

    @property
    def initial(self) -> Path:
        return self.root / "initial.json"

    def _initialise(self) -> None:
        payload = {
            "version": VERSION, "manifest_sha256": self.manifest_sha256,
            "source_identity_sha256": self.source_identity_sha256, "registry_sha256": self.registry_sha256,
            "ordered_tasks": list(self.tasks), "fixed_initial_state": self.fixed_initial_state,
            "fixed_initial_state_sha256": digest(self.fixed_initial_state),
            "dynamic_initial_state": self.dynamic_initial_state,
            "dynamic_initial_state_sha256": digest(self.dynamic_initial_state),
        }
        payload["record_sha256"] = digest(payload)
        if self.initial.exists():
            existing = _read(self.initial)
            if existing != payload:
                raise CoProMemDynamicCheckpointError("Dynamic checkpoint namespace identity drift")
            return
        _atomic(self.initial, payload)

    def _task_index(self, task: str) -> int:
        try:
            return self.tasks.index(task) + 1
        except ValueError as exc:
            raise CoProMemDynamicCheckpointError("task is outside the frozen Dynamic order") from exc

    def _task_root(self, task: str) -> Path:
        return self.root / "tasks" / f"{self._task_index(task):04d}-{task}"

    def _record_path(self, task: str, transition: str) -> Path:
        if transition not in TRANSITIONS:
            raise CoProMemDynamicCheckpointError("unknown Dynamic transition")
        return self._task_root(task) / f"{TRANSITIONS.index(transition) + 1:02d}-{transition}.json"

    def _snapshot_path(self, task: str, kind: str) -> Path:
        if kind not in {"pre", "post"}:
            raise ValueError("snapshot kind must be pre or post")
        return self._task_root(task) / f"{kind}-state.json"

    def _previous_hash(self, task: str, transition: str) -> str | None:
        task_index, transition_index = self._task_index(task), TRANSITIONS.index(transition)
        if transition_index:
            prior = self._record_path(task, TRANSITIONS[transition_index - 1])
            return _file_hash(prior)
        if task_index == 1:
            return _file_hash(self.initial)
        prior_task = self.tasks[task_index - 2]
        prior = self._record_path(prior_task, "next_task_authorized")
        return _file_hash(prior)

    def _write_snapshot(self, task: str, kind: str, state: Mapping[str, Any]) -> dict[str, str]:
        path = self._snapshot_path(task, kind)
        canonical_state = json.loads(json.dumps(state, ensure_ascii=False, sort_keys=True))
        payload = {"state": canonical_state, "semantic_state_sha256": digest(canonical_state)}
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing != payload:
                raise CoProMemDynamicCheckpointError("Dynamic snapshot conflicts with its immutable state")
        else:
            _atomic(path, payload)
        return {"path": str(path.resolve()), "file_sha256": _file_hash(path),
                "semantic_state_sha256": payload["semantic_state_sha256"]}

    def record(self, task: str, transition: str, **payload: Any) -> dict[str, Any]:
        """Atomically append one immutable, predecessor-bound transition."""
        index = self._task_index(task)
        body = {
            "version": VERSION, "task_id": task, "task_index": index, "transition": transition,
            "manifest_sha256": self.manifest_sha256, "source_identity_sha256": self.source_identity_sha256,
            "registry_sha256": self.registry_sha256,
            "predecessor_transition_file_sha256": self._previous_hash(task, transition), **payload,
        }
        body["record_sha256"] = digest(body)
        path = self._record_path(task, transition)
        if path.exists():
            existing = _read(path)
            if existing != body:
                raise CoProMemDynamicCheckpointError(f"immutable transition conflict: {task}/{transition}")
            return existing
        # No stage can skip an earlier transition.
        pos = TRANSITIONS.index(transition)
        if pos and not self._record_path(task, TRANSITIONS[pos - 1]).is_file():
            raise CoProMemDynamicCheckpointError("Dynamic transition predecessor is absent")
        _atomic(path, body)
        return body

    def freeze_task_pre_state(self, task: str, state: Mapping[str, Any]) -> dict[str, Any]:
        snapshot = self._write_snapshot(task, "pre", state)
        return self.record(task, "task_pre_state_frozen", pre_state_snapshot=snapshot,
                           pre_state_sha256=snapshot["semantic_state_sha256"])

    def snapshot_post_state(self, task: str, state: Mapping[str, Any], *, marker_sha256: str,
                            plan_sha256: str, validation_sha256: str) -> dict[str, Any]:
        snapshot = self._write_snapshot(task, "post", state)
        return self.record(task, "post_state_snapshot_persisted", post_state_snapshot=snapshot,
                           post_state_sha256=snapshot["semantic_state_sha256"], marker_sha256=marker_sha256,
                           plan_sha256=plan_sha256, validation_sha256=validation_sha256)

    def _validate_record(self, task: str, transition: str) -> dict[str, Any]:
        row = _read(self._record_path(task, transition))
        if (row.get("version") != VERSION or row.get("task_id") != task
                or row.get("task_index") != self._task_index(task)
                or row.get("transition") != transition
                or row.get("manifest_sha256") != self.manifest_sha256
                or row.get("source_identity_sha256") != self.source_identity_sha256
                or row.get("registry_sha256") != self.registry_sha256
                or row.get("predecessor_transition_file_sha256") != self._previous_hash(task, transition)):
            raise CoProMemDynamicCheckpointError("Dynamic transition identity or predecessor mismatch")
        return row

    @staticmethod
    def _load_snapshot(record: Mapping[str, Any], field: str) -> tuple[dict[str, Any], str]:
        snapshot = record.get(field)
        if not isinstance(snapshot, Mapping):
            raise CoProMemDynamicCheckpointError("Dynamic snapshot binding is absent")
        path = Path(str(snapshot.get("path", "")))
        if not path.is_absolute() or _file_hash(path) != snapshot.get("file_sha256"):
            raise CoProMemDynamicCheckpointError("Dynamic snapshot file hash mismatch")
        value = json.loads(path.read_text(encoding="utf-8"))
        state = value.get("state") if isinstance(value, Mapping) else None
        state_hash = value.get("semantic_state_sha256") if isinstance(value, Mapping) else None
        if not isinstance(state, dict) or state_hash != digest(state) or state_hash != snapshot.get("semantic_state_sha256"):
            raise CoProMemDynamicCheckpointError("Dynamic snapshot semantic state mismatch")
        return state, str(state_hash)

    def reconcile(self, *, ledger_reconciled: bool, fixed_current_state: Mapping[str, Any]) -> dict[str, Any]:
        """Read-only exact-prefix validation; return the sole next permitted task/stage."""
        if not ledger_reconciled:
            raise CoProMemDynamicCheckpointError("unresolved provider reservation blocks Dynamic restart")
        initial = _read(self.initial)
        if initial.get("fixed_initial_state_sha256") != digest(self.fixed_initial_state) or digest(fixed_current_state) != digest(self.fixed_initial_state):
            raise CoProMemDynamicCheckpointError("CoProMem Fixed state differs from frozen initial state")
        state = dict(self.dynamic_initial_state)
        completed = 0
        for task in self.tasks:
            present = [name for name in TRANSITIONS if self._record_path(task, name).is_file()]
            if not present:
                break
            positions = [TRANSITIONS.index(name) for name in present]
            if positions != list(range(len(positions))):
                raise CoProMemDynamicCheckpointError("Dynamic transition chain has a gap")
            for name in present:
                self._validate_record(task, name)
            pre = self._validate_record(task, "task_pre_state_frozen")
            pre_state, pre_hash = self._load_snapshot(pre, "pre_state_snapshot")
            if pre_hash != digest(state) or pre.get("pre_state_sha256") != pre_hash:
                raise CoProMemDynamicCheckpointError("Dynamic task pre-state does not match committed prefix")
            if "post_state_snapshot_persisted" not in present:
                return {"completed_task_count": completed, "next_task_id": task,
                        "next_transition": TRANSITIONS[len(present)], "dynamic_state": state,
                        "task_pre_state": pre_state}
            post = self._validate_record(task, "post_state_snapshot_persisted")
            state, post_hash = self._load_snapshot(post, "post_state_snapshot")
            if post.get("post_state_sha256") != post_hash:
                raise CoProMemDynamicCheckpointError("Dynamic post-state marker mismatch")
            if "next_task_authorized" not in present:
                return {"completed_task_count": completed, "next_task_id": task,
                        "next_transition": "next_task_authorized", "dynamic_state": state}
            completed += 1
        if completed == len(self.tasks):
            return {"completed_task_count": completed, "next_task_id": None,
                    "next_transition": "run_reconciled", "dynamic_state": state}
        return {"completed_task_count": completed, "next_task_id": self.tasks[completed],
                "next_transition": "task_pre_state_frozen", "dynamic_state": state}
