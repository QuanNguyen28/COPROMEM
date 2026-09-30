"""Dual-domain custody identities for the immutable v6.2 recovery prefix.

An ordered source inventory and an ordered envelope inventory are deliberately
different objects.  Their hashes are comparable only through the explicit
one-to-one mapping produced here.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Mapping

from .recovery_import import RecoveryImportError, canonical_sha256, file_sha256
from .v62_recovery_prefix import _host_path, _load, validate_real_prefix


VERSION = "v6.2-dual-domain-custody-v1"
SOURCE_DOMAIN = "v6.2-source-artifact-inventory-v1"
ENVELOPE_DOMAIN = "v6.2-successor-envelope-inventory-v1"
MAPPING_DOMAIN = "v6.2-source-envelope-custody-mapping-v1"
LEGACY_SOURCE_SHA256 = "c40daeba9baf334f073125a52f4aec5ff59bd86181e346983bd0f8250f33b122"
LEGACY_ENVELOPE_SHA256 = "d1b26a6e0e497deaf9660d000e737893f6a666b60fe68d38db7375b6542d32be"


def _history_sha256(path: pathlib.Path) -> str:
    row = _load(path)
    history = row.get("history")
    if not isinstance(history, list) or row.get("history_sha256") != canonical_sha256(history):
        raise RecoveryImportError("source artifact history identity is invalid")
    return str(row["history_sha256"])


def source_inventory(*, source_run: pathlib.Path, expected_manifest_sha256: str) -> list[dict[str, Any]]:
    """Return the exact ordered source preimage reconstructed from durable data."""
    rows = validate_real_prefix(source_run=source_run, expected_manifest_sha256=expected_manifest_sha256)
    if len(rows) != 20:
        raise RecoveryImportError("source prefix has the wrong item count")
    return rows


def envelope_inventory(*, imported_root: pathlib.Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return the exact atomic-marker preimage and matching full envelopes."""
    root = imported_root.resolve()
    marker = _load(root / "recovery_import_complete.json")
    records = marker.get("records")
    if (marker.get("version") != "atomic-recovery-import-v1" or not isinstance(records, list)
            or marker.get("marker_sha256") != canonical_sha256({key: value for key, value in marker.items() if key != "marker_sha256"})
            or len(records) != 20 or canonical_sha256(records) != marker.get("inventory_sha256")):
        raise RecoveryImportError("successor envelope inventory marker is invalid")
    envelopes: list[dict[str, Any]] = []
    for record in records:
        position = int(record.get("position", 0))
        envelope = _load(root / "import-envelopes" / f"{position:04d}.json")
        body = {key: value for key, value in envelope.items() if key != "envelope_sha256"}
        if envelope.get("envelope_sha256") != record.get("envelope_sha256") or canonical_sha256(body) != envelope.get("envelope_sha256"):
            raise RecoveryImportError("successor envelope content hash is invalid")
        envelopes.append(envelope)
    return list(records), envelopes


def build_mapping(*, source_run: pathlib.Path, expected_manifest_sha256: str,
                  imported_root: pathlib.Path, expected_source_inventory_sha256: str | None = None,
                  expected_envelope_inventory_sha256: str | None = None) -> dict[str, Any]:
    """Bind every immutable source entry to exactly one successor envelope."""
    source = source_inventory(source_run=source_run, expected_manifest_sha256=expected_manifest_sha256)
    records, envelopes = envelope_inventory(imported_root=imported_root)
    source_hash = canonical_sha256(source)
    envelope_hash = canonical_sha256(records)
    if expected_source_inventory_sha256 is not None and source_hash != expected_source_inventory_sha256:
        raise RecoveryImportError("source inventory hash does not match its declared domain")
    if expected_envelope_inventory_sha256 is not None and envelope_hash != expected_envelope_inventory_sha256:
        raise RecoveryImportError("envelope inventory hash does not match its declared domain")
    rows: list[dict[str, Any]] = []
    if len(source) != len(records) or len(records) != len(envelopes):
        raise RecoveryImportError("source/envelope inventory count mismatch")
    for position, (source_row, record, envelope) in enumerate(zip(source, records, envelopes), 1):
        source_identity = source_row["identity"]
        if (int(record.get("position", 0)) != position or int(source_row.get("position", 0)) != position
                or record.get("trajectory_id") != source_row.get("trajectory_id")
                or envelope.get("source") != source_row):
            raise RecoveryImportError("source/envelope ordering or provenance mismatch")
        artifact_path = _host_path(str(source_row["artifact_path"]))
        source_artifact = _load(artifact_path)
        if file_sha256(artifact_path) != source_row["artifact_sha256"]:
            raise RecoveryImportError("immutable source artifact hash mismatch")
        if (source_artifact.get("history_sha256") != _history_sha256(artifact_path)
                or source_artifact.get("execution_evidence_sha256") != source_row["journal_sha256"]):
            raise RecoveryImportError("source history or journal binding mismatch")
        row = {
            "position": position,
            "trajectory_id": source_row["trajectory_id"],
            "identity": dict(source_identity),
            "source_inventory_entry_sha256": canonical_sha256(source_row),
            "original_artifact_sha256": source_row["artifact_sha256"],
            "history_sha256": source_artifact["history_sha256"],
            "journal_sha256": source_row["journal_sha256"],
            "normalized_scorer_sha256": source_row["normalized_scorer_sha256"],
            "source_run": source_row["source_run"],
            "source_manifest_sha256": source_row["source_manifest_sha256"],
            "source_runtime_sha256": source_row["source_runtime_sha256"],
            "source_commit": source_row["source_commit"],
            "successor_envelope_sha256": envelope["envelope_sha256"],
        }
        rows.append(row)
    mapping = {
        "version": VERSION,
        "hash_domain": MAPPING_DOMAIN,
        "source_inventory": {"hash_domain": SOURCE_DOMAIN, "sha256": source_hash, "count": len(source)},
        "successor_envelope_inventory": {"hash_domain": ENVELOPE_DOMAIN, "sha256": envelope_hash, "count": len(records)},
        "entries": rows,
    }
    mapping["custody_mapping_sha256"] = canonical_sha256(mapping)
    return mapping


def validate_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Pure verification for restart/idempotent marker admission."""
    body = {key: value for key, value in mapping.items() if key != "custody_mapping_sha256"}
    if (mapping.get("version") != VERSION or mapping.get("hash_domain") != MAPPING_DOMAIN
            or mapping.get("custody_mapping_sha256") != canonical_sha256(body)):
        raise RecoveryImportError("custody mapping content identity is invalid")
    entries = mapping.get("entries")
    if not isinstance(entries, list) or len(entries) != 20:
        raise RecoveryImportError("custody mapping item count is invalid")
    expected_positions = list(range(1, 21))
    if [entry.get("position") for entry in entries] != expected_positions:
        raise RecoveryImportError("custody mapping ordering is invalid")
    if len({entry.get("trajectory_id") for entry in entries}) != 20:
        raise RecoveryImportError("custody mapping contains duplicate trajectories")
    for entry in entries:
        required = {"source_inventory_entry_sha256", "original_artifact_sha256", "history_sha256", "journal_sha256",
                    "normalized_scorer_sha256", "successor_envelope_sha256", "source_manifest_sha256", "source_runtime_sha256"}
        if not required <= set(entry) or any(not isinstance(entry[key], str) or len(entry[key]) != 64 for key in required):
            raise RecoveryImportError("custody mapping entry is incomplete")
    return dict(mapping)
