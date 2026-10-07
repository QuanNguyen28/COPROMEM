"""No-service adapter for a frozen CoProMem-only evaluation overlay.

The maintained v6.1 runner normally owns three official ReMe services.  A
manifest containing no ReMe arm must not start them: they are not an input to
CoProMem retrieval, scoring, or its Dynamic checkpoint.  The adapter supplies
only structurally compatible, no-op ReMe custody objects; it rejects manifests
that include a ReMe arm.
"""
from __future__ import annotations
import contextlib
from typing import Any

class _Service:
    proc = None
    base_url = "disabled://copromem-only"

class _Fixed:
    def __init__(self, **_: Any): pass
    def checkpoint(self, **_: Any) -> dict[str, str]: return {"checkpoint_sha256": "copromem-only-no-reme"}
    def reconcile(self) -> dict[str, object]: return {"mode": "copromem_only", "completed_count": 0}

class _Dynamic:
    def restore_latest(self) -> None: return None
    def reconcile(self) -> dict[str, object]: return {"mode": "copromem_only", "completed_count": 0}
    def callback(self, *_: Any, **__: Any):
        raise RuntimeError("ReMe Dynamic callback is forbidden in a CoProMem-only manifest")

def install(base: Any, arms: list[str]) -> None:
    if any(str(arm).startswith("official_upstream_reme") for arm in arms):
        return
    @contextlib.contextmanager
    def no_services(*_: Any, **__: Any):
        yield {"reme-fixed": _Service(), "reme-dynamic": _Service(), "reme-dynamic-verifier": _Service()}
    def no_post(*_: Any, **__: Any) -> dict[str, object]: return {"mode": "copromem_only"}
    base.services = no_services
    base.official_post = no_post
    base.ReMeFixedIntegrityManager = _Fixed
    base._dynamic_checkpoint = lambda *_args, **_kwargs: _Dynamic()
