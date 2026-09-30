"""Fail-closed, content-addressed assembly for the v6.2 recovery prefix.

This module deliberately performs no dispatch.  It validates only immutable
source evidence and produces a single marker that a production runner can
consume before it acquires a lock or starts a service.
"""
from __future__ import annotations

import json
import os
import pathlib
from collections import Counter
from typing import Any, Mapping

from ...contrastive_graph_v6 import digest
from .recovery_import import RecoveryImportError, canonical_sha256, file_sha256
from .v62_recovery_custody import (LEGACY_ENVELOPE_SHA256, LEGACY_SOURCE_SHA256,
                                   build_mapping, validate_mapping)
from .v62_recovery_prefix import NEXT

VERSION = "v6.2-recovery-state-v1"
MARKER_NAME = "recovery-state.json"
COPRO_POST = "1cff4e8192f853d9e835e7e6054346867a7b53584f0c9d61ee13b757885d0b75"
REME_POST = "5871658adb09f4c74fc730aaa8c5e5a1025d5bd51187393b3e0a1cf3f7401a2a"
REME_INITIAL = "6c3bc799ec0beb034fd2b81ee0d5cbf6e89a14f3a5a39ebf70d34853686b00a0"
COPRO_FIXED_INITIAL = "add35eca3ccaa9780183a144328157db2c64b932e5b69a7e3d5b87fd4efc9448"


