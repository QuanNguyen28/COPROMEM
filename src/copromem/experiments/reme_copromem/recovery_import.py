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
