#!/usr/bin/env python3
"""Twelve-task, one-trial, Dynamic-only CoProMem v6.2.3 gate check.

This is deliberately a new, independently frozen diagnostic.  It cannot edit,
resume, or be aggregated as evidence from a v6.2.2 run.  Its only method
change is the versioned public terminal-discovery rule in v6.2.3; the v6.2.2
semantic projection, prerequisite, tie, occurrence, executor, scorer, and
Dynamic checkpoint contracts remain in force.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from copromem.experiments.reme_copromem.contrastive_v6_runner import semantic_spine_task_batch_update
from copromem.experiments.reme_copromem.evidence_contract import validate as validate_execution_evidence
from copromem.experiments.reme_copromem.contrastive_v6_runner import scorer_evidence_sha256
from copromem.experiments.reme_copromem.runner import write_json
from copromem.experiments.reme_copromem.runtime_identity_v3 import (
    IDENTITY_VERSION as RUNTIME_IDENTITY_V3,
    build_evaluation_identity_v3,
)
from copromem.experiments.reme_copromem.task_conditioned_retrieval_v623 import (
    POLICY_VERSION,
    derive_task_query,
    frozen_policy,
    reproduce_retrieval,
    retrieve,
    validate_task_query,
)
from copromem.integrations.reme.transport import PROVIDER as CHAT_PROVIDER
from copromem.integrations.reme.transport import verify_locked_chat_route_available
from scripts import run_v61_exploratory_evaluation as base
from scripts import run_v622_semantic_spine_engineering as v622


PROTOCOL = "v6_2_3_dynamic_guidance_check_001"
ARM = "copromem_v6_2_3_dynamic"
ARMS = [ARM]
TRIAL_SEED = 62301
TASK_COUNT = 12
HARD_CAP_USD = 20.0
CALL_LIMITS = {"executor": TASK_COUNT * 30, "reme_lifecycle": 0,
               "reme_embedding": 0, "copromem_decomposition": 0}
ALLOCATION_NAME = "allocation-audit-v623-dynamic.json"


def _external(path: str) -> Path:
    if os.name == "posix" and len(path) >= 3 and path[1:3] == ":\\":
        return Path("/mnt/" + path[0].lower() + path[2:].replace("\\", "/"))
    return Path(path)


REVIEW = _external(r"E:\Project\AAMAS\COPROMEM-review")
BANK_ROOT = REVIEW / "artifacts/zero-cost-validation/v622-attested-semantic-spine-bank-003-clean-runtime"


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _selection(task_ids: list[str]) -> list[str]:
    if len(set(task_ids)) != len(task_ids):
        raise RuntimeError("source task inventory contains duplicates")
    return sorted(task_ids, key=lambda task: hashlib.sha256(
        f"{PROTOCOL}:public-task-id:{task}".encode("utf-8")).hexdigest())[:TASK_COUNT]


def allocate(run: Path, source_manifest: Path) -> None:
    """Freeze a public-ID-only deterministic twelve-task allocation."""
    if run.exists() and any(run.iterdir()):
        raise RuntimeError("allocation target must be empty")
    source = json.loads(source_manifest.read_text(encoding="utf-8"))
    evaluation = source.get("evaluation", {})
    task_ids = list(evaluation.get("task_ids", ()))
    if not all(isinstance(item, str) for item in task_ids) or len(task_ids) < TASK_COUNT:
        raise RuntimeError("source manifest lacks a usable public task inventory")
    selected = _selection(task_ids)
    if len(selected) != TASK_COUNT:
        raise RuntimeError("allocation did not select twelve distinct public task IDs")
    bank = {
        "path": str(BANK_ROOT),
        "fixed_bank_file_sha256": _file_sha(BANK_ROOT / "fixed-bank.json"),
        "admission_gate_file_sha256": _file_sha(BANK_ROOT / "semantic-admission-gate.json"),
        "recovery_report_file_sha256": _file_sha(BANK_ROOT / "recovery-report.json"),
        "semantic_state_sha256": json.loads((BANK_ROOT / "semantic-admission-gate.json").read_text())["state_sha256"],
    }
    audit = {
        "version": "v6.2.3-dynamic-guidance-public-id-allocation-v1",
        "protocol": PROTOCOL,
        "selection_source": "frozen_source_manifest_public_task_ids_only",
        "payloads_opened": False,
        "source_manifest_path": str(source_manifest.resolve()),
        "source_manifest_sha256": _file_sha(source_manifest),
        "source_task_inventory_sha256": _sha(task_ids),
        "selection_rule": "sha256(protocol:public-task-id:<id>) ascending first 12",
        "selected_task_ids": selected,
        "split": str(evaluation.get("split") or "test_normal"),
        "trial_seeds": [TRIAL_SEED],
        "arms": ARMS,
        "copromem_bank": bank,
        "historical_settled_exposure_usd": 0.0,
        "cost_scope": "new v6.2.3 diagnostic calls only; bank construction is referenced, not recharged",
    }
    run.mkdir(parents=True, exist_ok=False)
    write_json(run / ALLOCATION_NAME, audit)


def _audit(run: Path) -> Mapping[str, Any]:
    path = run / ALLOCATION_NAME
    if not path.is_file():
        raise RuntimeError("v6.2.3 Dynamic allocation audit is absent")
    audit = json.loads(path.read_text(encoding="utf-8"))
    selected = audit.get("selected_task_ids")
    if (audit.get("version") != "v6.2.3-dynamic-guidance-public-id-allocation-v1" or
            audit.get("protocol") != PROTOCOL or audit.get("payloads_opened") is not False or
            audit.get("arms") != ARMS or audit.get("trial_seeds") != [TRIAL_SEED] or
            not isinstance(selected, list) or len(selected) != TASK_COUNT or len(set(selected)) != TASK_COUNT or
            any(not isinstance(item, str) for item in selected)):
        raise RuntimeError("v6.2.3 Dynamic allocation audit is invalid")
    bank = audit.get("copromem_bank")
    if not isinstance(bank, Mapping) or _external(str(bank.get("path") or "")) != BANK_ROOT:
        raise RuntimeError("v6.2.3 Dynamic allocation bank locator differs")
    for name, field in (("fixed-bank.json", "fixed_bank_file_sha256"),
                        ("semantic-admission-gate.json", "admission_gate_file_sha256"),
                        ("recovery-report.json", "recovery_report_file_sha256")):
        if not (BANK_ROOT / name).is_file() or _file_sha(BANK_ROOT / name) != bank.get(field):
            raise RuntimeError(f"v6.2.3 Dynamic bank artifact differs: {name}")
    if not math.isfinite(float(audit.get("historical_settled_exposure_usd", -1))) or float(audit["historical_settled_exposure_usd"]) != 0:
        raise RuntimeError("v6.2.3 Dynamic diagnostic may not carry unrelated historical cost")
    return audit


def _retrieval_record(*, state: Mapping[str, Any], query_operations: list[str], registry_sha256: str,
                      task_query: Mapping[str, Any] | None = None,
                      callable_registry: Mapping[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    if callable_registry is None or task_query is None:
        raise ValueError("v6.2.3 retrieval requires frozen registry and public query provenance")
    if registry_sha256 != callable_registry.get("registry_sha256"):
        raise ValueError("v6.2.3 runner registry identity mismatch")
    if list(query_operations) != list(task_query.get("canonical_query_operations", ())):
        raise ValueError("v6.2.3 query operation boundary mismatch")
    guidance, provenance = retrieve(state, task_query, callable_registry)
    if guidance != reproduce_retrieval(state, task_query, callable_registry, provenance):
        raise ValueError("v6.2.3 retrieval cannot reproduce offline")
    return guidance, provenance


def _single_trial_gate_check_update(*, artifacts: list[Mapping[str, Any]], registry: Mapping[str, Any],
                                    pre_state: Mapping[str, Any], evidence_paths: list[str | Path],
                                    run_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Durably authorize a one-trial *retrieval* check without learning.

    Semantic-spine learning intentionally requires at least two independent
    executions of the same task.  A one-trial gate check therefore validates
    its scored evidence but records a no-op transition instead of silently
    lowering that learning threshold.  The next Dynamic retrieval sees the
    same bank, and the manifest labels this run as a retrieval diagnostic.
    """
    if len(artifacts) != 1 or len(evidence_paths) != 1:
        raise ValueError("v6.2.3 single-trial gate check requires exactly one scored artifact")
    artifact = artifacts[0]
    scorer_hash = scorer_evidence_sha256(artifact)
    evidence = validate_execution_evidence(
        artifact, run_root=run_root, expected_registry_sha256=str(registry["registry_sha256"])
    )
    pre_hash = _sha(dict(pre_state))
    plan = {"version": "v6.2.3-single-trial-no-learning-v1", "pre_state_sha256": pre_hash,
            "artifact_trajectory_id": str(artifact.get("trajectory_id") or ""),
            "scorer_evidence_sha256": scorer_hash,
            "execution_evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
            "action": "no_semantic_update_single_trial_insufficient"}
    plan["plan_sha256"] = _sha(plan)
    validation = {"version": "v6.2.3-single-trial-no-learning-v1", "passed": True,
                  "reason": "semantic_spine_learning_requires_at_least_two_same_task_trials",
                  "pre_state_sha256": pre_hash, "artifact_trajectory_id": plan["artifact_trajectory_id"]}
    marker = {"state": "rejected", "reason": validation["reason"], "post_state_sha256": pre_hash}
    audit = {"state_format": pre_state.get("state_format"), "semantic_policy_version": POLICY_VERSION,
             "pre_state_sha256": pre_hash, "semantic_graph_audits": [], "plan": plan,
             "validation": validation, "marker": marker, "post_state_sha256": pre_hash,
             "diagnostic_no_learning": True}
    return dict(pre_state), marker, audit


