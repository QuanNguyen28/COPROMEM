"""Hash-verified bank construction for the pinned AppWorld ReMe service.

The source at ``benchmark/appworld/appworld_react_agent.py`` first calls
``summary_task_memory`` and persists the returned ``memory_list`` with
``add_task_memory``. The same source clones a bank with the
``dump_memory``/``load_memory`` JSONL routes. This module deliberately uses
those exact legacy contracts, rather than the later ``reme_ai`` API.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
from typing import Any, Callable


Post = Callable[[str, str, dict[str, Any]], dict[str, Any]]


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def file_hash(path: pathlib.Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"official ReMe bank dump is absent: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _complete_marker_path(dump_file: pathlib.Path) -> pathlib.Path:
    return dump_file.with_name(f"{dump_file.stem}.complete.json")


def _write_complete_marker(dump_file: pathlib.Path, snapshot_hash: str, count: int) -> None:
    """Atomically attest that every frozen input reached the dumped bank."""
    marker = _complete_marker_path(dump_file)
    payload = {"version": 1, "snapshot_sha256": snapshot_hash,
               "snapshot_file_sha256": file_hash(dump_file), "construction_count": count}
    temporary = marker.with_suffix(marker.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, marker)


def _require_complete_marker(dump_file: pathlib.Path, expected_snapshot_hash: str | None = None,
                             expected_count: int | None = None) -> dict[str, Any]:
    marker = _complete_marker_path(dump_file)
    if not marker.is_file():
        raise RuntimeError("official ReMe shared-bank completion marker is absent")
    value = json.loads(marker.read_text(encoding="utf-8"))
    if (value.get("version") != 1 or value.get("snapshot_file_sha256") != file_hash(dump_file)
            or value.get("snapshot_sha256") != semantic_bank_hash(dump_file)):
        raise RuntimeError("official ReMe shared-bank completion marker is inconsistent")
    if expected_snapshot_hash is not None and value["snapshot_sha256"] != expected_snapshot_hash:
        raise RuntimeError("official ReMe shared-bank completion marker has the wrong snapshot")
    if expected_count is not None and value.get("construction_count") != expected_count:
        raise RuntimeError("official ReMe shared-bank completion marker has the wrong input count")
    return value


VECTOR_FLOAT32_TOLERANCE = 2.0e-8


def _bank_rows(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise RuntimeError(f"official ReMe bank dump is absent: {path}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def semantic_bank_hash(path: pathlib.Path) -> str:
    """Hash memory identity/content, excluding numerical vector serialization.

    The pinned in-memory store restores embeddings through float32 and its
    JSON dump changes at most one float32 ULP.  Vectors are verified separately
    in ``_assert_clone_equivalent``; this hash covers all decision-bearing
    records exactly without treating JSON float formatting as new memory.
    """
    rows = []
    for row in _bank_rows(path):
        rows.append({key: value for key, value in row.items() if key != "vector"})
    return canonical_hash(sorted(rows, key=lambda row: str(row.get("memory_id", ""))))


def _assert_clone_equivalent(source: pathlib.Path, clone: pathlib.Path) -> None:
    source_rows = {str(row.get("memory_id")): row for row in _bank_rows(source)}
    clone_rows = {str(row.get("memory_id")): row for row in _bank_rows(clone)}
    if set(source_rows) != set(clone_rows):
        raise RuntimeError("loaded ReMe clone changes the memory-id set")
    for memory_id, source_row in source_rows.items():
        clone_row = clone_rows[memory_id]
        if ({key: value for key, value in source_row.items() if key != "vector"} !=
                {key: value for key, value in clone_row.items() if key != "vector"}):
            raise RuntimeError("loaded ReMe clone changes memory content or metadata")
        left, right = source_row.get("vector"), clone_row.get("vector")
        if (left is None) != (right is None) or (isinstance(left, list) and len(left) != len(right)):
            raise RuntimeError("loaded ReMe clone changes vector shape")
        if isinstance(left, list) and any(abs(float(a) - float(b)) > VECTOR_FLOAT32_TOLERANCE for a, b in zip(left, right)):
            raise RuntimeError("loaded ReMe clone changes vectors beyond float32 round-trip tolerance")


def _append(path: pathlib.Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _summary_memories(response: dict[str, Any]) -> list[dict[str, Any]]:
    memories = (response.get("metadata") or {}).get("memory_list")
    if not isinstance(memories, list) or not all(isinstance(x, dict) for x in memories):
        raise RuntimeError("official ReMe summary lacks a valid metadata.memory_list")
    return memories


def construct_once(post: Post, base_url: str, trajectories: list[dict[str, Any]],
                   checkpoint: pathlib.Path, dump_file: pathlib.Path,
                   event: Callable[[dict[str, Any]], None]) -> tuple[str, int]:
    """Construct the shared bank once and make a byte-hashed JSONL snapshot."""
    states: dict[str, str] = {}
    prior: list[dict[str, Any]] = []
    if checkpoint.exists():
        prior = [json.loads(line) for line in checkpoint.read_text(encoding="utf-8").splitlines() if line]
        states = {str(row["trajectory_id"]): str(row["state"]) for row in prior}

    # Services are intentionally short-lived.  A restart after every durable
    # construction checkpoint must reuse the already-frozen source snapshot,
    # not silently create an empty in-memory builder bank.
    if dump_file.exists() and all(states.get(str(item["trajectory_id"])) == "persisted" for item in trajectories):
        snapshot_hash = semantic_bank_hash(dump_file)
        _require_complete_marker(dump_file, snapshot_hash, len(trajectories))
        event({"event": "reme_initial_bank_reused", "snapshot_sha256": snapshot_hash,
               "construction_count": len(trajectories), "snapshot_file_sha256": file_hash(dump_file)})
        return snapshot_hash, len(trajectories)

    for item in trajectories:
        trajectory_id = str(item["trajectory_id"])
        if states.get(trajectory_id) == "persisted":
            continue
        if states.get(trajectory_id) not in {None, "summarized"}:
            raise RuntimeError(f"unrecognized ReMe construction state for {trajectory_id}")
        if states.get(trajectory_id) is None:
            summary = post(base_url, "summary_task_memory", {
                "trajectories": [{"task_id": item["task_id"], "messages": item["task_history"],
                                  "score": item["after_score"]}],
                "success_threshold": 1.0, "enable_soft_comparison": True,
                "validation_threshold": 0.5,
            })
            memories = _summary_memories(summary)
            row = {"trajectory_id": trajectory_id, "task_id": item["task_id"], "state": "summarized",
                   "summary_sha256": canonical_hash(summary), "memory_list": memories,
                   "memory_count": len(memories)}
            _append(checkpoint, row); prior.append(row); states[trajectory_id] = "summarized"
        else:
            memories = next(row["memory_list"] for row in reversed(prior)
                            if row["trajectory_id"] == trajectory_id and row["state"] == "summarized")

        # The source agent makes this request even for a valid empty summary.
        added = post(base_url, "add_task_memory", {"memory_list": memories})
        row = {"trajectory_id": trajectory_id, "task_id": item["task_id"], "state": "persisted",
               "memory_sha256": canonical_hash(memories), "add_sha256": canonical_hash(added),
               "memory_count": len(memories)}
        _append(checkpoint, row); prior.append(row); states[trajectory_id] = "persisted"
        event({"event": "reme_initial_bank_item", "trajectory_id": trajectory_id,
               "memory_count": len(memories), "memory_sha256": canonical_hash(memories)})

    if any(states.get(str(item["trajectory_id"])) != "persisted" for item in trajectories):
        raise RuntimeError("ReMe bank cannot be frozen before every input is persisted")
    dump_file.parent.mkdir(parents=True, exist_ok=True)
    dumped = post(base_url, "dump_memory", {"dump_file_path": str(dump_file)})
    snapshot_file_hash = file_hash(dump_file)
    snapshot_hash = semantic_bank_hash(dump_file)
    _write_complete_marker(dump_file, snapshot_hash, len(trajectories))
    event({"event": "reme_initial_bank_frozen", "snapshot_sha256": snapshot_hash,
           "snapshot_file_sha256": snapshot_file_hash, "construction_count": len(trajectories),
           "dump_response_sha256": canonical_hash(dumped)})
    return snapshot_hash, len(trajectories)


def load_clone(post: Post, base_url: str, dump_file: pathlib.Path,
               expected_snapshot_hash: str) -> str:
    """Load an exact snapshot into an isolated legacy service."""
    _require_complete_marker(dump_file, expected_snapshot_hash)
    if semantic_bank_hash(dump_file) != expected_snapshot_hash:
        raise RuntimeError("ReMe initial-bank snapshot hash changed before clone")
    post(base_url, "load_memory", {"load_file_path": str(dump_file), "clear_existing": True})
    clone_dump = dump_file.with_name(f"{dump_file.stem}.clone-check.jsonl")
    post(base_url, "dump_memory", {"dump_file_path": str(clone_dump)})
    _assert_clone_equivalent(dump_file, clone_dump)
    clone_hash = semantic_bank_hash(clone_dump)
    if clone_hash != expected_snapshot_hash:
        raise RuntimeError("loaded ReMe clone differs from shared initial bank")
    return clone_hash
