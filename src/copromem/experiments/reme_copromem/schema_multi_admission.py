"""Immutable multi-schema custody for CoProMem retrieval admission.

Each schema remains independently externally admitted.  The bundle adds the
stable terminal-slice identity that is checked against the live Dynamic bank,
so a later task update cannot substitute a different learned schema under the
same identifier.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .schema_external_admission import digest, verify as verify_receipt


def schema_identity(schema: Mapping[str, Any]) -> str:
    """Hash only immutable retrieval semantics, excluding mutable support counts."""
    value = {
        "policy_version": schema.get("policy_version"),
        "registry_sha256": schema.get("registry_sha256"),
        "required_operations": list(schema.get("required_operations", ())),
        "terminal_effect": schema.get("terminal_effect"),
        "terminal_occurrence_id": schema.get("terminal_occurrence_id"),
        "typed_constraints": list(schema.get("typed_constraints", ())),
    }
    return digest(value)


def bundle(*, policy_sha256: str, entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Create a deterministic bundle of independently held-out schemas."""
    normalized: list[dict[str, Any]] = []
    for value in entries:
        row = dict(value)
        schema_id = row.get("schema_id")
        schema_sha256 = row.get("schema_identity_sha256")
        receipt = row.get("external_admission_receipt")
        if not isinstance(schema_id, str) or not schema_id:
            raise ValueError("schema admission entry has no schema id")
        if not isinstance(schema_sha256, str) or len(schema_sha256) != 64:
            raise ValueError("schema admission entry has invalid semantic identity")
        if not isinstance(receipt, Mapping):
            raise ValueError("schema admission entry has no external receipt")
        if receipt.get("schema_ids") != [schema_id]:
            raise ValueError("each multi-schema entry must have one exact external schema receipt")
        normalized.append({
            "schema_id": schema_id,
            "schema_identity_sha256": schema_sha256,
            "external_admission_receipt": dict(receipt),
        })
    normalized.sort(key=lambda row: row["schema_id"])
    if not normalized or len({row["schema_id"] for row in normalized}) != len(normalized):
        raise ValueError("multi-schema admission ids are empty or duplicated")
    value: dict[str, Any] = {
        "version": "copromem-multi-schema-admission-v1",
        "retrieval_policy_sha256": policy_sha256,
        "entries": normalized,
    }
    value["bundle_sha256"] = digest(value)
    return value


def verify(value: Mapping[str, Any], *, policy_sha256: str,
           schemas: Mapping[str, Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    row = dict(value)
    actual = row.pop("bundle_sha256", None)
    if actual != digest(row):
        raise ValueError("multi-schema admission bundle hash mismatch")
    if row.get("version") != "copromem-multi-schema-admission-v1":
        raise ValueError("multi-schema admission version is invalid")
    if row.get("retrieval_policy_sha256") != policy_sha256:
        raise ValueError("multi-schema admission policy differs")
    entries = row.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("multi-schema admission has no entries")
    admitted: dict[str, Mapping[str, Any]] = {}
    previous = ""
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ValueError("multi-schema admission entry is malformed")
        schema_id = entry.get("schema_id")
        receipt = entry.get("external_admission_receipt")
        if not isinstance(schema_id, str) or not schema_id or schema_id <= previous:
            raise ValueError("multi-schema admission ids are unordered or duplicated")
        previous = schema_id
        if not isinstance(receipt, Mapping) or receipt.get("schema_ids") != [schema_id]:
            raise ValueError("multi-schema admission receipt does not bind exactly one schema")
        bank_sha256 = receipt.get("bank_sha256")
        if not isinstance(bank_sha256, str) or not bank_sha256:
            raise ValueError("multi-schema admission receipt has no source bank identity")
        verify_receipt(receipt, bank_sha256=bank_sha256)
        if receipt.get("retrieval_policy_sha256") != policy_sha256:
            raise ValueError("multi-schema admission receipt policy differs")
        schema = schemas.get(schema_id)
        if not isinstance(schema, Mapping):
            raise ValueError("admitted schema is absent from live bank")
        if entry.get("schema_identity_sha256") != schema_identity(schema):
            raise ValueError("admitted schema semantic identity differs")
        admitted[schema_id] = schema
    return admitted