def configure(run: Path) -> None:
    audit = _audit(run)
    base.SOURCE = REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_shared_acquisition_001"
    base.CONSTRUCTION = REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_1_exploratory_diagnostic_construction_003"
    base.PROTOCOL = PROTOCOL
    base.ARMS = list(ARMS)
    base.FROZEN_TASK_IDS = list(audit["selected_task_ids"])
    base.EVALUATION_SPLIT = str(audit["split"])
    base.EVALUATION_SEEDS = (TRIAL_SEED,)
    base.HARD_CAP_USD = HARD_CAP_USD
    base.CALL_LIMITS = dict(CALL_LIMITS)
    base.HISTORICAL_EXPOSURE = 0.0
    base.COPRO_FIXED_ARM = "copromem_v6_2_3_fixed_unregistered"
    base.COPRO_DYNAMIC_ARM = ARM
    base.TASK_MAJOR_ARM_FIRST = True
    base.PREEXISTING_RUN_FILES = {ALLOCATION_NAME}
    base.COPRO = BANK_ROOT
    v622.V622_BANK_ROOT = BANK_ROOT
    base.identities = v622._bank_identities
    base.derive_task_query = derive_task_query
    base.validate_task_query = validate_task_query
    base.retrieval_record = _retrieval_record
    base.reproduce_retrieval = reproduce_retrieval
    # Do not lower v6.2.2's >=2 same-task semantic-learning threshold merely
    # because this user-requested check has one trial.  The arm exercises the
    # Dynamic retrieval callback and durable task prefix, but commits no bank
    # update until a separately frozen multi-trial evaluation is used.
    base.semantic_task_batch_update = _single_trial_gate_check_update