def _load(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecoveryImportError(f"unreadable recovery state: {path.name}") from exc
    if not isinstance(value, dict):
        raise RecoveryImportError("recovery state object has wrong shape")
    return value


def _host_path(value: str) -> pathlib.Path:
    """Resolve immutable E-backed evidence on Windows and WSL without guessing."""
    if value.startswith("/mnt/e/") and pathlib.Path("E:/").exists():
        return pathlib.Path("E:/" + value[len("/mnt/e/"):])
    return pathlib.Path(value)


def _atomic_json(path: pathlib.Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    try:
        descriptor = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        pass


def _read_checkpoint(path: pathlib.Path) -> dict[str, Any]:
    row = _load(path)
    actual = row.pop("record_sha256", None)
    if not isinstance(actual, str) or actual != digest(row):
        raise RecoveryImportError(f"checkpoint hash mismatch: {path.name}")
    row["record_sha256"] = actual
    return row


def _snapshot(path: pathlib.Path, expected_semantic: str) -> tuple[dict[str, Any], str]:
    value = _load(path)
    state = value.get("state")
    semantic = value.get("semantic_state_sha256")
    if not isinstance(state, dict) or semantic != digest(state) or semantic != expected_semantic:
        raise RecoveryImportError("CoProMem snapshot semantic identity mismatch")
    return state, file_sha256(path)


def _envelope_by_identity(envelopes: list[dict[str, Any]]) -> dict[tuple[str, str, int, int], dict[str, Any]]:
    result: dict[tuple[str, str, int, int], dict[str, Any]] = {}
    for envelope in envelopes:
        identity = envelope.get("source", {}).get("identity", {})
        key = (str(identity.get("arm")), str(identity.get("task_id")),
               int(identity.get("trial_id", 0)), int(identity.get("seed", -1)))
        if key in result:
            raise RecoveryImportError("duplicate imported trajectory identity")
        result[key] = envelope
    return result


def _verify_task1(source_run: pathlib.Path, envelope_index: Mapping[tuple[str, str, int, int], Mapping[str, Any]]) -> dict[str, Any]:
    task = "024c982_2"
    for trial, seed in ((1, 11001), (2, 11002)):
        if ("copromem_v6_2_dynamic", task, trial, seed) not in envelope_index:
            raise RecoveryImportError("CoProMem task-1 dynamic artifact is absent")
    root = source_run / "copromem-dynamic-checkpoints" / "tasks" / "0001-024c982_2"
    transitions = (
        "task_pre_state_frozen", "retrievals_materialized", "trajectories_complete", "batch_ready",
        "semantic_plan_persisted", "validation_persisted", "commit_persisted",
        "post_state_snapshot_persisted", "next_task_authorized",
    )
    records: list[dict[str, Any]] = []
    previous: str | None = file_sha256(source_run / "copromem-dynamic-checkpoints" / "initial.json")
    for position, transition in enumerate(transitions, 1):
        path = root / f"{position:02d}-{transition}.json"
        record = _read_checkpoint(path)
        if (record.get("task_id") != task or record.get("transition") != transition
                or record.get("predecessor_transition_file_sha256") != previous):
            raise RecoveryImportError("CoProMem task-1 transition ordering mismatch")
        previous = file_sha256(path)
        records.append(record)
    post_record = records[-2]
    post_path = _host_path(str(post_record.get("post_state_snapshot", {}).get("path") or ""))
    post, post_container_sha = _snapshot(post_path, COPRO_POST)
    if records[-1].get("post_state_sha256") != COPRO_POST:
        raise RecoveryImportError("CoProMem task-1 next-task state mismatch")
    schemas = post.get("contrastive_v6_schemas")
    if not isinstance(schemas, dict) or len(schemas) != 12:
        raise RecoveryImportError("CoProMem task-1 restored schema bank is incomplete")
    return {
        "task_id": task,
        "transition_file_sha256s": [file_sha256(root / f"{index:02d}-{name}.json") for index, name in enumerate(transitions, 1)],
        "commit_marker_sha256": records[6].get("marker_sha256"),
        "semantic_post_state_sha256": COPRO_POST,
        "post_snapshot_container_sha256": post_container_sha,
        "schema_ids": sorted(schemas),
        "schema_content_sha256": {name: digest(value) for name, value in sorted(schemas.items())},
        "duplicate_restore_idempotent": True,
    }


def _verify_task2(source_run: pathlib.Path, forensic: Mapping[str, Any], envelope_index: Mapping[tuple[str, str, int, int], Mapping[str, Any]]) -> dict[str, Any]:
    task = "042a9fc_1"
    for trial, seed in ((1, 11001), (2, 11002)):
        if ("copromem_v6_2_dynamic", task, trial, seed) not in envelope_index:
            raise RecoveryImportError("CoProMem task-2 dynamic artifact is absent")
    offline = forensic.get("copromem_dynamic", {}).get("offline_reconstruction", {})
    if not isinstance(offline, Mapping):
        raise RecoveryImportError("forensic rejected-boundary reconstruction is absent")
    pre = offline.get("semantic_pre_state", {})
    post = offline.get("semantic_post_state", {})
    if pre.get("sha256") != COPRO_POST or post.get("sha256") != COPRO_POST:
        raise RecoveryImportError("rejected CoProMem boundary mutated semantic state")
    validation = offline.get("validation", {})
    candidate = offline.get("candidate_schema", {})
    comparison = offline.get("semantic_state_comparison", {})
    if (validation.get("passed") is not False or candidate.get("committed") or candidate.get("retrieval_visible")
            or comparison.get("retrieval_visible_state_sha256_before_after") != COPRO_POST):
        raise RecoveryImportError("rejected candidate is visible to retrieval")
    schema_hashes = comparison.get("schema_content_sha256_before_after")
    schema_ids = comparison.get("schema_ids_before_after")
    if not isinstance(schema_hashes, Mapping) or not isinstance(schema_ids, list) or len(schema_ids) != 12:
        raise RecoveryImportError("rejected boundary schema audit is incomplete")
    root = source_run / "copromem-dynamic-checkpoints" / "tasks" / "0002-042a9fc_1"
    pre_record = _read_checkpoint(root / "01-task_pre_state_frozen.json")
    pre_path = _host_path(str(pre_record.get("pre_state_snapshot", {}).get("path") or ""))
    state, pre_container_sha = _snapshot(pre_path, COPRO_POST)
    actual_hashes = {name: digest(value) for name, value in sorted(state.get("contrastive_v6_schemas", {}).items())}
    if actual_hashes != dict(schema_hashes):
        raise RecoveryImportError("rejected boundary schema content drift")
    if candidate.get("schema_id") in actual_hashes:
        raise RecoveryImportError("quarantined candidate leaked into semantic state")
    return {
        "task_id": task,
        "semantic_pre_state_sha256": COPRO_POST,
        "semantic_post_state_sha256": COPRO_POST,
        "pre_snapshot_container_sha256": pre_container_sha,
        "plan_semantic_sha256": offline.get("plan", {}).get("plan_sha256"),
        "plan_container_sha256": offline.get("plan", {}).get("container_sha256"),
        "validation_sha256": validation.get("sha256"),
        "rejected_marker_sha256": offline.get("rejected_marker", {}).get("sha256"),
        "audit_container_sha256": offline.get("audit_container_sha256"),
        "candidate_schema": dict(candidate),
        "schema_ids": list(schema_ids),
        "schema_content_sha256": dict(schema_hashes),
        "duplicate_restore_idempotent": True,
    }


def _ledger_rows(path: pathlib.Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    except (OSError, json.JSONDecodeError) as exc:
        raise RecoveryImportError("ledger is unreadable") from exc


def _verify_reme(source_run: pathlib.Path, envelope_index: Mapping[tuple[str, str, int, int], Mapping[str, Any]]) -> dict[str, Any]:
    root = source_run / "reme-dynamic-checkpoints"
    # The first frozen task was imported from Evaluation 002.  Its official
    # Dynamic calls remain settled only in that immutable predecessor ledger;
    # Evaluation 004 must not fabricate duplicate rows for them.
    previous_run = source_run.parent / "v6_2_task_conditioned_evaluation_002"
    ledger = _ledger_rows(source_run / "ledger.jsonl") + _ledger_rows(previous_run / "ledger.jsonl")
    reserve = {str(row.get("id")): row for row in ledger if row.get("event") == "reserve"}
    settle = {str(row.get("id")): row for row in ledger if row.get("event") == "settle"}
    if len({str(row.get("id")) for row in _ledger_rows(source_run / "ledger.jsonl") if row.get("event") == "reserve"}) != 268:
        raise RecoveryImportError("Evaluation 004 source ledger count is not exactly 268")
    if set(reserve) != set(settle):
        raise RecoveryImportError("ReMe source ledger is not fully reconciled")
    updates: list[dict[str, Any]] = []
    predecessor: str | None = None
    for index in range(1, 5):
        marker_path = root / "markers" / f"update-{index:04d}.json"
        marker = _load(marker_path)
        marker_sha = file_sha256(marker_path)
        identity = marker.get("identity", {})
        key = ("official_upstream_reme_dynamic", str(identity.get("task_id")),
               int(identity.get("trial_id", 0)), int(identity.get("seed", -1)))
        envelope = envelope_index.get(key)
        snapshot = root / "snapshots" / str(marker.get("source_snapshot") or "")
        verifier = root / "snapshots" / str(marker.get("verifier_dump") or "")
        settled_ids = marker.get("newly_settled_lifecycle_or_embedding_ids")
        expected_artifact_sha = None
        if envelope is not None:
            artifact = _load(_host_path(str(envelope["source"]["artifact_path"])))
            carried = artifact.get("carried_completed_from")
            expected_artifact_sha = (carried.get("source_artifact_sha256") if isinstance(carried, Mapping)
                                     else envelope["copied_artifact_sha256"])
        if (marker.get("ordered_update_index") != index or marker.get("predecessor_completion_marker_sha256") != predecessor
                or envelope is None or marker.get("scored_artifact_sha256") != expected_artifact_sha
                or marker.get("execution_evidence_sha256") != envelope["copied_journal_sha256"]
                or not snapshot.is_file() or file_sha256(snapshot) != marker.get("source_snapshot_sha256")
                or not verifier.is_file() or file_sha256(verifier) != marker.get("verifier_dump_sha256")
                or not isinstance(settled_ids, list) or not settled_ids):
            raise RecoveryImportError("ReMe Dynamic marker/snapshot identity mismatch")
        for call_id in settled_ids:
            role = str(settle.get(str(call_id), {}).get("role") or "")
            if call_id not in reserve or not role.startswith(("reme_lifecycle:reme-dynamic", "reme_embedding:reme-dynamic")):
                raise RecoveryImportError("ReMe Dynamic settlement binding is invalid")
        updates.append({"ordered_update_index": index, "trajectory_id": identity.get("trajectory_id"),
                        "marker_sha256": marker_sha, "snapshot_sha256": file_sha256(snapshot),
                        "verifier_dump_sha256": file_sha256(verifier),
                        "pre_update_semantic_sha256": marker.get("pre_update_semantic_sha256"),
                        "post_update_semantic_sha256": marker.get("post_update_semantic_sha256"),
                        "settlement_ids": list(settled_ids)})
        predecessor = marker_sha
    if updates[-1]["post_update_semantic_sha256"] != REME_POST:
        raise RecoveryImportError("latest ReMe Dynamic state mismatch")
    return {"updates": updates, "latest_semantic_state_sha256": REME_POST,
            "clean_reload_proven_by_durable_verifier_dumps": True}


def _summary(envelopes: list[Mapping[str, Any]]) -> dict[str, Any]:
    arms = Counter(str(item["source"]["identity"]["arm"]) for item in envelopes)
    scores: dict[str, list[float]] = {}
    actions: dict[str, list[int]] = {}
    for item in envelopes:
        row = _load(_host_path(str(item["source"]["artifact_path"])))
        arm = str(row["arm"])
        scores.setdefault(arm, []).append(float(row["after_score"]))
        actions.setdefault(arm, []).append(int(row["actions"]))
    return {"completed": 20, "expected": 300, "imported_completed": 20, "newly_completed": 0,
            "completed_task_boundaries": 2,
            "per_arm": {arm: {"completed": arms[arm], "successes": sum(score == 1.0 for score in scores[arm]),
                               "avg_score": sum(scores[arm]) / len(scores[arm]),
                               "avg_actions": sum(actions[arm]) / len(actions[arm])}
                        for arm in sorted(arms)}}


def assemble(*, imported_root: pathlib.Path, source_run: pathlib.Path, forensic_json: pathlib.Path,
             successor_identity: Mapping[str, Any], historical_exposure: float,
             expected_source_inventory_sha256: str = LEGACY_SOURCE_SHA256,
             expected_envelope_inventory_sha256: str = LEGACY_ENVELOPE_SHA256) -> dict[str, Any]:
    """Validate the full production prefix and return one canonical recovery state."""
    imported_root = imported_root.resolve()
    source_run = source_run.resolve()
    marker = _load(imported_root / "recovery_import_complete.json")
    if marker.get("version") != "atomic-recovery-import-v1" or int(marker.get("imported_count", 0)) != 20:
        raise RecoveryImportError("recovery import marker is incomplete")
    spec = _load(imported_root / "recovery-import-spec.json")
    if canonical_sha256(spec) != marker.get("specification_sha256") or spec.get("next") != NEXT:
        raise RecoveryImportError("recovery import specification/next identity mismatch")
    records = marker.get("records")
    if not isinstance(records, list) or len(records) != 20 or len({item.get("trajectory_id") for item in records}) != 20:
        raise RecoveryImportError("recovery envelope inventory is incomplete")
    envelopes: list[dict[str, Any]] = []
    for row in records:
        path = imported_root / "import-envelopes" / f"{int(row['position']):04d}.json"
        envelope = _load(path)
        body = {key: value for key, value in envelope.items() if key != "envelope_sha256"}
        if envelope.get("envelope_sha256") != row.get("envelope_sha256") or canonical_sha256(body) != envelope.get("envelope_sha256"):
            raise RecoveryImportError("recovery envelope hash mismatch")
        envelopes.append(envelope)
    envelope_index = _envelope_by_identity(envelopes)
    custody = build_mapping(source_run=source_run, expected_manifest_sha256=str(spec.get("source_manifest_sha256") or ""),
                            imported_root=imported_root, expected_source_inventory_sha256=expected_source_inventory_sha256,
                            expected_envelope_inventory_sha256=expected_envelope_inventory_sha256)
    validate_mapping(custody)
    forensic = _load(forensic_json)
    task1 = _verify_task1(source_run, envelope_index)
    task2 = _verify_task2(source_run, forensic, envelope_index)
    reme = _verify_reme(source_run, envelope_index)
    reme_fixed = _load(source_run / "reme-fixed-integrity" / "initial.json")
    copro_initial = _load(source_run / "copromem-dynamic-checkpoints" / "initial.json")
    if reme_fixed.get("semantic_sha256") != REME_INITIAL or copro_initial.get("fixed_initial_state_sha256") != COPRO_FIXED_INITIAL:
        raise RecoveryImportError("fixed arm identity differs from frozen initial bank")
    ledger_rows = _ledger_rows(source_run / "ledger.jsonl")
    historical = [row for row in ledger_rows if row.get("id") == "historical-construction-carry"]
    if len(historical) != 2 or {row.get("event") for row in historical} != {"reserve", "settle"}:
        raise RecoveryImportError("historical carry-forward is not unique and settled")
    state = {
        "version": VERSION,
        "import_marker_sha256": marker.get("marker_sha256"),
        "source_prefix_inventory_sha256": custody["source_inventory"]["sha256"],
        "successor_envelope_inventory_sha256": custody["successor_envelope_inventory"]["sha256"],
        "custody_mapping_sha256": custody["custody_mapping_sha256"],
        "custody_mapping": custody,
        "source": {"run": str(source_run), "manifest_sha256": spec.get("source_manifest_sha256"),
                   "runtime_sha256": envelopes[0]["source"].get("source_runtime_sha256")},
        "envelope_hashes": [item["envelope_sha256"] for item in envelopes],
        "copromem_dynamic": {"task1_committed": task1, "task2_rejected_nonmutating": task2,
                               "restored_semantic_state_sha256": COPRO_POST},
        "reme_dynamic": reme,
        "fixed": {"copromem_semantic_state_sha256": COPRO_FIXED_INITIAL,
                  "reme_semantic_state_sha256": REME_INITIAL,
                  "dynamic_contamination": False},
        "ledger": {"evaluation_004_ledger_sha256": file_sha256(source_run / "ledger.jsonl"),
                   "source_reservations": 268, "source_settlements": 268, "source_unresolved": 0,
                   "historical_carry_id": "historical-construction-carry", "historical_exposure": historical_exposure,
                   "successor_reservations": 0},
        "progress": _summary(envelopes), "next": dict(NEXT), "successor_identity": dict(successor_identity),
    }
    if state["progress"]["per_arm"] and any(value["completed"] != 4 for value in state["progress"]["per_arm"].values()):
        raise RecoveryImportError("imported progress does not contain four trajectories per arm")
    if state["next"] != NEXT:
        raise RecoveryImportError("next trajectory identity mismatch")
    state["recovery_state_sha256"] = canonical_sha256(state)
    return state


def publish(*, root: pathlib.Path, state: Mapping[str, Any]) -> dict[str, Any]:
    """Atomically publish exactly one immutable unified recovery marker."""
    body = dict(state)
    content = {key: value for key, value in body.items() if key != "recovery_state_sha256"}
    if body.get("version") != VERSION or body.get("recovery_state_sha256") != canonical_sha256(content):
        raise RecoveryImportError("recovery state is not content-addressed")
    path = root.resolve() / MARKER_NAME
    if path.exists():
        existing = _load(path)
        if existing != body:
            raise RecoveryImportError("recovery-state marker conflicts with immutable import")
        return existing
    _atomic_json(path, body)
    return body


def load_published(root: pathlib.Path) -> dict[str, Any]:
    """Read-only validation used by the production recovery-start boundary."""
    value = _load(root.resolve() / MARKER_NAME)
    expected = {key: item for key, item in value.items() if key != "recovery_state_sha256"}
    if value.get("version") != VERSION or value.get("recovery_state_sha256") != canonical_sha256(expected):
        raise RecoveryImportError("unified recovery-state marker is invalid")
    if (value.get("next") != NEXT or value.get("progress", {}).get("completed") != 20
            or value.get("source_prefix_inventory_sha256") != LEGACY_SOURCE_SHA256
            or value.get("successor_envelope_inventory_sha256") != LEGACY_ENVELOPE_SHA256
            or not isinstance(value.get("custody_mapping_sha256"), str)):
        raise RecoveryImportError("unified recovery-state continuation identity is invalid")
    mapping = value.get("custody_mapping")
    if (not isinstance(mapping, Mapping) or mapping.get("custody_mapping_sha256") != value.get("custody_mapping_sha256")
            or mapping.get("source_inventory", {}).get("sha256") != value.get("source_prefix_inventory_sha256")
            or mapping.get("successor_envelope_inventory", {}).get("sha256") != value.get("successor_envelope_inventory_sha256")):
        raise RecoveryImportError("unified recovery-state custody mapping binding is invalid")
    validate_mapping(mapping)
    return value


def validate_published_custody(root: pathlib.Path, state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Rebuild the two custody domains before admitting a recovered prefix.

    ``load_published`` checks the marker's own content identity.  This second,
    read-only step also compares it with the immutable source artifacts and
    copied envelopes, preventing a self-consistent but source-divergent marker
    from becoming a runnable continuation.
    """
    root = root.resolve()
    published = dict(state) if state is not None else load_published(root)
    source = published.get("source", {})
    source_run = _host_path(str(source.get("run") or ""))
    actual = build_mapping(
        source_run=source_run,
        expected_manifest_sha256=str(source.get("manifest_sha256") or ""),
        imported_root=root,
        expected_source_inventory_sha256=LEGACY_SOURCE_SHA256,
        expected_envelope_inventory_sha256=LEGACY_ENVELOPE_SHA256,
    )
    if actual != published.get("custody_mapping"):
        raise RecoveryImportError("published custody mapping diverges from immutable evidence")
    return actual
