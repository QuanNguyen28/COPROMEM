"""Hash-verified, provenance-preserving scored-artifact recovery imports.

This boundary is intentionally local-only: it copies already durable evidence
into a new run root, rebinds the copied journal paths, and never dispatches a
provider, benchmark, or scorer operation.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import uuid
from collections.abc import Mapping
from typing import Any

from .evidence_contract import (
    HASH,
    PATH,
    RELATIVE,
    ROWS,
    SCORER,
    EvidenceContractError,
    load_artifact,
    validate,
)


class RecoveryImportError(RuntimeError):
    """A predecessor artifact cannot be imported without changing evidence."""


IMPORT_VERSION = "atomic-recovery-import-v1"


def file_sha256(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise RecoveryImportError(f"unreadable recovery file: {path.name}") from exc


def _atomic_json(path: pathlib.Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    try:
        directory = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError:
        pass


def canonical_sha256(value: Any) -> str:
    """Content identity used for immutable recovery specifications/markers."""
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def publish_atomic_import(*, target_run: pathlib.Path, specification: Mapping[str, Any],
                          materialize: callable) -> dict[str, Any]:
    """Stage and atomically publish a complete, content-bound recovery import.

    ``materialize(staging_root)`` must return one mapping per imported object.
    It is deliberately local-only.  A completed marker makes subsequent calls
    read-only; a staging directory without the marker never authorizes work.
    """
    target_run = target_run.resolve()
    marker_path = target_run / "recovery_import_complete.json"
    spec = dict(specification)
    spec_hash = canonical_sha256(spec)
    if marker_path.exists():
        existing = json.loads(marker_path.read_text(encoding="utf-8"))
        if existing.get("specification_sha256") != spec_hash:
            raise RecoveryImportError("completed recovery import specification drift")
        if existing.get("marker_sha256") != canonical_sha256({k: v for k, v in existing.items() if k != "marker_sha256"}):
            raise RecoveryImportError("completed recovery import marker hash mismatch")
        return existing
    staging = target_run / ".recovery-import-staging"
    if staging.exists():
        raise RecoveryImportError("partial recovery import staging exists without completion marker")
    staging.mkdir(parents=True, exist_ok=False)
    try:
        records = list(materialize(staging))
        expected = spec.get("expected_trajectory_ids")
        identities = [str(row.get("trajectory_id") or "") for row in records]
        if (not isinstance(expected, list) or len(expected) != len(records)
                or len(identities) != len(set(identities)) or identities != list(map(str, expected))):
            raise RecoveryImportError("recovery import inventory is incomplete, duplicate, or reordered")
        inventory_hash = canonical_sha256(records)
        manifest = {
            "version": IMPORT_VERSION, "specification_sha256": spec_hash,
            "inventory_sha256": inventory_hash, "imported_count": len(records),
            "records": records,
        }
        manifest["marker_sha256"] = canonical_sha256(manifest)
        _atomic_json(staging / "recovery_import_complete.json", manifest)
        # Same-filesystem rename makes publication all-or-nothing.
        for child in list(staging.iterdir()):
            if child.name == "recovery_import_complete.json":
                continue
            destination = target_run / child.name
            if destination.exists():
                raise RecoveryImportError("recovery target already contains staged evidence")
            os.replace(child, destination)
        os.replace(staging / "recovery_import_complete.json", marker_path)
        staging.rmdir()
        _fsync_target = target_run
        try:
            fd = os.open(str(_fsync_target), os.O_RDONLY); os.fsync(fd); os.close(fd)
        except OSError:
            pass
        return manifest
    except Exception:
        # Preserve staging for forensic recovery; never clean it silently.
        raise


def _durable_copy(source: pathlib.Path, destination: pathlib.Path) -> None:
    if not source.is_file():
        raise RecoveryImportError("recovery source journal is absent")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with source.open("rb") as input_handle, temporary.open("wb") as output_handle:
        shutil.copyfileobj(input_handle, output_handle)
        output_handle.flush()
        os.fsync(output_handle.fileno())
    if file_sha256(source) != file_sha256(temporary):
        temporary.unlink(missing_ok=True)
        raise RecoveryImportError("recovery journal copy hash mismatch")
    os.replace(temporary, destination)
    try:
        directory = os.open(str(destination.parent), os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError:
        pass


def copy_evidence_file(source: pathlib.Path, destination: pathlib.Path) -> str:
    """Durably copy one immutable evidence file and return its verified hash."""
    _durable_copy(source, destination)
    return file_sha256(destination)


def import_scored_artifact(*, source_artifact: pathlib.Path, source_run: pathlib.Path,
                           target_artifact: pathlib.Path, target_run: pathlib.Path,
                           source_manifest_sha256: str) -> dict[str, Any]:
    """Copy one valid scored artifact with journal paths rebound to ``target_run``.

    The original artifact remains untouched.  The derived artifact retains the
    immutable source artifact hash and source manifest identity, while the
    standard evidence contract validates only the copied, byte-identical
    journals beneath the successor run root.
    """
    source_run, target_run = source_run.resolve(), target_run.resolve()
    try:
        source = load_artifact(source_artifact)
        execution_source = validate(source, run_root=source_run)
    except EvidenceContractError as exc:
        raise RecoveryImportError("source scored artifact fails its evidence contract") from exc
    scorer = source.get(SCORER)
    if not isinstance(scorer, Mapping):
        raise RecoveryImportError("source scored artifact lacks scorer binding")
    scorer_source = pathlib.Path(str(scorer.get("path") or ""))
    if not scorer_source.is_absolute() or not scorer_source.is_file():
        raise RecoveryImportError("source scorer journal is absent")
    execution_target = target_run / "journals" / execution_source.name
    scorer_target = target_run / "journals" / scorer_source.name
    _durable_copy(execution_source, execution_target)
    _durable_copy(scorer_source, scorer_target)
    result = json.loads(json.dumps(source, ensure_ascii=False, sort_keys=True))
    result[PATH] = str(execution_target.resolve())
    # Preserve the current platform's canonical relative representation; the
    # evidence contract deliberately performs the same conversion.
    result[RELATIVE] = str(execution_target.resolve().relative_to(target_run))
    result[HASH] = file_sha256(execution_target)
    result[ROWS] = len(execution_target.read_bytes().splitlines())
    result[SCORER] = {**dict(scorer), "path": str(scorer_target.resolve()), "sha256": file_sha256(scorer_target)}
    result["carried_completed_from"] = {
        "source_manifest_sha256": source_manifest_sha256,
        "source_artifact_sha256": file_sha256(source_artifact),
        "source_trajectory_id": source.get("trajectory_id"),
    }
    _atomic_json(target_artifact, result)
    try:
        validate(result, run_root=target_run)
    except EvidenceContractError as exc:
        raise RecoveryImportError("rebound scored artifact fails its evidence contract") from exc
    return {
        "source_artifact_sha256": result["carried_completed_from"]["source_artifact_sha256"],
        "target_artifact_sha256": file_sha256(target_artifact),
        "trajectory_id": str(result.get("trajectory_id") or ""),
        "execution_evidence_sha256": result[HASH],
        "scorer_evidence_sha256": result[SCORER]["sha256"],
    }
