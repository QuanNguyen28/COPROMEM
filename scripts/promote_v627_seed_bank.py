#!/usr/bin/env python3
"""Promote one completed v6.2.7 seed run into an immutable next seed bank.

The promotion is entirely offline: it verifies a completed checkpoint prefix
and writes a new bank record that references, rather than edits, source
evidence.  It deliberately has no provider, executor, scorer, or AppWorld
dependency.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from copromem.experiments.reme_copromem.contrastive_v6_runner import digest
from copromem.experiments.reme_copromem.copromem_dynamic_checkpoint import CoProMemDynamicCheckpointManager


def file_sha(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"missing immutable source file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path.name}")
    return value


def atomic_json(path: Path, value: Mapping[str, Any]) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(body); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, path)
    try:
        directory = os.open(str(path.parent), os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    except OSError:
        pass
    return hashlib.sha256(body).hexdigest()


def promote(source: Path, output: Path) -> dict[str, Any]:
    source, output = source.resolve(), output.resolve()
    if output.exists():
        raise ValueError("refusing to overwrite an immutable promoted bank")
    manifest_path, status_path = source / "manifest.json", source / "runner-status.json"
    manifest, status = read(manifest_path), read(status_path)
    if status.get("state") != "completed":
        raise ValueError("seed source is not completed")
    terminal_path = source / "terminal-reconciliation.json"
    terminal = read(terminal_path)
    if terminal.get("valid") is not True:
        raise ValueError("seed terminal reconciliation is not valid")
    checkpoint_root = source / "copromem-dynamic-checkpoints"
    initial = read(checkpoint_root / "initial.json")
    tasks = initial.get("ordered_tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("seed checkpoint order is invalid")
    manager = CoProMemDynamicCheckpointManager(
        root=checkpoint_root,
        manifest_sha256=file_sha(manifest_path),
        source_identity_sha256=str(initial.get("source_identity_sha256") or ""),
        registry_sha256=str(initial.get("registry_sha256") or ""),
        ordered_tasks=tasks,
        fixed_initial_state=initial["fixed_initial_state"],
        dynamic_initial_state=initial["dynamic_initial_state"],
    )
    prefix = manager.reconcile(ledger_reconciled=True, fixed_current_state=initial["fixed_initial_state"])
    if prefix.get("completed_task_count") != len(tasks) or prefix.get("next_transition") != "run_reconciled":
        raise ValueError("seed Dynamic checkpoint prefix is incomplete")
    marker = manager.validate_run_reconciled()
    state = prefix["dynamic_state"]
    report = {
        "version": "copromem-v6.2.7-seed-bank-promotion-v1",
        "source_run": str(source), "source_manifest_sha256": file_sha(manifest_path),
        "source_runtime_identity_sha256": manifest.get("runtime_identity_sha256"),
        "source_terminal_reconciliation_sha256": file_sha(terminal_path),
        "source_run_reconciled_sha256": marker.get("record_sha256"),
        "source_checkpoint_initial_sha256": file_sha(checkpoint_root / "initial.json"),
        "source_checkpoint_root": str(checkpoint_root),
        "ordered_tasks": tasks,
        "state_sha256": digest(state),
    }
    report["report_sha256"] = digest(report)
    output.mkdir(parents=True)
    atomic_json(output / "fixed-bank.json", state)
    report_hash = atomic_json(output / "recovery-report.json", report)
    gate = {"version": "copromem-v6.2.7-seed-bank-promotion-v1", "passed": True, "provider_calls": 0,
            "state_sha256": digest(state), "source_manifest_sha256": report["source_manifest_sha256"],
            "recovery_report_sha256": report_hash}
    gate["gate_sha256"] = digest(gate)
    atomic_json(output / "semantic-admission-gate.json", gate)
    return {"bank_sha256": digest(state), "gate_sha256": gate["gate_sha256"], "report_sha256": report["report_sha256"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(promote(args.source, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
