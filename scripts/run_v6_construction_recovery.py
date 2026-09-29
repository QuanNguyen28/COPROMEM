#!/usr/bin/env python3
"""Restart-safe, construction-only successor for v6 shared acquisition 001.

It consumes the immutable 24-trajectory pool and the separately reconstructed
CoProMem v6 bank.  It has no executor or scorer path, so acquisition cannot be
replayed from this command.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
os.environ.setdefault("COPROMEM_ROOT", str(ROOT))
import sys
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from copromem.experiments.reme_copromem.runner import AppendOnlyLedger, append, v5_budget_bound, write_json
from scripts.run_v6_shared_acquisition import c_free_gib, construct_reme, file_sha, git_head

SOURCE_RUN = ROOT / "artifacts/research/official_reme_copromem_pilot/v6_shared_acquisition_001"
SOURCE_MANIFEST_SHA256 = "422a45f8925b82dd83287bb10642a857fd3753b77570ccadb069f4ed310ad607"
COPRO_RECOVERY = SOURCE_RUN / "copromem-v6.1-semantic-recovery-003"


def _event(run: pathlib.Path, event: str, **extra: Any) -> None:
    append(run / "progress.jsonl", {"event": event, "time_ns": time.time_ns(), **extra})


def _status(run: pathlib.Path, state: str, **extra: Any) -> None:
    write_json(run / "runner-status.json", {"state": state, "pid": os.getpid(), "updated_ns": time.time_ns(), **extra})


def _settled_exposure(path: pathlib.Path) -> tuple[float, int]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    reserve = {str(row["id"]): float(row["usd"]) for row in rows if row.get("event") == "reserve"}
    settled = {str(row["id"]): float(row["usd"]) for row in rows if row.get("event") == "settle"}
    unresolved = set(reserve) - set(settled)
    if unresolved:
        raise RuntimeError("source ledger has unresolved reservation")
    return sum(settled.values()), len(settled)


def _source_identity() -> dict[str, Any]:
    if file_sha(SOURCE_RUN / "manifest.json") != SOURCE_MANIFEST_SHA256:
        raise RuntimeError("source acquisition manifest hash mismatch")
    recovery = json.loads((COPRO_RECOVERY / "semantic-recovery-report.json").read_text(encoding="utf-8"))
    if recovery.get("source_manifest_sha256") != SOURCE_MANIFEST_SHA256 or not recovery.get("gate", {}).get("passed"):
        raise RuntimeError("v6.1 semantic CoProMem bank has not passed admission")
    ledger = SOURCE_RUN / "ledger.jsonl"
    exposure, settlement_count = _settled_exposure(ledger)
    return {"source_manifest_sha256": SOURCE_MANIFEST_SHA256, "source_pool_sha256": file_sha(SOURCE_RUN / "shared-pool.json"),
            "source_ledger_sha256": file_sha(ledger), "source_settled_exposure_usd": exposure,
            "source_settlement_count": settlement_count, "copromem_semantic_report_sha256": recovery["report_sha256"],
            "copromem_state_sha256": recovery["gate"]["state_sha256"]}


def prepare(run: pathlib.Path) -> None:
    if run.exists() and any(run.iterdir()):
        raise RuntimeError("recovery run directory is not empty")
    identity = _source_identity()
    limits = {"executor": 0, "reme_lifecycle": 128, "reme_embedding": 512, "copromem_decomposition": 0}
    budget = v5_budget_bound(call_limits=limits, historical_usd=identity["source_settled_exposure_usd"], lifecycle_input_ceiling=131072)
    budget.update({"hard_cap_usd": 100.0, "call_limits": limits, "fits_hard_cap": budget["all_in_usd"] <= 100.0})
    if not budget["fits_hard_cap"]:
        raise RuntimeError("all-inclusive construction recovery bound exceeds USD 100")
    value = {"protocol": "v6_shared_acquisition_001_construction_recovery_001", "purpose": "infrastructure_only_rebuild_from_immutable_shared_pool",
             "git_commit": git_head(), "source_identity": identity, "budget": budget,
             "execution": {"c_floor_gib": 10.0, "executor_dispatch_permitted": False, "provider_routes": "unchanged_from_source_manifest"},
             "provider_calls_before_recovery": 0}
    write_json(run / "template.json", value)


def freeze(run: pathlib.Path) -> None:
    template = run / "template.json"
    if not template.exists() or (run / "manifest.json").exists():
        raise RuntimeError("prepared recovery template required")
    value = json.loads(template.read_text(encoding="utf-8"))
    if value["git_commit"] != git_head():
        raise RuntimeError("source changed after recovery preparation")
    write_json(run / "manifest.json", value)
    (run / "manifest.sha256").write_text(file_sha(run / "manifest.json") + "\n", encoding="utf-8")


def load(run: pathlib.Path) -> dict[str, Any]:
    manifest = run / "manifest.json"
    if file_sha(manifest) != (run / "manifest.sha256").read_text(encoding="utf-8").strip():
        raise RuntimeError("recovery manifest hash mismatch")
    value = json.loads(manifest.read_text(encoding="utf-8"))
    if value.get("git_commit") != git_head() or c_free_gib() < float(value["execution"]["c_floor_gib"]):
        raise RuntimeError("recovery source or C-drive guard failed")
    if value["source_identity"] != _source_identity():
        raise RuntimeError("immutable source identity changed")
    if not value["budget"]["fits_hard_cap"]:
        raise RuntimeError("recovery budget guard failed")
    return value


def _lock(run: pathlib.Path) -> pathlib.Path:
    lock = run / "runner.lock"
    if lock.exists():
        prior = int(json.loads(lock.read_text(encoding="utf-8"))["pid"])
        try: os.kill(prior, 0)
        except ProcessLookupError: lock.unlink()
        else: raise RuntimeError("duplicate construction-recovery runner is active")
    write_json(lock, {"pid": os.getpid(), "manifest_sha256": file_sha(run / "manifest.json")})
    return lock


def execute(run: pathlib.Path) -> None:
    value = load(run); lock = _lock(run)
    ledger = AppendOnlyLedger(run / "ledger.jsonl", 100.0, value["budget"]["call_limits"])
    try:
        historical_id = "v6-source-settled-exposure-carry-forward"
        if not (run / "ledger.jsonl").exists() or not (run / "ledger.jsonl").read_text(encoding="utf-8").strip():
            amount = float(value["source_identity"]["source_settled_exposure_usd"])
            ledger.reserve(historical_id, amount, {"role": "historical_carry_forward", "source": "v6_shared_acquisition_001"})
            ledger.settle(historical_id, amount, {"role": "historical_carry_forward", "source": "v6_shared_acquisition_001"})
        _status(run, "running", manifest_sha256=file_sha(run / "manifest.json")); _event(run, "construction_recovery_started")
        records = json.loads((SOURCE_RUN / "shared-pool.json").read_text(encoding="utf-8"))["trajectories"]
        reme = construct_reme(run, records, ledger)
        reserved, settled = ledger._call_state()
        if set(reserved) - set(settled):
            raise RuntimeError("unsettled provider reservation")
        report = {"classification": "ACQUISITION READY: immutable shared pool produced independently constructed upstream ReMe and repaired deterministic CoProMem v6 banks.",
                  "manifest_sha256": file_sha(run / "manifest.json"), "source_identity": value["source_identity"], "reme": reme,
                  "copromem": json.loads((COPRO_RECOVERY / "semantic-admission-gate.json").read_text(encoding="utf-8")), "ledger_exposure_usd": ledger._exposure(),
                  "c_free_gib": c_free_gib()}
        write_json(run / "FINAL_ACQUISITION_REPORT.json", report)
        _status(run, "completed", final_report_sha256=file_sha(run / "FINAL_ACQUISITION_REPORT.json")); _event(run, "construction_recovery_completed")
    except BaseException as exc:
        _status(run, "failed", failure_class=type(exc).__name__, failure_message=str(exc)[:240])
        _event(run, "construction_recovery_failed", failure_class=type(exc).__name__)
        raise
    finally:
        if lock.exists(): lock.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("prepare", "freeze", "preflight", "run")); parser.add_argument("--run", type=pathlib.Path, required=True); args = parser.parse_args()
    if args.command == "prepare": prepare(args.run)
    elif args.command == "freeze": freeze(args.run)
    elif args.command == "preflight":
        value = load(args.run); _status(args.run, "preflight_passed", manifest_sha256=file_sha(args.run / "manifest.json"), c_free_gib=c_free_gib()); _event(args.run, "preflight_passed"); print(json.dumps({"provider_calls": 0, "all_in_usd": value["budget"]["all_in_usd"]}, sort_keys=True))
    else: execute(args.run)
    return 0


if __name__ == "__main__": raise SystemExit(main())
