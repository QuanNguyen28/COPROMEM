#!/usr/bin/env python3
"""Versioned engineering runner for CoProMem v6.2.2 semantic retrieval.

This is a configuration layer over the maintained v6.1 five-arm orchestration,
not a fork of its executor, scorer, checkpoint, or ReMe lifecycle.  Its sole
method change is the public, task-conditioned CoProMem retrieval boundary.
It requires its own allocation audit and never opens or edits a v6.2.1 run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import sys
from collections.abc import Mapping
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
os.environ.setdefault("COPROMEM_EVALUATION_RUNNER", str(pathlib.Path(__file__).resolve()))

from copromem.experiments.reme_copromem.runner import write_json
from copromem.experiments.reme_copromem.contrastive_v6_runner import semantic_spine_task_batch_update
from copromem.experiments.reme_copromem.runtime_identity_v3 import IDENTITY_VERSION as RUNTIME_IDENTITY_V3, build_evaluation_identity_v3
from copromem.experiments.reme_copromem.task_conditioned_retrieval_v622 import (
    POLICY_VERSION, derive_task_query, frozen_policy, reproduce_retrieval, retrieve,
    validate_task_query,
)
from scripts import run_v61_exploratory_evaluation as base


PROTOCOL = "v6_2_2_semantic_spine_engineering_001"
RUN_NAME = "v6_2_2_semantic_spine_engineering_001"
ARMS = ["no_memory", "official_upstream_reme_fixed", "official_upstream_reme_dynamic",
        "copromem_v6_2_2_fixed", "copromem_v6_2_2_dynamic"]
CALL_LIMITS = {"executor": 900, "reme_lifecycle": 128, "reme_embedding": 512,
               "copromem_decomposition": 0}
HARD_CAP_USD = 300
ALLOCATION_NAME = "allocation-audit-v622.json"
V622_BANK_ROOT: pathlib.Path | None = None


def _bank_identities() -> tuple[dict[str, Any], dict[str, Any]]:
    if V622_BANK_ROOT is None:
        raise RuntimeError("v6.2.2 bank root is not configured")
    report, _legacy_gate = base.identities_original()
    gate_path = V622_BANK_ROOT / "semantic-admission-gate.json"
    bank_path = V622_BANK_ROOT / "fixed-bank.json"
    if not gate_path.is_file() or not bank_path.is_file():
        raise RuntimeError("v6.2.2 admitted bank artifacts are absent")
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    bank = json.loads(bank_path.read_text(encoding="utf-8"))
    if (gate.get("version") != "copromem-v6.2.2-bank-admission-v1" or gate.get("passed") is not True
            or gate.get("provider_calls") != 0 or gate.get("state_sha256") != base.digest(bank)):
        raise RuntimeError("v6.2.2 bank admission identity is invalid")
    return report, gate


def _retrieval_record(*, state: Mapping[str, Any], query_operations: list[str], registry_sha256: str,
                      task_query: Mapping[str, Any] | None = None,
                      callable_registry: Mapping[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    """Adapter preserving the maintained runner call boundary exactly."""
    if callable_registry is None or task_query is None:
        raise ValueError("v6.2.2 retrieval requires frozen registry and public query provenance")
    if registry_sha256 != callable_registry.get("registry_sha256"):
        raise ValueError("v6.2.2 runner registry identity mismatch")
    if list(query_operations) != list(task_query.get("canonical_query_operations", ())):
        raise ValueError("v6.2.2 query operation boundary mismatch")
    guidance, provenance = retrieve(state, task_query, callable_registry)
    if guidance != reproduce_retrieval(state, task_query, callable_registry, provenance):
        raise ValueError("v6.2.2 retrieval cannot reproduce offline")
    return guidance, provenance


def _configure(run: pathlib.Path) -> None:
    audit_path = run / ALLOCATION_NAME
    if not audit_path.is_file():
        raise RuntimeError("frozen public engineering allocation audit is absent")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    selected = audit.get("selected_task_ids")
    if not isinstance(selected, list) or len(selected) != 3 or len(set(selected)) != 3:
        raise RuntimeError("v6.2.2 engineering allocation requires exactly three distinct task IDs")
    if audit.get("payloads_opened") is not False or audit.get("selection_source") != "public_pre_execution_metadata_only":
        raise RuntimeError("v6.2.2 allocation is not pre-payload public-only evidence")
    if audit.get("compatible_task_count") != 2 or audit.get("negative_control_count") != 1:
        raise RuntimeError("v6.2.2 allocation must preregister two compatible tasks and one negative control")
    if audit.get("retrieval_policy_version") != POLICY_VERSION:
        raise RuntimeError("v6.2.2 allocation does not bind the semantic-spine policy")
    bank_record = audit.get("copromem_bank")
    if not isinstance(bank_record, Mapping):
        raise RuntimeError("v6.2.2 allocation lacks an admitted bank record")
    bank_root = pathlib.Path(str(bank_record.get("path") or ""))
    if not bank_root.is_absolute():
        raise RuntimeError("v6.2.2 bank path must be absolute")
    for name, field in (("fixed-bank.json", "fixed_bank_file_sha256"),
                        ("semantic-admission-gate.json", "admission_gate_file_sha256"),
                        ("recovery-report.json", "recovery_report_file_sha256")):
        path = bank_root / name
        if not path.is_file() or base.file_sha(path) != bank_record.get(field):
            raise RuntimeError(f"v6.2.2 bank artifact identity mismatch: {name}")
    try:
        historical_exposure = float(audit["historical_settled_exposure_usd"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("v6.2.2 allocation lacks settled historical exposure") from exc
    if not math.isfinite(historical_exposure) or historical_exposure < 0:
        raise RuntimeError("v6.2.2 allocation has invalid settled historical exposure")
    base.PROTOCOL = PROTOCOL
    base.ARMS = list(ARMS)
    base.FROZEN_TASK_IDS = list(selected)
    base.EVALUATION_SPLIT = str(audit.get("split") or "test_normal")
    base.HARD_CAP_USD = HARD_CAP_USD
    base.CALL_LIMITS = dict(CALL_LIMITS)
    base.HISTORICAL_EXPOSURE = historical_exposure
    base.COPRO_FIXED_ARM = "copromem_v6_2_2_fixed"
    base.COPRO_DYNAMIC_ARM = "copromem_v6_2_2_dynamic"
    base.TASK_MAJOR_ARM_FIRST = True
    base.PREEXISTING_RUN_FILES = {ALLOCATION_NAME, "engineering-protocol.json"}
    global V622_BANK_ROOT
    V622_BANK_ROOT = bank_root
    base.COPRO = bank_root
    if not hasattr(base, "identities_original"):
        base.identities_original = base.identities
    base.identities = _bank_identities
    # These assignments are intentionally localized to this versioned entry
    # point.  Historical v6/v6.2 runners retain their frozen retrieval method.
    base.derive_task_query = derive_task_query
    base.validate_task_query = validate_task_query
    base.retrieval_record = _retrieval_record
    base.reproduce_retrieval = reproduce_retrieval
    base.semantic_task_batch_update = semantic_spine_task_batch_update


def prepare(run: pathlib.Path) -> None:
    _configure(run)
    base.prepare(run)
    template_path = run / "template.json"
    template = json.loads(template_path.read_text(encoding="utf-8"))
    allocation_bytes = (run / ALLOCATION_NAME).read_bytes()
    template["method"] = {
        "copromem": POLICY_VERSION,
        "retrieval": "task-supported semantic-spine projection; ambiguous schemas abstain",
        "analysis_scope": "engineering integration validation; not efficacy or superiority evidence",
    }
    template["method_policy"] = frozen_policy()
    template["evaluation"].update({
        "allocation_audit_sha256": hashlib.sha256(allocation_bytes).hexdigest(),
        "expected_trajectories": 30,
        "compatible_task_count": 2,
        "negative_control_count": 1,
    })
    template["budget"].update({"historical_settled_exposure": base.HISTORICAL_EXPOSURE,
                                "hard_cap_usd": HARD_CAP_USD})
    # V3 is generated only after every semantic template field exists.  The
    # record is then verified again by the maintained base runner at startup,
    # restart, each pre-task checkpoint, and terminal reconciliation.
    template["runtime_identity_version"] = RUNTIME_IDENTITY_V3
    runtime, inputs = build_evaluation_identity_v3(root=ROOT, manifest=template)
    write_json(run / "runtime-identity.json", runtime)
    write_json(run / "runtime-identity.binding.json", {
        "runtime_identity_sha256": runtime["runtime_identity_sha256"],
        "runtime_identity_record_sha256": base.file_sha(run / "runtime-identity.json"),
    })
    template["runtime_identity_inputs"] = inputs
    template["runtime_identity_sha256"] = runtime["runtime_identity_sha256"]
    template["runtime_identity_file_sha256"] = base.file_sha(run / "runtime-identity.json")
    write_json(template_path, template)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "freeze", "preflight", "run"])
    parser.add_argument("--run", required=True, type=pathlib.Path)
    args = parser.parse_args(); args.run = args.run.resolve()
    _configure(args.run)
    if args.command == "prepare":
        prepare(args.run)
    elif args.command == "freeze":
        base.freeze(args.run)
    elif args.command == "preflight":
        base.load(args.run); base.st(args.run, "preflight_passed")
    else:
        base.run(args.run)


if __name__ == "__main__":
    main()
