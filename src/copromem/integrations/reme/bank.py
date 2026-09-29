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

    # A persisted checkpoint alone proves that a request reached the service,
    # not that a fresh service can reconstruct its in-memory vector store.
    # Continuing would skip the settled item and silently build an incomplete
    # bank.  A durable dump/complete marker is therefore mandatory before a
    # process restart may reuse persisted construction records.
    if any(state == "persisted" for state in states.values()):
        raise RuntimeError("partial ReMe checkpoint lacks a durable shared-bank snapshot; replay would duplicate settled lifecycle or embedding calls")

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


def _fsync_directory(path: pathlib.Path) -> None:
    """Best-effort directory durability on filesystems that support it."""
    try:
        descriptor = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _fsync_file(path: pathlib.Path) -> None:
    """Durably flush a service-written dump before it becomes a checkpoint."""
    # Windows rejects fsync on a read-only descriptor.  Read/write mode does
    # not alter a service dump and preserves the same durability guarantee on
    # the E-backed Linux production filesystem.
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())
    _fsync_directory(path.parent)


def _snapshot_metadata(path: pathlib.Path, ordered: list[str], item: dict[str, Any]) -> dict[str, Any]:
    rows = _bank_rows(path)
    return {"version": 1, "snapshot_file": path.name, "snapshot_file_sha256": file_hash(path),
            "snapshot_sha256": semantic_bank_hash(path), "ordered_completed_items": ordered,
            "item_count": len(ordered), "memory_entry_count": len(rows),
            "vector_count": sum(isinstance(row.get("vector"), list) for row in rows),
            "source_trajectory_id": item["trajectory_id"], "source_history_sha256": item.get("history_sha256"),
            "lifecycle_output_hashes": item["lifecycle_output_hashes"]}


def _atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, separators=(",", ":")); handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, path); _fsync_directory(path.parent)


