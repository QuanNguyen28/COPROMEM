"""Read-only production-runner admission for a v6.2 recovered prefix.

The runner must call :func:`admit` before acquiring a lock, starting a ReMe
service, or opening a task.  This keeps an incomplete import from becoming a
best-effort resume.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .recovery_import import RecoveryImportError, canonical_sha256
from .v62_recovery_prefix import NEXT
from .v62_recovery_state import load_published, validate_published_custody


class RecoveryStartError(RuntimeError):
    """A recovered production run may not safely begin."""


@dataclass(frozen=True)
class RecoveryStart:
    """The sole next-work identity admitted from a complete unified marker."""

    recovery_state_sha256: str
    imported_completed: int
    expected: int
    next: Mapping[str, Any]
    copromem_dynamic_sha256: str
    reme_dynamic_sha256: str
    copromem_fixed_sha256: str
    reme_fixed_sha256: str


def admit(*, marker_root: Path, expected_source_identity: Mapping[str, Any],
          expected_manifest_sha256: str) -> RecoveryStart:
    """Read and validate recovery state without creating any runtime object."""
    try:
        state = load_published(marker_root)
        validate_published_custody(marker_root, state)
    except RecoveryImportError as exc:
        raise RecoveryStartError(str(exc)) from exc
    if dict(state.get("successor_identity", {})) != dict(expected_source_identity):
        raise RecoveryStartError("recovery marker source identity drift")
    source = state.get("source", {})
    if source.get("manifest_sha256") != expected_manifest_sha256:
        raise RecoveryStartError("recovery marker source manifest drift")
    progress = state.get("progress", {})
    ledger = state.get("ledger", {})
    fixed = state.get("fixed", {})
    copro = state.get("copromem_dynamic", {})
    reme = state.get("reme_dynamic", {})
    if (progress.get("completed") != 20 or progress.get("imported_completed") != 20
            or progress.get("newly_completed") != 0 or progress.get("expected") != 300
            or any(value.get("completed") != 4 for value in progress.get("per_arm", {}).values())
            or ledger.get("successor_reservations") != 0 or ledger.get("source_unresolved") != 0
            or state.get("next") != NEXT):
        raise RecoveryStartError("recovery marker progress, ledger, or next-work identity is invalid")
    if (copro.get("restored_semantic_state_sha256") != "1cff4e8192f853d9e835e7e6054346867a7b53584f0c9d61ee13b757885d0b75"
            or reme.get("latest_semantic_state_sha256") != "5871658adb09f4c74fc730aaa8c5e5a1025d5bd51187393b3e0a1cf3f7401a2a"
            or fixed.get("copromem_semantic_state_sha256") != "add35eca3ccaa9780183a144328157db2c64b932e5b69a7e3d5b87fd4efc9448"
            or fixed.get("reme_semantic_state_sha256") != "6c3bc799ec0beb034fd2b81ee0d5cbf6e89a14f3a5a39ebf70d34853686b00a0"):
        raise RecoveryStartError("recovery marker state identity is invalid")
    recorded = state.get("recovery_state_sha256")
    if not isinstance(recorded, str) or recorded != canonical_sha256({key: value for key, value in state.items() if key != "recovery_state_sha256"}):
        raise RecoveryStartError("recovery marker content identity is invalid")
    return RecoveryStart(recorded, 20, 300, dict(NEXT), copro["restored_semantic_state_sha256"],
                         reme["latest_semantic_state_sha256"], fixed["copromem_semantic_state_sha256"],
                         fixed["reme_semantic_state_sha256"])
