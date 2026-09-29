"""Versioned, fail-closed scored-artifact execution-evidence contract.

This is the one vocabulary used by the producer, reconciliation, reporting,
and restart boundaries.  It deliberately validates the durable journal binding
without reading task content.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from collections.abc import Mapping
from typing import Any


VERSION = "scored-execution-evidence-v1"
PATH = "execution_evidence_path"
HASH = "execution_evidence_sha256"
ROWS = "execution_evidence_rows"
REGISTRY = "execution_evidence_registry_sha256"
RELATIVE = "execution_evidence_run_relative"
VERSION_FIELD = "execution_evidence_contract_version"
FIELDS = frozenset({PATH, HASH, ROWS, REGISTRY, RELATIVE, VERSION_FIELD})


class EvidenceContractError(RuntimeError):
    """A scored artifact is not safely bound to its execution journal."""


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise EvidenceContractError(f"duplicate scored-artifact field: {key}")
        value[key] = item
    return value


def load_artifact(path: pathlib.Path) -> dict[str, Any]:
    """Load one artifact while rejecting duplicate JSON object keys."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicates)
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceContractError("scored artifact is unreadable") from exc
    if not isinstance(value, dict):
        raise EvidenceContractError("scored artifact has the wrong shape")
    return value


def _relative(path: pathlib.Path, run_root: pathlib.Path) -> str:
    try:
        return str(path.relative_to(run_root.resolve()))
    except ValueError as exc:
        raise EvidenceContractError("execution-evidence journal escapes the run root") from exc


def bind(*, journal: pathlib.Path, run_root: pathlib.Path, registry_sha256: str) -> dict[str, Any]:
    """Return the canonical evidence fields after a durable journal write."""
    run_root = run_root.resolve()
    journal = journal.resolve()
    if not journal.is_absolute() or not journal.is_file():
        raise EvidenceContractError("execution-evidence journal is not an absolute durable file")
    payload = journal.read_bytes()
    if not payload:
        raise EvidenceContractError("execution-evidence journal is empty")
    if not isinstance(registry_sha256, str) or not registry_sha256:
        raise EvidenceContractError("execution-evidence registry identity is absent")
    return {
        PATH: str(journal),
        HASH: hashlib.sha256(payload).hexdigest(),
        ROWS: len(payload.splitlines()),
        REGISTRY: registry_sha256,
        RELATIVE: _relative(journal, run_root),
        VERSION_FIELD: VERSION,
    }


def validate(row: Mapping[str, Any], *, run_root: pathlib.Path,
             expected_registry_sha256: str | None = None) -> pathlib.Path:
    """Validate and return the canonical journal path without modifying state."""
    if row.get(VERSION_FIELD) != VERSION:
        raise EvidenceContractError("scored artifact execution-evidence contract version mismatch")
    if any(field not in row for field in FIELDS):
        raise EvidenceContractError("scored artifact has missing execution-evidence binding fields")
    raw_path = row.get(PATH)
    if not isinstance(raw_path, str) or not raw_path:
        raise EvidenceContractError("scored artifact has no absolute execution-evidence path")
    journal = pathlib.Path(raw_path)
    if not journal.is_absolute() or not journal.is_file():
        raise EvidenceContractError("scored artifact execution-evidence journal is absent")
    payload = journal.read_bytes()
    if not payload:
        raise EvidenceContractError("scored artifact execution-evidence journal is empty")
    if row.get(HASH) != hashlib.sha256(payload).hexdigest():
        raise EvidenceContractError("scored artifact execution-evidence hash mismatch")
    if not isinstance(row.get(ROWS), int) or row[ROWS] != len(payload.splitlines()) or row[ROWS] <= 0:
        raise EvidenceContractError("scored artifact execution-evidence row count mismatch")
    registry = row.get(REGISTRY)
    if not isinstance(registry, str) or not registry:
        raise EvidenceContractError("scored artifact lacks execution-evidence registry identity")
    if expected_registry_sha256 is not None and registry != expected_registry_sha256:
        raise EvidenceContractError("scored artifact execution-evidence registry differs from the frozen registry")
    if not isinstance(row.get(RELATIVE), str) or row[RELATIVE] != _relative(journal, run_root):
        raise EvidenceContractError("scored artifact execution-evidence locator mismatch")
    return journal