def _checkpoint_rows(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists(): return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def construct_durable_snapshot_bank(post: Post, builder_url: str, verifier_url: str,
                                    trajectories: list[dict[str, Any]], checkpoint: pathlib.Path,
                                    snapshots: pathlib.Path, event: Callable[[dict[str, Any]], None],
                                    capacity_guard: Callable[[str], None] | None = None) -> tuple[str, int]:
    """Build an upstream bank with durable, reload-tested state after each item.

    A checkpoint is authoritative only when its named snapshot exists and the
    snapshot metadata exactly covers the ordered completed prefix.  Ambiguous
    pre-marker snapshots fail closed instead of replaying provider calls.
    """
    def guarded_post(stage: str, base_url: str, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        if capacity_guard is not None:
            capacity_guard(stage)
        return post(base_url, endpoint, payload)

    rows = _checkpoint_rows(checkpoint); completed = [str(row["trajectory_id"]) for row in rows]
    expected = [str(item["trajectory_id"]) for item in trajectories]
    if completed != expected[:len(completed)] or len(completed) != len(set(completed)):
        raise RuntimeError("durable ReMe checkpoint order mismatch")
    intents = checkpoint.with_name(f"{checkpoint.stem}.intents.jsonl")
    started = [str(row["trajectory_id"]) for row in _checkpoint_rows(intents)
               if row.get("state") == "started"]
    # An intent is written before the first provider call for an item.  If the
    # process dies before its reload-tested snapshot/marker, replay could
    # duplicate a settled call.  It is intentionally an integrity stop, not a
    # best-effort retry mechanism.
    unresolved_started = set(started) - set(completed)
    if unresolved_started:
        raise RuntimeError("durable ReMe item intent lacks a completion snapshot marker")
    if any(trajectory_id not in expected for trajectory_id in started):
        raise RuntimeError("durable ReMe item intent references an unknown trajectory")
    snapshots.mkdir(parents=True, exist_ok=True)
    metadata_paths = sorted(snapshots.glob("after-*.json"))
    if len(metadata_paths) != len(completed):
        raise RuntimeError("durable ReMe checkpoint/snapshot count mismatch")
    if completed:
        metadata = json.loads(metadata_paths[-1].read_text(encoding="utf-8")); snapshot = snapshots / metadata["snapshot_file"]
        if (metadata.get("ordered_completed_items") != completed or metadata.get("item_count") != len(completed)
                or not snapshot.is_file() or metadata.get("snapshot_file_sha256") != file_hash(snapshot)
                or metadata.get("snapshot_sha256") != semantic_bank_hash(snapshot)):
            raise RuntimeError("durable ReMe snapshot metadata mismatch")
        guarded_post("restore_snapshot", builder_url, "load_memory", {"load_file_path": str(snapshot), "clear_existing": True})
        event({"event": "reme_durable_snapshot_restored", "item_count": len(completed), "snapshot_sha256": metadata["snapshot_sha256"]})
    for index, item in enumerate(trajectories[len(completed):], len(completed) + 1):
        if capacity_guard is not None:
            capacity_guard("construction_item")
        _append(intents, {"trajectory_id": str(item["trajectory_id"]), "state": "started",
                          "ordered_index": index, "history_sha256": item.get("history_sha256")})
        summary = guarded_post("summary_task_memory", builder_url, "summary_task_memory", {"trajectories": [{"task_id": item["task_id"], "messages": item["task_history"], "score": item["after_score"]}], "success_threshold": 1.0, "enable_soft_comparison": True, "validation_threshold": 0.5})
        memories = _summary_memories(summary)
        added = guarded_post("add_task_memory", builder_url, "add_task_memory", {"memory_list": memories})
        item_for_metadata = {"trajectory_id": str(item["trajectory_id"]), "history_sha256": item.get("history_sha256"),
                             "lifecycle_output_hashes": {"summary_sha256": canonical_hash(summary), "add_sha256": canonical_hash(added)}}
        snapshot = snapshots / f"after-{index:04d}.jsonl"
        guarded_post("durable_snapshot", builder_url, "dump_memory", {"dump_file_path": str(snapshot)})
        # Verify both the bytes and a clean verifier-process reload before a
        # completion marker may attest this item.
        if not snapshot.is_file(): raise RuntimeError("durable ReMe snapshot dump is absent")
        _fsync_file(snapshot)
        metadata = _snapshot_metadata(snapshot, completed + [item_for_metadata["trajectory_id"]], item_for_metadata)
        verifier_dump = snapshots / f"verify-{index:04d}.jsonl"
        guarded_post("snapshot_reload_verification", verifier_url, "load_memory", {"load_file_path": str(snapshot), "clear_existing": True})
        guarded_post("snapshot_reload_verification", verifier_url, "dump_memory", {"dump_file_path": str(verifier_dump)})
        if not verifier_dump.is_file():
            raise RuntimeError("durable ReMe verifier snapshot dump is absent")
        _fsync_file(verifier_dump)
        if semantic_bank_hash(verifier_dump) != metadata["snapshot_sha256"]:
            raise RuntimeError("durable ReMe snapshot reload verification failed")
        _atomic_json(snapshots / f"after-{index:04d}.json", metadata)
        _append(checkpoint, {**item_for_metadata, "state": "completed", "snapshot_sha256": metadata["snapshot_sha256"],
                             "snapshot_file_sha256": metadata["snapshot_file_sha256"], "memory_entry_count": metadata["memory_entry_count"], "vector_count": metadata["vector_count"]})
        completed.append(item_for_metadata["trajectory_id"])
        event({"event": "reme_durable_item_completed", "trajectory_id": item_for_metadata["trajectory_id"], "item_count": len(completed),
               "snapshot_sha256": metadata["snapshot_sha256"], "memory_entry_count": metadata["memory_entry_count"], "vector_count": metadata["vector_count"]})
    if len(completed) != len(trajectories): raise RuntimeError("durable ReMe construction incomplete")
    final_path = snapshots / f"after-{len(completed):04d}.json"
    if not final_path.is_file():
        raise RuntimeError("durable ReMe final snapshot metadata is absent")
    final = json.loads(final_path.read_text(encoding="utf-8"))
    return str(final["snapshot_sha256"]), len(completed)


def freeze_durable_final_snapshot(snapshots: pathlib.Path, count: int,
                                  destination: pathlib.Path) -> str:
    """Publish the reload-verified final per-item snapshot as the shared bank."""
    metadata_path = snapshots / f"after-{count:04d}.json"
    if not metadata_path.is_file():
        raise RuntimeError("durable ReMe final snapshot metadata is absent")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    source = snapshots / str(metadata.get("snapshot_file", ""))
    if (metadata.get("item_count") != count or metadata.get("ordered_completed_items") is None
            or len(metadata["ordered_completed_items"]) != count or not source.is_file()
            or metadata.get("snapshot_file_sha256") != file_hash(source)
            or metadata.get("snapshot_sha256") != semantic_bank_hash(source)):
        raise RuntimeError("durable ReMe final snapshot metadata mismatch")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with source.open("rb") as origin, temporary.open("wb") as target:
        while chunk := origin.read(1024 * 1024):
            target.write(chunk)
        target.flush(); os.fsync(target.fileno())
    os.replace(temporary, destination); _fsync_directory(destination.parent)
    if (file_hash(destination) != metadata["snapshot_file_sha256"]
            or semantic_bank_hash(destination) != metadata["snapshot_sha256"]):
        raise RuntimeError("published ReMe final snapshot differs from durable snapshot")
    _write_complete_marker(destination, str(metadata["snapshot_sha256"]), count)
    return str(metadata["snapshot_sha256"])


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
