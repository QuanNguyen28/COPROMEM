#!/usr/bin/env python3
"""One-hundred-task, three-trial Dynamic CoProMem v6.2.5 engineering pilot.

This is a separate, independently frozen overlay.  It reuses only the exact
public task/trial grid of the four-arm evaluation; it never edits, resumes, or
imports that run's artifacts, bank, ledger, or costs.  Its only method change
is the versioned public terminal-discovery rule in v6.2.5; the v6.2.2 semantic
projection, prerequisite, tie, occurrence, executor, scorer, and Dynamic
checkpoint contracts remain in force.
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
from copromem.experiments.reme_copromem.task_conditioned_retrieval_v625 import (
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


PROTOCOL = "v6_2_5_safe_terminal_slice_100x3_engineering_pilot_001"
ARM = "copromem_v6_2_5_dynamic"
ARMS = [ARM]
VALIDATION_TRIAL_SEED = 62301
TRIAL_SEEDS = (11001, 11002, 11003)
TASK_COUNT = 100
# Preflight derives and enforces the conservative all-in bound before dispatch.
# This stays far below the historical four-arm cap while covering 300 isolated
# Dynamic trajectories at the existing executor/action ceilings.
HARD_CAP_USD = 140.0
CALL_LIMITS = {"executor": TASK_COUNT * 30, "reme_lifecycle": 0,
               "reme_embedding": 0, "copromem_decomposition": 0}
ALLOCATION_NAME = "allocation-audit-v625-100x3-dynamic.json"
VALIDATION_TASK_ID = "2c544f9_3"
VALIDATION_SCHEMA_ID = "schema_32fa5b751d6342b6"
_PHASE: str | None = None


def _external(path: str) -> Path:
    if os.name == "posix" and len(path) >= 3 and path[1:3] == ":\\":
        return Path("/mnt/" + path[0].lower() + path[2:].replace("\\", "/"))
    return Path(path)


REVIEW = _external(r"E:\Project\AAMAS\COPROMEM-review")
BANK_ROOT = REVIEW / "artifacts/zero-cost-validation/v622-attested-semantic-spine-bank-003-clean-runtime"
COVERAGE = REVIEW / "artifacts/zero-cost-validation/v625-safe-terminal-slice-coverage-001.json"


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _guidance_positive(task_ids: list[str]) -> list[str]:
    if len(set(task_ids)) != len(task_ids):
        raise RuntimeError("source task inventory contains duplicates")
    if not COVERAGE.is_file():
        raise RuntimeError("v6.2.5 guidance coverage audit is absent")
    coverage = json.loads(COVERAGE.read_text(encoding="utf-8"))
    positives = coverage.get("guidance_positive_task_ids")
    if not isinstance(positives, list):
        raise RuntimeError("v6.2.5 coverage audit has no guidance-positive task inventory")
    return sorted({str(task) for task in positives
                   if isinstance(task, str) and task in task_ids and task != VALIDATION_TASK_ID})


def _selection(task_ids: list[str]) -> list[str]:
    """Accept only the exact 100-task grid used by the four-arm evaluation."""
    if len(task_ids) != TASK_COUNT or len(set(task_ids)) != TASK_COUNT:
        raise RuntimeError("four-arm allocation must contain exactly 100 distinct task IDs")
    return list(task_ids)


def _appworld_root() -> Path:
    value = os.environ.get("COPROMEM_APPWORLD_ROOT") or os.environ.get("APPWORLD_ROOT")
    if not value:
        raise RuntimeError("COPROMEM_APPWORLD_ROOT or APPWORLD_ROOT is required")
    root = _external(value).resolve()
    if not root.is_dir():
        raise RuntimeError("configured AppWorld root does not exist")
    return root


def _openapi_root() -> Path:
    root = _appworld_root() / "data" / "api_docs" / "openapi"
    if not root.is_dir() or not any(root.glob("*.json")):
        raise RuntimeError("configured AppWorld OpenAPI directory is absent or empty")
    return root


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


def allocate(run: Path, source_manifest: Path, four_arm_allocation: Path, admission_receipt: Path) -> None:
    """Freeze an exact task/trial overlay on the independently frozen four-arm grid."""
    if run.exists() and any(run.iterdir()):
        raise RuntimeError("allocation target must be empty")
    source = json.loads(source_manifest.read_text(encoding="utf-8"))
    task_ids = list(source.get("evaluation", {}).get("task_ids", ()))
    if not all(isinstance(item, str) for item in task_ids):
        raise RuntimeError("source manifest task inventory is malformed")
    four = json.loads(four_arm_allocation.read_text(encoding="utf-8"))
    selected = list(four.get("selected_task_ids", ()))
    if (four.get("version") != "v6.2.2-real-pilot-public-allocation-v1"
            or _sha(selected) != four.get("selected_task_ids_sha256")
            or selected != task_ids or selected != _selection(selected)):
        raise RuntimeError("four-arm allocation differs from the frozen source task grid")
    if not admission_receipt.is_file():
        raise RuntimeError("100x3 overlay requires an immutable external admission receipt")
    receipt = json.loads(admission_receipt.read_text(encoding="utf-8"))
    state = json.loads((BANK_ROOT / "fixed-bank.json").read_text(encoding="utf-8"))
    verify_admission(receipt, bank_sha256=_sha(state))
    if receipt.get("retrieval_policy_sha256") != frozen_policy()["policy_sha256"]:
        raise RuntimeError("external admission receipt was validated under a different retrieval policy")
    if not COVERAGE.is_file():
        raise RuntimeError("v6.2.5 coverage audit is absent")
    coverage = json.loads(COVERAGE.read_text(encoding="utf-8"))
    if coverage.get("source_manifest_sha256") != _file_sha(source_manifest):
        raise RuntimeError("coverage audit is for a different source manifest")
    positive = [task for task in selected if task in set(_guidance_positive(selected))]
    if not positive:
        raise RuntimeError("exact four-arm grid has no v6.2.5 guidance-positive task")
    audit = {
        "version": "v6.2.5-four-arm-overlay-allocation-v1",
        "phase": "four_arm_overlay",
        "protocol": PROTOCOL,
        "selection_source": "exact_frozen_four_arm_allocation",
        "payloads_opened": False,
        "source_manifest_path": str(source_manifest.resolve()),
        "source_manifest_sha256": _file_sha(source_manifest),
        "source_task_inventory_sha256": _sha(task_ids),
        "four_arm_allocation_path": str(four_arm_allocation.resolve()),
        "four_arm_allocation_sha256": _file_sha(four_arm_allocation),
        "four_arm_selected_task_ids_sha256": four["selected_task_ids_sha256"],
        "selected_task_ids": selected,
        "selected_task_ids_sha256": _sha(selected),
        "split": str(source.get("evaluation", {}).get("split") or "test_normal"),
        "trial_seeds": list(TRIAL_SEEDS),
        "arms": ARMS,
        "guidance_coverage_file_sha256": _file_sha(COVERAGE),
        "expected_guidance_positive_task_ids": positive,
        "copromem_bank": _bank_audit(),
        "external_admission_receipt_sha256": _file_sha(admission_receipt),
        "external_admission_receipt_semantic_sha256": receipt["receipt_sha256"],
        "external_admission_validation_task_id": receipt.get("validation_task_id"),
        "external_admission_validation_task_is_in_evaluation_grid": receipt.get("validation_task_id") in selected,
        "historical_settled_exposure_usd": 0.0,
        "cost_scope": "new CoProMem v6.2.5 Dynamic overlay calls only; four-arm historical cost remains separate",
    }
    _write_allocation(run, audit)
    (run / "external-admission-receipt.json").write_bytes(admission_receipt.read_bytes())


def _audit(run: Path) -> Mapping[str, Any]:
    path = run / ALLOCATION_NAME
    if not path.is_file():
        raise RuntimeError("v6.2.5 100x3 overlay allocation is absent")
    audit = json.loads(path.read_text(encoding="utf-8"))
    selected = audit.get("selected_task_ids")
    if (audit.get("version") != "v6.2.5-four-arm-overlay-allocation-v1"
            or audit.get("phase") != "four_arm_overlay" or audit.get("protocol") != PROTOCOL
            or audit.get("arms") != ARMS or audit.get("trial_seeds") != list(TRIAL_SEEDS)
            or not isinstance(selected, list) or selected != _selection(selected)
            or audit.get("selected_task_ids_sha256") != _sha(selected)):
        raise RuntimeError("v6.2.5 100x3 overlay allocation is invalid")
    source_path = Path(str(audit.get("source_manifest_path") or ""))
    four_path = Path(str(audit.get("four_arm_allocation_path") or ""))
    if (not source_path.is_file() or _file_sha(source_path) != audit.get("source_manifest_sha256")
            or not four_path.is_file() or _file_sha(four_path) != audit.get("four_arm_allocation_sha256")):
        raise RuntimeError("100x3 overlay source identity differs")
    source = json.loads(source_path.read_text(encoding="utf-8"))
    four = json.loads(four_path.read_text(encoding="utf-8"))
    source_ids = list(source.get("evaluation", {}).get("task_ids", ()))
    if (source_ids != selected or _sha(source_ids) != audit.get("source_task_inventory_sha256")
            or four.get("selected_task_ids") != selected
            or four.get("selected_task_ids_sha256") != audit.get("four_arm_selected_task_ids_sha256")):
        raise RuntimeError("100x3 overlay task grid differs from four-arm allocation")
    receipt_path = run / "external-admission-receipt.json"
    if not receipt_path.is_file() or _file_sha(receipt_path) != audit.get("external_admission_receipt_sha256"):
        raise RuntimeError("100x3 overlay admission receipt binding is invalid")
    state = json.loads((BANK_ROOT / "fixed-bank.json").read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    verify_admission(receipt, bank_sha256=_sha(state))
    if (receipt.get("receipt_sha256") != audit.get("external_admission_receipt_semantic_sha256")
            or receipt.get("retrieval_policy_sha256") != frozen_policy()["policy_sha256"]):
        raise RuntimeError("100x3 overlay admission receipt identity differs")
    if not COVERAGE.is_file() or _file_sha(COVERAGE) != audit.get("guidance_coverage_file_sha256"):
        raise RuntimeError("100x3 overlay coverage audit differs")
    positives = [task for task in selected if task in set(_guidance_positive(selected))]
    if positives != audit.get("expected_guidance_positive_task_ids") or not positives:
        raise RuntimeError("100x3 overlay guidance-positive inventory differs")
    bank = audit.get("copromem_bank")
    if not isinstance(bank, Mapping) or _external(str(bank.get("path") or "")) != BANK_ROOT:
        raise RuntimeError("100x3 overlay bank locator differs")
    for name, field in (("fixed-bank.json", "fixed_bank_file_sha256"),
                        ("semantic-admission-gate.json", "admission_gate_file_sha256"),
                        ("recovery-report.json", "recovery_report_file_sha256")):
        if not (BANK_ROOT / name).is_file() or _file_sha(BANK_ROOT / name) != bank.get(field):
            raise RuntimeError(f"100x3 overlay bank artifact differs: {name}")
    if not math.isfinite(float(audit.get("historical_settled_exposure_usd", -1))) or float(audit["historical_settled_exposure_usd"]) != 0:
        raise RuntimeError("100x3 overlay may not carry four-arm historical cost")
    return audit


def _retrieval_record(*, state: Mapping[str, Any], query_operations: list[str], registry_sha256: str,
                      task_query: Mapping[str, Any] | None = None,
                      callable_registry: Mapping[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    if callable_registry is None or task_query is None:
        raise ValueError("v6.2.5 retrieval requires frozen registry and public query provenance")
    if registry_sha256 != callable_registry.get("registry_sha256"):
        raise ValueError("v6.2.5 runner registry identity mismatch")
    if list(query_operations) != list(task_query.get("canonical_query_operations", ())):
        raise ValueError("v6.2.5 query operation boundary mismatch")
    candidate = _PHASE == "external_validation"
    if candidate:
        if os.environ.get("COPROMEM_V625_CANDIDATE_VALIDATION") not in {None, "1"}:
            raise RuntimeError("candidate validation phase override is invalid")
        guidance, provenance = candidate_validation_retrieve(
            state, task_query, callable_registry, schema_id=VALIDATION_SCHEMA_ID,
            validation_task_id=VALIDATION_TASK_ID, current_task_id=VALIDATION_TASK_ID,
        )
        return guidance, provenance
    receipt_path = Path(os.environ.get("COPROMEM_V625_ADMISSION_RECEIPT", ""))
    if not receipt_path.is_file():
        # The frozen, local, hash-bound receipt is the normal production path.
        receipt_path = Path(getattr(_retrieval_record, "receipt_path", ""))
    if not receipt_path.is_file():
        raise RuntimeError("v6.2.5 external admission receipt is absent")
    admission = json.loads(receipt_path.read_text(encoding="utf-8"))
    admission_bank_sha256 = str(admission.get("bank_sha256") or "")
    verify_admission(admission, bank_sha256=admission_bank_sha256)
    guidance, provenance = retrieve(state, task_query, callable_registry, admission, admission_bank_sha256=admission_bank_sha256)
    # An admitted schema must never be forced into an unrelated task.  Empty
    # retrieval is the fail-closed result for nonmatching task queries; the
    # frozen coverage-positive task is separately asserted at preflight and
    # after execution.  Treating all empty retrievals as a runner failure
    # prevented the remaining diagnostic schedule from running at all.
    return guidance, provenance


def create_external_admission(*, run: Path) -> Path:
    """Create the immutable receipt only after the isolated validation run passes."""
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("evaluation", {}).get("task_ids") != [VALIDATION_TASK_ID]:
        raise RuntimeError("external validation run has an unexpected task schedule")
    artifact = run / "artifacts" / VALIDATION_TASK_ID / ARM / "trial-1.json"
    journal = run / "journals" / f"evaluation_{ARM}_{VALIDATION_TASK_ID}_trial_1_seed_{VALIDATION_TRIAL_SEED}.execution-evidence.jsonl"
    state = json.loads((BANK_ROOT / "fixed-bank.json").read_text(encoding="utf-8"))
    registry = json.loads(base.REG.read_text(encoding="utf-8"))
    retrieval = run / "retrievals" / VALIDATION_TASK_ID / f"{ARM}-1.json"
    receipt = admit_external_validation(bank_sha256=_sha(state), schema_ids=[VALIDATION_SCHEMA_ID],
        validation_task_id=VALIDATION_TASK_ID, artifact_path=artifact, journal_path=journal,
        expected_registry_sha256=str(registry["registry_sha256"]),
        retrieval_provenance_path=retrieval,
        retrieval_policy_sha256=frozen_policy()["policy_sha256"])
    target = run / "external-admission-receipt.json"
    if target.exists() and json.loads(target.read_text(encoding="utf-8")) != receipt:
        raise RuntimeError("external admission receipt conflicts with immutable validation evidence")
    if not target.exists(): write_json(target, receipt)
    return target


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
    base.EVALUATION_SEEDS = tuple(TRIAL_SEEDS)
    base.HARD_CAP_USD = HARD_CAP_USD
    base.CALL_LIMITS = {**CALL_LIMITS,
                        "executor": len(audit["selected_task_ids"]) * len(TRIAL_SEEDS) * 30}
    base.HISTORICAL_EXPOSURE = 0.0
    base.COPRO_FIXED_ARM = "copromem_v6_2_5_fixed_unregistered"
    base.COPRO_DYNAMIC_ARM = ARM
    base.TASK_MAJOR_ARM_FIRST = True
    base.PREEXISTING_RUN_FILES = {
        ALLOCATION_NAME,
        "public-operation-intents.json",
        "external-admission-receipt.json",
    }
    base.COPRO = BANK_ROOT
    v622.V622_BANK_ROOT = BANK_ROOT
    base.identities = v622._bank_identities
    intent_path = run / "public-operation-intents.json"
    if not intent_path.is_file():
        raise RuntimeError("v6.2.5 public operation intent registry is absent")
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
        if provenance.get("retrieval_mode") != "isolated_safe_terminal_slice_candidate_validation":
            receipt_path = run / "external-admission-receipt.json"
            if not receipt_path.is_file():
                raise ValueError("admitted v6.2.5 restart lacks its frozen receipt")
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        from copromem.experiments.reme_copromem.task_conditioned_retrieval_v625 import reproduce_retrieval
        return reproduce_retrieval(state, task_query, callable_registry, provenance, receipt, admission_bank_sha256=(str(receipt.get("bank_sha256")) if receipt else None))
    base.reproduce_retrieval = reproduce_with_intents
    # Three trials per task retain v6.2.2's native Dynamic update threshold.
    # This is the regular durable checkpoint path, never the one-trial no-op
    # used by the completed guidance diagnostic.
    base.semantic_task_batch_update = semantic_spine_task_batch_update


def prepare(run: Path) -> None:
    run.mkdir(parents=True, exist_ok=True)
    intent_path = run / "public-operation-intents.json"
    if not intent_path.exists():
        write_json(intent_path, build_intents(_openapi_root()))
    configure(run)
    base.prepare(run)
    path = run / "template.json"
    template = json.loads(path.read_text(encoding="utf-8"))
    allocation = (run / ALLOCATION_NAME).read_bytes()
    audit = _audit(run)
    count = len(audit["selected_task_ids"])
    template["method"] = {
        "copromem": POLICY_VERSION,
        "retrieval": "admitted named-app action-and-object safe terminal slice; v6.2.2 semantic safety guards retained",
        "analysis_scope": "CoProMem v6.2.5 Dynamic overlay on the exact frozen four-arm task/trial grid; costs and evidence remain separate",
    }
    template["method_policy"] = frozen_policy()
    # The executor transport is the authority for the OpenRouter route.  Keep
    # the manifest field, identity input, and pre-dispatch route check aligned.
    template["execution"]["provider_only"] = CHAT_PROVIDER
    template["evaluation"].update({"allocation_audit_sha256": hashlib.sha256(allocation).hexdigest(),
                                   "expected_trajectories": count * len(TRIAL_SEEDS),
                                   "task_count": count, "trial_count": len(TRIAL_SEEDS),
                                   "phase": _PHASE, "overlay_four_arm_allocation_sha256": audit["four_arm_allocation_sha256"]})
    template["execution"]["call_limits"] = {**CALL_LIMITS, "executor": count * len(TRIAL_SEEDS) * 30}
    template["external_admission"] = {
        "mode": "admitted_retrieval", "receipt_file_sha256": _file_sha(run / "external-admission-receipt.json"),
        "receipt_sha256": json.loads((run / "external-admission-receipt.json").read_text())["receipt_sha256"],
    }
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
    parser.add_argument("--admission-receipt", type=Path)
    parser.add_argument("--four-arm-allocation", type=Path)
    args = parser.parse_args(); run = args.run.resolve()
    if args.command == "allocate":
        if args.source_manifest is None or args.admission_receipt is None or args.four_arm_allocation is None:
            raise SystemExit("--source-manifest, --four-arm-allocation and --admission-receipt are required for allocate")
        allocate(run, args.source_manifest.resolve(), args.four_arm_allocation.resolve(), args.admission_receipt.resolve()); return
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