def prepare(run: Path) -> None:
    configure(run)
    base.prepare(run)
    path = run / "template.json"
    template = json.loads(path.read_text(encoding="utf-8"))
    allocation = (run / ALLOCATION_NAME).read_bytes()
    template["method"] = {
        "copromem": POLICY_VERSION,
        "retrieval": "unique named-app complete-noun terminal discovery; v6.2.2 semantic safety guards retained",
        "analysis_scope": "Dynamic retrieval-only gate diagnostic; no semantic update from a one-trial task; not comparative efficacy evidence",
    }
    template["method_policy"] = frozen_policy()
    template["method_policy"]["single_trial_dynamic_update"] = (
        "disabled: semantic-spine learning requires at least two same-task trials; pre-state carries forward unchanged"
    )
    # The executor transport is the authority for the OpenRouter route.  Keep
    # the manifest field, identity input, and pre-dispatch route check aligned.
    template["execution"]["provider_only"] = CHAT_PROVIDER
    template["evaluation"].update({"allocation_audit_sha256": hashlib.sha256(allocation).hexdigest(),
                                   "expected_trajectories": TASK_COUNT,
                                   "task_count": TASK_COUNT, "trial_count": 1})
    template["budget"].update({"historical_settled_exposure": 0.0, "hard_cap_usd": HARD_CAP_USD})
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
    write_json(path, template)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["allocate", "prepare", "freeze", "preflight", "run"])
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--source-manifest", type=Path)
    args = parser.parse_args(); run = args.run.resolve()
    if args.command == "allocate":
        if args.source_manifest is None:
            raise SystemExit("--source-manifest is required for allocate")
        allocate(run, args.source_manifest.resolve()); return
    configure(run)
    if args.command == "prepare":
        prepare(run)
    elif args.command == "freeze":
        base.freeze(run)
    elif args.command == "preflight":
        base.load(run)
        route = verify_locked_chat_route_available()
        if route.get("provider") != CHAT_PROVIDER:
            raise RuntimeError("locked route differs from manifest provider")
        write_json(run / "provider-route-preflight.json", route)
        base.st(run, "preflight_passed", provider_route=route)
    else:
        base.run(run)


if __name__ == "__main__":
    main()
