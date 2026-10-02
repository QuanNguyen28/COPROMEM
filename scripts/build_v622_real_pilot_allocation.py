#!/usr/bin/env python3
"""Freeze a public-only 100-task allocation for the v6.2.2 real pilot.

This command intentionally knows only the published ``test_normal`` inventory,
durable custody records, and already-frozen bank identities.  It never imports
AppWorld or opens a task payload.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from copromem.experiments.reme_copromem.medium_allocation import allocate_round_robin, canonical_digest
from copromem.experiments.reme_copromem.runner import write_json
from copromem.experiments.reme_copromem.v61_custody import classify


COUNT = 100
ALLOCATION_NAME = "allocation-audit-real-100.json"
COPRO_BANK_LOCATOR = "/mnt/e/Project/AAMAS/COPROMEM-review/artifacts/zero-cost-validation/v622-attested-semantic-spine-bank-003-clean-runtime"
RB_BANK_LOCATOR = "/mnt/e/Project/AAMAS/reasoningbank-appworld-artifacts/reasoningbank_appworld_engineering_016_recovery/reasoningbank-dynamic-checkpoints/snapshots/0006.json"
PREDECESSOR_LEDGER = ROOT / "artifacts/research/official_reme_copromem_pilot/v6_2_2_parallel_baseline_pilot_005_protocol_label_fix/ledger.jsonl"


def sha256(path: pathlib.Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _native(locator: str) -> pathlib.Path:
    """Resolve the one portable E-backed locator on Windows or WSL."""
    if os.name == "nt" and locator.startswith("/mnt/") and len(locator) > 6:
        return pathlib.Path(locator[5].upper() + ":" + locator[6:])
    return pathlib.Path(locator)


def _bank_records() -> dict[str, Any]:
    copro_bank, rb_bank = _native(COPRO_BANK_LOCATOR), _native(RB_BANK_LOCATOR)
    fixed, gate, report = (copro_bank / "fixed-bank.json", copro_bank / "semantic-admission-gate.json",
                           copro_bank / "recovery-report.json")
    if not all(path.is_file() for path in (fixed, gate, report, rb_bank)):
        raise RuntimeError("a frozen CoProMem or ReasoningBank bank artifact is absent")
    bank = json.loads(fixed.read_text(encoding="utf-8")); admitted = json.loads(gate.read_text(encoding="utf-8"))
    rb = json.loads(rb_bank.read_text(encoding="utf-8"))
    return {
        "copromem_bank": {"path": COPRO_BANK_LOCATOR, "fixed_bank_file_sha256": sha256(fixed),
                           "admission_gate_file_sha256": sha256(gate), "recovery_report_file_sha256": sha256(report),
                           "semantic_state_sha256": admitted.get("state_sha256")},
        "reasoningbank_bank": {"path": RB_BANK_LOCATOR, "file_sha256": sha256(rb_bank),
                                "semantic_state_sha256": rb.get("semantic_state_sha256"),
                                "source_run": "reasoningbank_appworld_engineering_016_recovery",
                                "source_terminal_status": "ENGINEERING-VALIDATED"},
    }


def _historical_exposure() -> dict[str, Any]:
    """Carry the prior append-only cumulative ledger without rewriting it."""
    if not PREDECESSOR_LEDGER.is_file():
        raise RuntimeError("the immediate predecessor ledger is absent")
    rows = [json.loads(line) for line in PREDECESSOR_LEDGER.read_text(encoding="utf-8").splitlines()]
    reserved = {str(row["id"]): float(row["usd"]) for row in rows if row.get("event") == "reserve"}
    settled = {str(row["id"]): float(row["usd"]) for row in rows if row.get("event") == "settle"}
    if set(settled) - set(reserved):
        raise RuntimeError("predecessor ledger has a settlement without a reservation")
    return {"historical_source_ledger": str(PREDECESSOR_LEDGER), "historical_source_ledger_sha256": sha256(PREDECESSOR_LEDGER),
            "historical_settled_exposure_usd": sum(settled.values()),
            "historical_unresolved_reserved_exposure_usd": sum(reserved[item] for item in reserved if item not in settled),
            "historical_reservation_count": len(reserved), "historical_settlement_count": len(settled)}


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--run", required=True, type=pathlib.Path)
    args = parser.parse_args(); run = args.run.resolve(); run.mkdir(parents=True, exist_ok=True)
    inventory_path = ROOT / "research/reme_copromem_fixed_dynamic_review/v62-medium-public-test-normal-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8")); task_ids = set(map(str, inventory["task_ids"]))
    custody = classify(ROOT, inventory_path, include_research=False, candidate_ids=task_ids)
    known = {item["task_id"] for item in custody["decisions"]}
    custody["decisions"].extend({"task_id": task_id, "classification": "public_mention_only",
                                  "evidence": [{"path": str(inventory_path.relative_to(ROOT)).replace("\\\\", "/"),
                                                "category": "public_mention_only", "reason": "permitted public inventory"}]}
                                for task_id in sorted(task_ids - known))
    custody["decisions"].sort(key=lambda item: item["task_id"])
    custody["decision_trace_sha256"] = canonical_digest(custody["decisions"])
    allocation = dict(allocate_round_robin(inventory_ids=task_ids, hard_exposed_ids=custody["hard_exclusion"],
                                            ambiguous_ids=custody["ambiguous_exclusion"], count=COUNT))
    if not allocation["sufficient"]:
        raise RuntimeError("fewer than 100 public, non-hard-exposed test_normal IDs are available")
    registry = json.loads((ROOT / "research/reme_copromem_fixed_dynamic_review/appworld_public_tool_schema_registry_v5_3.json").read_text(encoding="utf-8"))
    allocation.update({"version": "v6.2.2-real-pilot-public-allocation-v1", "selection_source": "public_pre_execution_metadata_only",
                       "payloads_opened": False, "task_count": COUNT, "custody_trace_sha256": custody["decision_trace_sha256"],
                       "public_inventory_file_sha256": canonical_digest(inventory), "registry_sha256": registry["registry_sha256"],
                       "selection_commits_all_selected_ids_to_exposure": True, **_bank_records(), **_historical_exposure()})
    write_json(run / "custody-audit.json", custody)
    write_json(run / ALLOCATION_NAME, allocation)


if __name__ == "__main__":
    main()
