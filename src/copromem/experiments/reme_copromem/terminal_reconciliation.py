"""Read-only, multi-error terminal integrity gate for a v6.2 evaluation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .live_summary import build_live_summary, reconcile_artifacts


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_terminal_run(*, run_root: Path, manifest: Mapping[str, Any], runtime_verify: Callable[[], None],
                          copro_reconcile: Callable[[], Mapping[str, Any]], reme_dynamic_reconcile: Callable[[], Mapping[str, Any]],
                          reme_fixed_reconcile: Callable[[], Any], active_processes: Callable[[], bool],
                          historical_exposure: float, additional_checks: Mapping[str, Callable[[], Any]] | None = None) -> dict[str, Any]:
    """Return every observable discrepancy without mutating any run evidence."""
    failures: list[dict[str, str]] = []
    root = run_root.resolve()
    try:
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file() or _sha(manifest_path) != (root / "manifest.sha256").read_text(encoding="utf-8").strip():
            raise RuntimeError("manifest hash mismatch")
        if json.loads(manifest_path.read_text(encoding="utf-8")) != dict(manifest):
            raise RuntimeError("in-memory manifest differs from frozen file")
    except Exception as exc:
        failures.append({"gate": "manifest", "reason": str(exc)})
    for gate, check in (("runtime_identity", runtime_verify), ("copromem_dynamic_prefix", copro_reconcile),
                        ("reme_dynamic_prefix", reme_dynamic_reconcile), ("reme_fixed_integrity", reme_fixed_reconcile)):
        try:
            check()
        except Exception as exc:
            failures.append({"gate": gate, "reason": str(exc)})
    for gate, check in sorted((additional_checks or {}).items()):
        try:
            check()
        except Exception as exc:
            failures.append({"gate": str(gate), "reason": str(exc)})
    try:
        evaluation = manifest["evaluation"]
        registered_arms = manifest.get("arms")
        reconcile_artifacts(root / "artifacts", expected_tasks=evaluation["task_ids"], expected_seeds=evaluation["seeds"],
                           require_evidence=True, registered_arms=registered_arms)
        summary = build_live_summary(ledger_path=root / "ledger.jsonl", artifact_root=root / "artifacts",
            expected_tasks=evaluation["task_ids"], expected_seeds=evaluation["seeds"],
            historical_expected_usd=historical_exposure, state="completed", final=True,
            expected_trajectories=int(evaluation["expected_trajectories"]), registered_arms=registered_arms)
        if int(summary["completed"]) != int(evaluation["expected_trajectories"]):
            raise RuntimeError("terminal summary denominator mismatch")
    except Exception as exc:
        failures.append({"gate": "artifacts_ledger_summary", "reason": str(exc)})
    try:
        if active_processes():
            raise RuntimeError("owned runner or service remains active")
    except Exception as exc:
        failures.append({"gate": "process_ownership", "reason": str(exc)})
    return {"version": "v6.2-terminal-reconciliation-v1", "run_root_sha256": hashlib.sha256(str(root).encode()).hexdigest(),
            "valid": not failures, "failure_count": len(failures), "failures": failures}
