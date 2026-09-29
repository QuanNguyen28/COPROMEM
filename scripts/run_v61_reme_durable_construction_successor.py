#!/usr/bin/env python3
"""Durable full-bank ReMe successor for the immutable v6.1 acquisition pool.

This intentionally never reads the abandoned in-memory bank from construction
001.  Its per-item snapshots make a provider-call replay impossible after an
ambiguous interruption: the runner stops rather than guessing which request
settled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
os.environ.setdefault("COPROMEM_ROOT", str(ROOT))

from copromem.experiments.reme_copromem.runner import AppendOnlyLedger, append, official_post, services, v5_budget_bound, write_json
from copromem.integrations.reme.bank import construct_durable_snapshot_bank, freeze_durable_final_snapshot, load_clone
from scripts.run_v6_shared_acquisition import c_free_gib, file_sha, git_head

SOURCE = ROOT / "artifacts/research/official_reme_copromem_pilot/v6_shared_acquisition_001"
FAILED = ROOT / "artifacts/research/official_reme_copromem_pilot/v6_1_exploratory_diagnostic_construction_001"
COPRO_V61 = SOURCE / "copromem-v6.1-semantic-recovery-003"
SOURCE_MANIFEST_SHA256 = "422a45f8925b82dd83287bb10642a857fd3753b77570ccadb069f4ed310ad607"
FAILED_MANIFEST_SHA256 = "9525b30ac2fc56b179fcb6031a46597324a7dcb8d8b33847405df9488f42bf78"


def _event(run: pathlib.Path, name: str, **extra: Any) -> None:
    append(run / "progress.jsonl", {"event": name, "time_ns": time.time_ns(), **extra})


def _status(run: pathlib.Path, state: str, **extra: Any) -> None:
    write_json(run / "runner-status.json", {"state": state, "pid": os.getpid(), "updated_ns": time.time_ns(), **extra})


def _ledger_identity(path: pathlib.Path) -> dict[str, Any]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    reservations = {str(row["id"]): float(row["usd"]) for row in rows if row.get("event") == "reserve"}
    settlements = {str(row["id"]): float(row["usd"]) for row in rows if row.get("event") == "settle"}
    unresolved = sorted(set(reservations) - set(settlements))
    return {"ledger_sha256": file_sha(path), "reserve_count": len(reservations), "settle_count": len(settlements),
            "unresolved_ids": unresolved, "settled_exposure_usd": sum(settlements.values())}


def _identity() -> dict[str, Any]:
    if file_sha(SOURCE / "manifest.json") != SOURCE_MANIFEST_SHA256:
        raise RuntimeError("immutable acquisition manifest hash mismatch")
    if file_sha(FAILED / "manifest.json") != FAILED_MANIFEST_SHA256:
        raise RuntimeError("failed construction manifest hash mismatch")
    failed_ledger = _ledger_identity(FAILED / "ledger.jsonl")
    if (failed_ledger["reserve_count"], failed_ledger["settle_count"], failed_ledger["unresolved_ids"]) != (11, 11, []):
        raise RuntimeError("failed construction ledger is not the required 11/11 settled state")
    if (FAILED / "reme" / "shared-bank.jsonl").exists() or (FAILED / "reme" / "shared-bank.complete.json").exists():
        raise RuntimeError("abandoned construction unexpectedly has a durable shared bank")
    semantic = json.loads((COPRO_V61 / "semantic-recovery-report.json").read_text(encoding="utf-8"))
    if not semantic.get("gate", {}).get("passed"):
        raise RuntimeError("v6.1 CoProMem recovery admission is not immutable/passed")
    return {"source_manifest_sha256": SOURCE_MANIFEST_SHA256, "source_pool_sha256": file_sha(SOURCE / "shared-pool.json"),
            "failed_construction_manifest_sha256": FAILED_MANIFEST_SHA256, "failed_construction_ledger": failed_ledger,
            "failed_construction_reason": "service exited after first item lifecycle/embedding calls; no durable vector-store snapshot or completed shared bank existed",
            "repeat_authorization": "full construction successor repeats every lifecycle/embedding call from immutable inputs; abandoned content is excluded",
            "copromem_v61_bank_sha256": semantic["gate"]["state_sha256"]}


def prepare(run: pathlib.Path) -> None:
    if run.exists() and any(run.iterdir()):
        raise RuntimeError("successor run directory is not empty")
    identity = _identity(); run.mkdir(parents=True, exist_ok=True)
    limits = {"executor": 0, "reme_lifecycle": 128, "reme_embedding": 512, "copromem_decomposition": 0}
    budget = v5_budget_bound(call_limits=limits, historical_usd=float(identity["failed_construction_ledger"]["settled_exposure_usd"]), lifecycle_input_ceiling=131072)
    if float(budget["all_in_usd"]) > 100.0:
        raise RuntimeError("successor conservative construction bound exceeds USD 100")
    manifest = {"protocol": "v6_1_exploratory_diagnostic_construction_002", "purpose": "full_durable_official_reme_bank_construction_successor",
                "git_commit": git_head(), "source_identity": identity,
                "durability": {"snapshot_directory": "reme/snapshots", "checkpoint": "reme/construction.jsonl",
                               "intent_journal": "reme/construction.intents.jsonl", "ordered_item_count": 24,
                               "snapshot_after_each_item": True, "reload_test_before_marker": True,
                               "resume_policy": "restore latest valid ordered snapshot; fail closed on ambiguity"},
                "execution": {"c_floor_gib": 10.0, "executor_dispatch_permitted": False, "official_reme_only": True,
                              "lifecycle_input_ceiling": 131072, "provider_route": "unchanged_from_frozen_v6_source"},
                "budget": {**budget, "hard_cap_usd": 100.0, "call_limits": limits, "fits_hard_cap": True}}
    write_json(run / "template.json", manifest)


def freeze(run: pathlib.Path) -> None:
    template = run / "template.json"
    if not template.is_file() or (run / "manifest.json").exists():
        raise RuntimeError("prepared successor template required")
    manifest = json.loads(template.read_text(encoding="utf-8"))
    if manifest["git_commit"] != git_head():
        raise RuntimeError("source changed after successor preparation")
    write_json(run / "manifest.json", manifest)
    (run / "manifest.sha256").write_text(file_sha(run / "manifest.json") + "\n", encoding="utf-8")


def load(run: pathlib.Path) -> dict[str, Any]:
    manifest = run / "manifest.json"
    if not manifest.is_file() or file_sha(manifest) != (run / "manifest.sha256").read_text(encoding="utf-8").strip():
        raise RuntimeError("successor manifest hash mismatch")
    value = json.loads(manifest.read_text(encoding="utf-8"))
    if value["git_commit"] != git_head() or _identity() != value["source_identity"]:
        raise RuntimeError("successor source identity changed")
    if c_free_gib() < float(value["execution"]["c_floor_gib"]):
        raise RuntimeError("C-drive floor breached")
    return value


def _lock(run: pathlib.Path) -> pathlib.Path:
    path = run / "runner.lock"
    if path.exists():
        try: os.kill(int(json.loads(path.read_text(encoding="utf-8"))["pid"]), 0)
        except ProcessLookupError: path.unlink()
        else: raise RuntimeError("duplicate ReMe construction successor is active")
    write_json(path, {"pid": os.getpid(), "manifest_sha256": file_sha(run / "manifest.json")})
    return path


def _inputs() -> list[dict[str, Any]]:
    rows = json.loads((SOURCE / "shared-pool.json").read_text(encoding="utf-8"))["trajectories"]
    inputs = [{"trajectory_id": str(row["acquisition_identity"]), "task_id": str(row["task_id"]), "task_history": row["history"],
               "after_score": row["after_score"], "history_sha256": row["history_sha256"]} for row in rows]
    if len(inputs) != 24 or len({row["trajectory_id"] for row in inputs}) != 24:
        raise RuntimeError("immutable ReMe source input coverage is not exactly 24")
    return inputs


def _event_callback(run: pathlib.Path, record: dict[str, Any]) -> None:
    payload = {key: value for key, value in record.items() if key != "event"}
    _event(run, "reme_durable_construction", upstream_event=record.get("event"), **payload)


def _require_settled(ledger: AppendOnlyLedger) -> None:
    reserved, settled = ledger._call_state()
    if set(reserved) - set(settled):
        raise RuntimeError("successor ledger has unresolved reservation")


def run_construction(run: pathlib.Path) -> None:
    value = load(run); lock = _lock(run); ledger = AppendOnlyLedger(run / "ledger.jsonl", 100.0, value["budget"]["call_limits"])
    try:
        if not (run / "ledger.jsonl").exists() or not (run / "ledger.jsonl").read_text(encoding="utf-8").strip():
            amount = float(value["source_identity"]["failed_construction_ledger"]["settled_exposure_usd"])
            ledger.reserve("historical-failed-construction-001", amount, {"role": "historical_carry_forward", "source": "v6_1_exploratory_diagnostic_construction_001"})
            ledger.settle("historical-failed-construction-001", amount, {"role": "historical_carry_forward", "source": "v6_1_exploratory_diagnostic_construction_001"})
        _require_settled(ledger)
        _status(run, "running", manifest_sha256=file_sha(run / "manifest.json")); _event(run, "construction_successor_started")
        inputs = _inputs(); reme_dir = run / "reme"; snapshot_dir = reme_dir / "snapshots"; checkpoint = reme_dir / "construction.jsonl"
        with services(run, run / "ledger.jsonl", run / "progress.jsonl", 100.0,
                      ["reme-builder", "reme-verifier", "reme-fixed", "reme-dynamic"], lifecycle_input_ceiling=131072) as svc:
            shared_hash, count = construct_durable_snapshot_bank(official_post, svc["reme-builder"].base_url, svc["reme-verifier"].base_url,
                                                                   inputs, checkpoint, snapshot_dir, lambda record: _event_callback(run, record))
            if count != 24:
                raise RuntimeError("durable ReMe construction did not account for every source trajectory")
            shared = reme_dir / "shared-bank.jsonl"
            shared_hash = freeze_durable_final_snapshot(snapshot_dir, count, shared)
            fixed_hash = load_clone(official_post, svc["reme-fixed"].base_url, shared, shared_hash)
            dynamic_hash = load_clone(official_post, svc["reme-dynamic"].base_url, shared, shared_hash)
            probe = official_post(svc["reme-fixed"].base_url, "retrieve_task_memory", {"query": str(inputs[0]["task_history"][0].get("content", "")), "top_k": 1,
                                                                                           "enable_llm_build": False, "enable_llm_rerank": False, "enable_llm_rewrite": False})
            write_json(reme_dir / "retrieval-health.json", {"bank_sha256": shared_hash, "input_source": "immutable_acquisition_public_instruction",
                                                               "response_sha256": hashlib.sha256(json.dumps(probe, sort_keys=True).encode()).hexdigest()})
        _require_settled(ledger)
        final_snapshot = snapshot_dir / "after-0024.json"
        report = {"manifest_sha256": file_sha(run / "manifest.json"), "shared_bank_sha256": shared_hash, "fixed_clone_sha256": fixed_hash,
                  "dynamic_clone_sha256": dynamic_hash, "input_count": count, "final_snapshot_metadata_sha256": file_sha(final_snapshot),
                  "vector_and_memory_counts": json.loads(final_snapshot.read_text(encoding="utf-8")), "ledger_exposure_usd": ledger._exposure(),
                  "historical_failed_attempt_exposure_usd": value["source_identity"]["failed_construction_ledger"]["settled_exposure_usd"]}
        write_json(run / "FINAL_CONSTRUCTION_REPORT.json", report)
        _status(run, "completed", final_report_sha256=file_sha(run / "FINAL_CONSTRUCTION_REPORT.json")); _event(run, "construction_successor_completed", input_count=count)
    except BaseException as exc:
        _status(run, "failed", failure_class=type(exc).__name__, failure_message=str(exc)[:240]); _event(run, "construction_successor_failed", failure_class=type(exc).__name__)
        raise
    finally:
        if lock.exists(): lock.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("prepare", "freeze", "preflight", "run")); parser.add_argument("--run", type=pathlib.Path, required=True); args = parser.parse_args()
    if args.command == "prepare": prepare(args.run)
    elif args.command == "freeze": freeze(args.run)
    elif args.command == "preflight":
        value = load(args.run); _status(args.run, "preflight_passed", manifest_sha256=file_sha(args.run / "manifest.json"), c_free_gib=c_free_gib()); _event(args.run, "preflight_passed"); print(json.dumps({"provider_calls": 0, "all_in_usd": value["budget"]["all_in_usd"]}))
    else: run_construction(args.run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
