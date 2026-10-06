#!/usr/bin/env python3
"""Twelve-task, one-trial, Dynamic-only CoProMem v6.2.4 gate check.

This is deliberately a new, independently frozen diagnostic.  It cannot edit,
resume, or be aggregated as evidence from a v6.2.2 run.  Its only method
change is the versioned public terminal-discovery rule in v6.2.4; the v6.2.2
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
from copromem.experiments.reme_copromem.public_operation_intent_registry import (
    build as build_intents, verify as verify_intents,
)
from copromem.experiments.reme_copromem.schema_external_admission import verify as verify_admission
from copromem.experiments.reme_copromem.external_validation_admission import admit as admit_external_validation
from copromem.experiments.reme_copromem.task_conditioned_retrieval_v624 import (
    POLICY_VERSION,
    candidate_validation_retrieve,
    derive_task_query,
    frozen_policy,
    retrieve,
    validate_task_query,
)
from copromem.integrations.reme.transport import PROVIDER as CHAT_PROVIDER
from copromem.integrations.reme.transport import verify_locked_chat_route_available
from scripts import run_v61_exploratory_evaluation as base
from scripts import run_v622_semantic_spine_engineering as v622


PROTOCOL = "v6_2_4_dynamic_guidance_check_001"
ARM = "copromem_v6_2_4_dynamic"
ARMS = [ARM]
TRIAL_SEED = 62301
TASK_COUNT = 12
HARD_CAP_USD = 20.0
CALL_LIMITS = {"executor": TASK_COUNT * 30, "reme_lifecycle": 0,
               "reme_embedding": 0, "copromem_decomposition": 0}
ALLOCATION_NAME = "allocation-audit-v624-dynamic.json"
VALIDATION_TASK_ID = "2c544f9_3"
VALIDATION_SCHEMA_ID = "schema_32fa5b751d6342b6"
_PHASE: str | None = None


def _external(path: str) -> Path:
    if os.name == "posix" and len(path) >= 3 and path[1:3] == ":\\":
        return Path("/mnt/" + path[0].lower() + path[2:].replace("\\", "/"))
    return Path(path)


REVIEW = _external(r"E:\Project\AAMAS\COPROMEM-review")
BANK_ROOT = REVIEW / "artifacts/zero-cost-validation/v622-attested-semantic-spine-bank-003-clean-runtime"
COVERAGE = REVIEW / "artifacts/zero-cost-validation/v624-public-task-guidance-coverage-001.json"


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _guidance_positive(task_ids: list[str]) -> list[str]:
    if len(set(task_ids)) != len(task_ids):
        raise RuntimeError("source task inventory contains duplicates")
    if not COVERAGE.is_file():
        raise RuntimeError("v6.2.4 guidance coverage audit is absent")
    coverage = json.loads(COVERAGE.read_text(encoding="utf-8"))
    return sorted({str(item.get("task")) for item in coverage.get("guidance_positive", [])
                   if isinstance(item, Mapping) and str(item.get("task")) in task_ids
                   and str(item.get("task")) != VALIDATION_TASK_ID})


def _selection(task_ids: list[str]) -> list[str]:
    # The held-out admission task is never part of the later diagnostic.
    candidates = [task for task in task_ids if task != VALIDATION_TASK_ID]
    positive = _guidance_positive(candidates)
    # A retrieval diagnostic must include every zero-provider-confirmed
    # positive task available in its frozen source inventory.  Fill only the
    # remaining slots with the original public-ID rule, retaining a 12-task
    # sample without pretending every task should receive this schema.
    remaining = sorted((task for task in candidates if task not in positive), key=lambda task: hashlib.sha256(
        f"{PROTOCOL}:public-task-id:{task}".encode("utf-8")).hexdigest())
    return [*positive, *remaining][:TASK_COUNT]


def _bank_audit() -> dict[str, Any]:
    return {
        "path": str(BANK_ROOT),
        "fixed_bank_file_sha256": _file_sha(BANK_ROOT / "fixed-bank.json"),
        "admission_gate_file_sha256": _file_sha(BANK_ROOT / "semantic-admission-gate.json"),
        "recovery_report_file_sha256": _file_sha(BANK_ROOT / "recovery-report.json"),
        "semantic_state_sha256": json.loads((BANK_ROOT / "semantic-admission-gate.json").read_text())["state_sha256"],
    }


def _write_allocation(run: Path, audit: Mapping[str, Any]) -> None:
    run.mkdir(parents=True, exist_ok=False)
    write_json(run / ALLOCATION_NAME, dict(audit))


def allocate_validation(run: Path, source_manifest: Path) -> None:
    """Freeze the one and only isolated held-out admission trajectory."""
    source = json.loads(source_manifest.read_text(encoding="utf-8"))
    task_ids = list(source.get("evaluation", {}).get("task_ids", ()))
    if VALIDATION_TASK_ID not in task_ids:
        raise RuntimeError("held-out validation task is absent from source inventory")
    audit = {
        "version": "v6.2.4-external-admission-validation-allocation-v1",
        "phase": "external_validation",
        "protocol": PROTOCOL,
        "selection_source": "frozen_source_manifest_exact_held_out_task",
        "payloads_opened": True,
        "source_manifest_path": str(source_manifest.resolve()),
        "source_manifest_sha256": _file_sha(source_manifest),
        "source_task_inventory_sha256": _sha(task_ids),
        "selected_task_ids": [VALIDATION_TASK_ID],
        "split": str(source.get("evaluation", {}).get("split") or "test_normal"),
        "trial_seeds": [TRIAL_SEED], "arms": ARMS,
        "candidate_schema_id": VALIDATION_SCHEMA_ID,
        "copromem_bank": _bank_audit(), "historical_settled_exposure_usd": 0.0,
        "cost_scope": "one isolated held-out external admission validation; excluded from pilot diagnostic",
    }
    _write_allocation(run, audit)


def allocate(run: Path, source_manifest: Path, admission_receipt: Path) -> None:
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
    if not admission_receipt.is_file():
        raise RuntimeError("normal pilot allocation requires an immutable external admission receipt")
    receipt = json.loads(admission_receipt.read_text(encoding="utf-8"))
    state = json.loads((BANK_ROOT / "fixed-bank.json").read_text(encoding="utf-8"))
    verify_admission(receipt, bank_sha256=_sha(state))
    if receipt.get("validation_task_id") != VALIDATION_TASK_ID or receipt.get("schema_ids") != [VALIDATION_SCHEMA_ID]:
        raise RuntimeError("external admission receipt is for a different validation boundary")
    audit = {
        "version": "v6.2.4-dynamic-guidance-coverage-allocation-v3",
        "phase": "pilot",
        "protocol": PROTOCOL,
        "selection_source": "frozen_source_manifest_public_task_ids_only",
        "payloads_opened": False,
        "source_manifest_path": str(source_manifest.resolve()),
        "source_manifest_sha256": _file_sha(source_manifest),
        "source_task_inventory_sha256": _sha(task_ids),
        "selection_rule": "all frozen zero-provider guidance-positive public task IDs, then sha256(protocol:public-task-id:<id>) ascending fill to 12",
        "guidance_coverage_file_sha256": _file_sha(COVERAGE),
        "expected_guidance_positive_task_ids": [task for task in selected if task in set(_guidance_positive(task_ids))],
        "selected_task_ids": selected,
        "split": str(evaluation.get("split") or "test_normal"),
        "trial_seeds": [TRIAL_SEED],
        "arms": ARMS,
        "copromem_bank": _bank_audit(),
        "external_admission_receipt_sha256": _file_sha(admission_receipt),
        "external_admission_receipt_semantic_sha256": receipt["receipt_sha256"],
        "historical_settled_exposure_usd": 0.0,
        "cost_scope": "new v6.2.4 diagnostic calls only; bank construction is referenced, not recharged",
    }
    _write_allocation(run, audit)
    # Bind an immutable copy at a known successor path, never a mutable env path.
    write_json(run / "external-admission-receipt.json", receipt)


def _audit(run: Path) -> Mapping[str, Any]:
    path = run / ALLOCATION_NAME
    if not path.is_file():
        raise RuntimeError("v6.2.4 Dynamic allocation audit is absent")
    audit = json.loads(path.read_text(encoding="utf-8"))
    selected = audit.get("selected_task_ids")
    phase = audit.get("phase")
    expected_count = 1 if phase == "external_validation" else TASK_COUNT
    expected_version = ("v6.2.4-external-admission-validation-allocation-v1" if phase == "external_validation"
                        else "v6.2.4-dynamic-guidance-coverage-allocation-v3")
    if (audit.get("version") != expected_version or audit.get("protocol") != PROTOCOL or
            phase not in {"external_validation", "pilot"} or audit.get("arms") != ARMS or
            audit.get("trial_seeds") != [TRIAL_SEED] or not isinstance(selected, list) or
            len(selected) != expected_count or len(set(selected)) != expected_count or
            any(not isinstance(item, str) for item in selected)):
        raise RuntimeError("v6.2.4 Dynamic allocation audit is invalid")
    if phase == "external_validation":
        if selected != [VALIDATION_TASK_ID] or audit.get("candidate_schema_id") != VALIDATION_SCHEMA_ID:
            raise RuntimeError("external validation allocation may contain only its exact held-out candidate")
    else:
        if audit.get("payloads_opened") is not False or VALIDATION_TASK_ID in selected:
            raise RuntimeError("pilot allocation must exclude the held-out validation task")
        receipt_path = run / "external-admission-receipt.json"
        if not receipt_path.is_file() or _file_sha(receipt_path) != audit.get("external_admission_receipt_sha256"):
            raise RuntimeError("pilot external admission receipt binding is invalid")
        state = json.loads((BANK_ROOT / "fixed-bank.json").read_text(encoding="utf-8"))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        verify_admission(receipt, bank_sha256=_sha(state))
        if receipt.get("receipt_sha256") != audit.get("external_admission_receipt_semantic_sha256"):
            raise RuntimeError("pilot external admission semantic identity differs")
        positives = [task for task in selected if task in set(_guidance_positive(list(selected)))]
        if (not COVERAGE.is_file() or _file_sha(COVERAGE) != audit.get("guidance_coverage_file_sha256")
                or audit.get("expected_guidance_positive_task_ids") != positives
                or not positives):
            raise RuntimeError("pilot guidance coverage binding is invalid")
    bank = audit.get("copromem_bank")
    if not isinstance(bank, Mapping) or _external(str(bank.get("path") or "")) != BANK_ROOT:
        raise RuntimeError("v6.2.4 Dynamic allocation bank locator differs")
    for name, field in (("fixed-bank.json", "fixed_bank_file_sha256"),
                        ("semantic-admission-gate.json", "admission_gate_file_sha256"),
                        ("recovery-report.json", "recovery_report_file_sha256")):
        if not (BANK_ROOT / name).is_file() or _file_sha(BANK_ROOT / name) != bank.get(field):
            raise RuntimeError(f"v6.2.4 Dynamic bank artifact differs: {name}")
    if not math.isfinite(float(audit.get("historical_settled_exposure_usd", -1))) or float(audit["historical_settled_exposure_usd"]) != 0:
        raise RuntimeError("v6.2.4 Dynamic diagnostic may not carry unrelated historical cost")
    return audit


def _retrieval_record(*, state: Mapping[str, Any], query_operations: list[str], registry_sha256: str,
                      task_query: Mapping[str, Any] | None = None,
                      callable_registry: Mapping[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    if callable_registry is None or task_query is None:
        raise ValueError("v6.2.4 retrieval requires frozen registry and public query provenance")
    if registry_sha256 != callable_registry.get("registry_sha256"):
        raise ValueError("v6.2.4 runner registry identity mismatch")
    if list(query_operations) != list(task_query.get("canonical_query_operations", ())):
        raise ValueError("v6.2.4 query operation boundary mismatch")
    candidate = _PHASE == "external_validation"
    if candidate:
        if os.environ.get("COPROMEM_V624_CANDIDATE_VALIDATION") not in {None, "1"}:
            raise RuntimeError("candidate validation phase override is invalid")
        guidance, provenance = candidate_validation_retrieve(
            state, task_query, callable_registry, schema_id=VALIDATION_SCHEMA_ID,
            validation_task_id=VALIDATION_TASK_ID, current_task_id=VALIDATION_TASK_ID,
        )
        return guidance, provenance
    receipt_path = Path(os.environ.get("COPROMEM_V624_ADMISSION_RECEIPT", ""))
    if not receipt_path.is_file():
        # The frozen, local, hash-bound receipt is the normal production path.
        receipt_path = Path(getattr(_retrieval_record, "receipt_path", ""))
    if not receipt_path.is_file():
        raise RuntimeError("v6.2.4 external admission receipt is absent")
    admission = json.loads(receipt_path.read_text(encoding="utf-8"))
    verify_admission(admission, bank_sha256=_sha(dict(state)))
    guidance, provenance = retrieve(state, task_query, callable_registry, admission)
    if not guidance:
        raise RuntimeError("v6.2.4 admitted retrieval produced empty guidance")
    return guidance, provenance


def create_external_admission(*, run: Path) -> Path:
    """Create the immutable receipt only after the isolated validation run passes."""
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("evaluation", {}).get("task_ids") != [VALIDATION_TASK_ID]:
        raise RuntimeError("external validation run has an unexpected task schedule")
    artifact = run / "artifacts" / VALIDATION_TASK_ID / ARM / "trial-1.json"
    journal = run / "journals" / f"evaluation_{ARM}_{VALIDATION_TASK_ID}_trial_1_seed_{TRIAL_SEED}.execution-evidence.jsonl"
    state = json.loads((BANK_ROOT / "fixed-bank.json").read_text(encoding="utf-8"))
    registry = json.loads(base.REG.read_text(encoding="utf-8"))
    receipt = admit_external_validation(bank_sha256=_sha(state), schema_ids=[VALIDATION_SCHEMA_ID],
        validation_task_id=VALIDATION_TASK_ID, artifact_path=artifact, journal_path=journal,
        expected_registry_sha256=str(registry["registry_sha256"]))
    target = run / "external-admission-receipt.json"
    if target.exists() and json.loads(target.read_text(encoding="utf-8")) != receipt:
        raise RuntimeError("external admission receipt conflicts with immutable validation evidence")
    if not target.exists(): write_json(target, receipt)
    return target


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
        raise ValueError("v6.2.4 single-trial gate check requires exactly one scored artifact")
    artifact = artifacts[0]
    scorer_hash = scorer_evidence_sha256(artifact)
    evidence = validate_execution_evidence(
        artifact, run_root=run_root, expected_registry_sha256=str(registry["registry_sha256"])
    )
    pre_hash = _sha(dict(pre_state))
    plan = {"version": "v6.2.4-single-trial-no-learning-v1", "pre_state_sha256": pre_hash,
            "artifact_trajectory_id": str(artifact.get("trajectory_id") or ""),
            "scorer_evidence_sha256": scorer_hash,
            "execution_evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
            "action": "no_semantic_update_single_trial_insufficient"}
    plan["plan_sha256"] = _sha(plan)
    validation = {"version": "v6.2.4-single-trial-no-learning-v1", "passed": True,
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
    global _PHASE
    _PHASE = str(audit["phase"])
    base.SOURCE = REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_shared_acquisition_001"
    base.CONSTRUCTION = REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_1_exploratory_diagnostic_construction_003"
    base.PROTOCOL = PROTOCOL
    base.ARMS = list(ARMS)
    base.FROZEN_TASK_IDS = list(audit["selected_task_ids"])
    base.EVALUATION_SPLIT = str(audit["split"])
    base.EVALUATION_SEEDS = (TRIAL_SEED,)
    base.HARD_CAP_USD = HARD_CAP_USD
    base.CALL_LIMITS = {**CALL_LIMITS, "executor": len(audit["selected_task_ids"]) * 30}
    base.HISTORICAL_EXPOSURE = 0.0
    base.COPRO_FIXED_ARM = "copromem_v6_2_4_fixed_unregistered"
    base.COPRO_DYNAMIC_ARM = ARM
    base.TASK_MAJOR_ARM_FIRST = True
    base.PREEXISTING_RUN_FILES = {ALLOCATION_NAME, "public-operation-intents.json"}
    if _PHASE == "pilot":
        base.PREEXISTING_RUN_FILES.add("external-admission-receipt.json")
    base.COPRO = BANK_ROOT
    v622.V622_BANK_ROOT = BANK_ROOT
    base.identities = v622._bank_identities
    intent_path = run / "public-operation-intents.json"
    if not intent_path.is_file():
        raise RuntimeError("v6.2.4 public operation intent registry is absent")
    intents = json.loads(intent_path.read_text(encoding="utf-8")); verify_intents(intents)
    _retrieval_record.receipt_path = run / "external-admission-receipt.json"
    def derive_with_intents(instruction: str, domain: str, tool_meta: Mapping[str, Any],
                            callable_registry: Mapping[str, Any] | None = None) -> dict[str, Any]:
        # ``base.conditioned_memory`` passes its already frozen registry as a
        # fourth positional argument.  Retain that exact authority rather than
        # silently loading a second registry view.
        registry = callable_registry or json.loads(base.REG.read_text(encoding="utf-8"))
        return derive_task_query(instruction, domain, {**tool_meta, "public_operation_intents": intents}, registry)
    def validate_with_intents(record: Mapping[str, Any], *, instruction: str,
                              public_tool_metadata: Mapping[str, Any], callable_registry: Mapping[str, Any]) -> None:
        validate_task_query(record, instruction=instruction,
                            public_tool_metadata={**public_tool_metadata, "public_operation_intents": intents},
                            callable_registry=callable_registry)
    base.derive_task_query = derive_with_intents
    base.validate_task_query = validate_with_intents
    base.retrieval_record = _retrieval_record
    def reproduce_with_intents(state: Mapping[str, Any], task_query: Mapping[str, Any],
                               callable_registry: Mapping[str, Any], provenance: Mapping[str, Any]) -> str:
        receipt = None
        if provenance.get("retrieval_mode") != "isolated_external_candidate_validation":
            receipt_path = run / "external-admission-receipt.json"
            if not receipt_path.is_file():
                raise ValueError("admitted v6.2.4 restart lacks its frozen receipt")
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        from copromem.experiments.reme_copromem.task_conditioned_retrieval_v624 import reproduce_retrieval
        return reproduce_retrieval(state, task_query, callable_registry, provenance, receipt)
    base.reproduce_retrieval = reproduce_with_intents
    # Do not lower v6.2.2's >=2 same-task semantic-learning threshold merely
    # because this user-requested check has one trial.  The arm exercises the
    # Dynamic retrieval callback and durable task prefix, but commits no bank
    # update until a separately frozen multi-trial evaluation is used.
    base.semantic_task_batch_update = _single_trial_gate_check_update


def prepare(run: Path) -> None:
    run.mkdir(parents=True, exist_ok=True)
    intent_path = run / "public-operation-intents.json"
    if not intent_path.exists():
        write_json(intent_path, build_intents("/home/xiqhq/copromem-appworld/data/api_docs/openapi"))
    configure(run)
    base.prepare(run)
    path = run / "template.json"
    template = json.loads(path.read_text(encoding="utf-8"))
    allocation = (run / ALLOCATION_NAME).read_bytes()
    audit = _audit(run)
    count = len(audit["selected_task_ids"])
    template["method"] = {
        "copromem": POLICY_VERSION,
        "retrieval": "unique named-app complete-noun terminal discovery; v6.2.2 semantic safety guards retained",
        "analysis_scope": ("isolated external admission validation" if _PHASE == "external_validation"
                           else "Dynamic retrieval-only gate diagnostic; no semantic update from a one-trial task; not comparative efficacy evidence"),
    }
    template["method_policy"] = frozen_policy()
    template["method_policy"]["single_trial_dynamic_update"] = (
        "disabled: semantic-spine learning requires at least two same-task trials; pre-state carries forward unchanged"
    )
    # The executor transport is the authority for the OpenRouter route.  Keep
    # the manifest field, identity input, and pre-dispatch route check aligned.
    template["execution"]["provider_only"] = CHAT_PROVIDER
    template["evaluation"].update({"allocation_audit_sha256": hashlib.sha256(allocation).hexdigest(),
                                   "expected_trajectories": count,
                                   "task_count": count, "trial_count": 1,
                                   "phase": _PHASE})
    template["execution"]["call_limits"] = {**CALL_LIMITS, "executor": count * 30}
    template["external_admission"] = ({
        "mode": "isolated_candidate_validation", "validation_task_id": VALIDATION_TASK_ID,
        "candidate_schema_id": VALIDATION_SCHEMA_ID,
    } if _PHASE == "external_validation" else {
        "mode": "admitted_retrieval", "receipt_file_sha256": _file_sha(run / "external-admission-receipt.json"),
        "receipt_sha256": json.loads((run / "external-admission-receipt.json").read_text())["receipt_sha256"],
    })
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
    parser.add_argument("command", choices=["allocate", "allocate-validation", "prepare", "freeze", "preflight", "run", "admit"])
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--admission-receipt", type=Path)
    args = parser.parse_args(); run = args.run.resolve()
    if args.command == "allocate":
        if args.source_manifest is None or args.admission_receipt is None:
            raise SystemExit("--source-manifest and --admission-receipt are required for allocate")
        allocate(run, args.source_manifest.resolve(), args.admission_receipt.resolve()); return
    if args.command == "allocate-validation":
        if args.source_manifest is None:
            raise SystemExit("--source-manifest is required for allocate-validation")
        allocate_validation(run, args.source_manifest.resolve()); return
    if args.command == "admit":
        create_external_admission(run=run); return
    if args.command == "prepare":
        prepare(run)
        return
    configure(run)
    if args.command == "prepare":
        raise AssertionError("prepare returned unexpectedly")
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
