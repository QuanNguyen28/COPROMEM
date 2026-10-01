"""Keep semantic runtime identity distinct from its durable record-file hash."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping


class RuntimeIdentityBindingError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _valid(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise RuntimeIdentityBindingError("runtime identity is malformed")
    return value


def read(run_root: Path) -> dict[str, str]:
    path = run_root / "runtime-identity.json"; sidecar_path = run_root / "runtime-identity.binding.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8")); sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeIdentityBindingError("runtime identity record or binding is unavailable") from exc
    semantic, record_hash = _valid(record.get("runtime_identity_sha256")), _sha(path)
    if sidecar != {"runtime_identity_sha256": semantic, "runtime_identity_record_sha256": record_hash}:
        raise RuntimeIdentityBindingError("runtime semantic and record identity binding differs from its record")
    return {"runtime_identity_sha256": semantic, "runtime_identity_record_sha256": record_hash}


def verify(run_root: Path, value: Mapping[str, object]) -> dict[str, str]:
    observed = read(run_root)
    semantic, record_hash = _valid(value.get("runtime_identity_sha256")), _valid(value.get("runtime_identity_record_sha256"))
    if semantic == record_hash or semantic != observed["runtime_identity_sha256"] or record_hash != observed["runtime_identity_record_sha256"]:
        raise RuntimeIdentityBindingError("runtime semantic identity and record identity use different domains")
    return observed


def artifact_domains(value: Mapping[str, object]) -> dict[str, str]:
    """Return the two runtime identity domains bound by a scored artifact.

    Production artifacts use ``runtime_identity_sha256`` for the semantic
    identity.  A short-lived v6.2.2 sidecar fixture used the more verbose
    ``runtime_identity_semantic_sha256`` alias.  Accept that alias only for
    historical evidence and fail closed if both spellings disagree.
    """
    canonical = value.get("runtime_identity_sha256")
    legacy_alias = value.get("runtime_identity_semantic_sha256")
    if canonical is None:
        canonical = legacy_alias
    elif legacy_alias is not None and legacy_alias != canonical:
        raise RuntimeIdentityBindingError(
            "artifact contains conflicting semantic runtime identities"
        )
    semantic = _valid(canonical)
    record_hash = _valid(value.get("runtime_identity_record_sha256"))
    if semantic == record_hash:
        raise RuntimeIdentityBindingError(
            "artifact runtime semantic and record identities share a domain"
        )
    return {
        "runtime_identity_sha256": semantic,
        "runtime_identity_record_sha256": record_hash,
    }
