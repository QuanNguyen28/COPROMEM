#!/usr/bin/env python3
"""Isolated external admission for one v6.2.7 schema and public train task.

The runner is deliberately generic: every candidate is supplied in a frozen
allocation audit and is independently validated before any provider call. It
never learns from its one-trial validation evidence.
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
os.environ.setdefault("COPROMEM_EVALUATION_RUNNER", str(Path(__file__).resolve()))

from copromem.experiments.reme_copromem.contrastive_v6_runner import scorer_evidence_sha256
from copromem.experiments.reme_copromem.evidence_contract import validate as validate_execution_evidence
from copromem.experiments.reme_copromem.external_validation_admission import admit as admit_external_validation
from copromem.experiments.reme_copromem.public_operation_intent_registry import build as build_intents, verify as verify_intents
from copromem.experiments.reme_copromem.runner import write_json
from copromem.experiments.reme_copromem.runtime_identity_v3 import IDENTITY_VERSION as RUNTIME_IDENTITY_V3, build_evaluation_identity_v3
from copromem.experiments.reme_copromem.task_conditioned_retrieval_v627 import (
    POLICY_VERSION, candidate_validation_retrieve, derive_task_query, frozen_policy,
    reproduce_retrieval, validate_task_query,
)
from copromem.integrations.reme.transport import PROVIDER as CHAT_PROVIDER, verify_locked_chat_route_available
from scripts import run_v61_exploratory_evaluation as base
from scripts.v626_copromem_only_runtime import install as install_copromem_only_runtime

PROTOCOL = "v6_2_7_multi_schema_external_admission_v1"
ARM = "copromem_v6_2_7_dynamic"
TRIAL_SEED = 62701
ALLOCATION_NAME = "allocation-audit-v627-external-admission.json"
HARD_CAP_USD = 5.0
REVIEW = Path(os.environ.get("COPROMEM_REVIEW_ROOT", "/mnt/e/Project/AAMAS/COPROMEM-review"))
_PHASE: str | None = None
_BANK_ROOT: Path | None = None
_CANDIDATE_TASK_ID: str | None = None
_CANDIDATE_SCHEMA_ID: str | None = None


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _file_sha(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"required immutable file is absent: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def _bank_identities() -> tuple[dict[str, Any], dict[str, Any]]:
    if _BANK_ROOT is None:
        raise RuntimeError("v6.2.7 bank root is not configured")
    report_path = base.CONSTRUCTION / "FINAL_CONSTRUCTION_REPORT.json"
    report = _read(report_path)
    if report.get("shared_bank_sha256") != "6c3bc799ec0beb034fd2b81ee0d5cbf6e89a14f3a5a39ebf70d34853686b00a0":
        raise RuntimeError("shared ReMe construction identity is invalid")
    bank_path, gate_path = _BANK_ROOT / "fixed-bank.json", _BANK_ROOT / "semantic-admission-gate.json"
    bank, gate = _read(bank_path), _read(gate_path)
    if (gate.get("version") != "copromem-v6.2.7-seed-bank-promotion-v1" or gate.get("passed") is not True
            or gate.get("provider_calls") != 0 or gate.get("state_sha256") != _sha(bank)):
        raise RuntimeError("promoted v6.2.7 seed-bank identity is invalid")
    report_path = _BANK_ROOT / "recovery-report.json"
    if gate.get("recovery_report_sha256") != _file_sha(report_path):
        raise RuntimeError("promoted v6.2.7 seed-bank custody is invalid")
    return report, gate


def _bank_audit(bank_root: Path) -> dict[str, Any]:
    bank, gate = _read(bank_root / "fixed-bank.json"), _read(bank_root / "semantic-admission-gate.json")
    if gate.get("state_sha256") != _sha(bank):
        raise RuntimeError("candidate bank state differs from its gate")
    return {"path": str(bank_root.resolve()), "fixed_bank_file_sha256": _file_sha(bank_root / "fixed-bank.json"),
            "admission_gate_file_sha256": _file_sha(bank_root / "semantic-admission-gate.json"),
            "recovery_report_file_sha256": _file_sha(bank_root / "recovery-report.json"),
            "semantic_state_sha256": _sha(bank)}


def _used_seed_task_ids() -> set[str]:
    used: set[str] = set()
    root = REVIEW / "artifacts/research/official_reme_copromem_pilot"
    for run in root.glob("v6_2_7_seed_acquisition_*"):
        for artifact in run.glob("artifacts/*/*/trial-*.json"):
            try:
                task = _read(artifact).get("task_id")
                if isinstance(task, str):
                    used.add(task)
            except (OSError, ValueError, json.JSONDecodeError):
                pass
    return used


def allocate(run: Path, inventory_path: Path, evaluation_allocation: Path, bank_root: Path,
             task_id: str, schema_id: str) -> None:
    """Freeze exactly one independently held-out candidate validation."""
    if run.exists() and any(run.iterdir()):
        raise RuntimeError("admission allocation target must be empty")
    inventory, evaluation = _read(inventory_path), _read(evaluation_allocation)
    rows = [row for row in inventory.get("unseen_train_tasks", []) if isinstance(row, dict)]
    matches = [row for row in rows if row.get("task_id") == task_id]
    if len(matches) != 1:
        raise RuntimeError("candidate task must occur exactly once in the frozen public train inventory")
    excluded = {str(value) for value in evaluation.get("selected_task_ids", []) if isinstance(value, str)} | _used_seed_task_ids()
    if task_id in excluded:
        raise RuntimeError("candidate task was already used by test allocation or seed construction")
    state, registry = _read(bank_root / "fixed-bank.json"), _read(base.REG)
    intents = build_intents("/home/xiqhq/copromem-appworld/data/api_docs/openapi")
    row = matches[0]
    query = derive_task_query(str(row.get("instruction") or ""), "train", {
        "app_descriptions": row.get("app_descriptions", {}), "public_operation_intents": intents,
    }, registry)
    guidance, provenance = candidate_validation_retrieve(state, query, registry, schema_id=schema_id,
        validation_task_id=task_id, current_task_id=task_id)
    if not guidance or provenance.get("guidance_nonempty") is not True:
        raise RuntimeError("candidate schema has no compatible public train retrieval; no admission run was created")
    audit = {
        "version": "v6.2.7-external-admission-allocation-v1", "phase": "external_validation",
        "protocol": PROTOCOL, "split": "train", "payloads_opened": False, "provider_calls": 0,
        "selected_task_ids": [task_id], "trial_seeds": [TRIAL_SEED], "arms": [ARM],
        "candidate_schema_id": schema_id, "candidate_query_sha256": query["query_sha256"],
        "candidate_retrieval_sha256": provenance["retrieval_sha256"],
        "candidate_guidance_sha256": provenance["guidance_sha256"],
        "source_inventory_path": str(inventory_path.resolve()), "source_inventory_sha256": _file_sha(inventory_path),
        "evaluation_exclusion_path": str(evaluation_allocation.resolve()), "evaluation_exclusion_sha256": _file_sha(evaluation_allocation),
        "seed_exclusion_task_ids_sha256": _sha(sorted(_used_seed_task_ids())), "copromem_bank": _bank_audit(bank_root),
        "historical_settled_exposure_usd": 0.0,
        "cost_scope": "isolated external schema-admission validation; no semantic learning",
    }
    run.mkdir(parents=True, exist_ok=False)
    write_json(run / ALLOCATION_NAME, audit)


def _audit(run: Path) -> dict[str, Any]:
    audit = _read(run / ALLOCATION_NAME)
    if (audit.get("version") != "v6.2.7-external-admission-allocation-v1" or audit.get("phase") != "external_validation"
            or audit.get("protocol") != PROTOCOL or audit.get("split") != "train" or audit.get("payloads_opened") is not False
            or audit.get("provider_calls") != 0 or audit.get("arms") != [ARM] or audit.get("trial_seeds") != [TRIAL_SEED]
            or not isinstance(audit.get("candidate_schema_id"), str) or not isinstance(audit.get("selected_task_ids"), list)
            or len(audit["selected_task_ids"]) != 1 or not isinstance(audit["selected_task_ids"][0], str)):
        raise RuntimeError("frozen external-admission allocation is invalid")
    bank = audit.get("copromem_bank")
    if not isinstance(bank, Mapping): raise RuntimeError("external-admission bank audit is absent")
    root = Path(str(bank.get("path") or ""))
    expected = _bank_audit(root)
    if dict(bank) != expected:
        raise RuntimeError("external-admission bank audit differs")
    if not math.isfinite(float(audit.get("historical_settled_exposure_usd", -1))) or float(audit["historical_settled_exposure_usd"]) != 0:
        raise RuntimeError("external admission must not absorb prior cost")
    return audit


def _retrieval_record(*, state: Mapping[str, Any], query_operations: list[str], registry_sha256: str,
                      task_query: Mapping[str, Any] | None = None, callable_registry: Mapping[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    if _CANDIDATE_TASK_ID is None or _CANDIDATE_SCHEMA_ID is None or callable_registry is None or task_query is None:
        raise RuntimeError("external admission candidate configuration is absent")
    if registry_sha256 != callable_registry.get("registry_sha256") or list(query_operations) != list(task_query.get("canonical_query_operations", ())):
        raise RuntimeError("external admission query authority differs")
    return candidate_validation_retrieve(state, task_query, callable_registry, schema_id=_CANDIDATE_SCHEMA_ID,
        validation_task_id=_CANDIDATE_TASK_ID, current_task_id=_CANDIDATE_TASK_ID)


def _single_trial_no_learning(*, artifacts: list[Mapping[str, Any]], registry: Mapping[str, Any],
                              pre_state: Mapping[str, Any], evidence_paths: list[str | Path], run_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if len(artifacts) != 1 or len(evidence_paths) != 1: raise ValueError("external admission requires one scored artifact")
    artifact = artifacts[0]
    evidence = validate_execution_evidence(artifact, run_root=run_root, expected_registry_sha256=str(registry["registry_sha256"]))
    pre = _sha(dict(pre_state))
    plan = {"version": "v6.2.7-external-admission-no-learning-v1", "pre_state_sha256": pre,
            "artifact_trajectory_id": str(artifact.get("trajectory_id") or ""), "scorer_evidence_sha256": scorer_evidence_sha256(artifact),
            "execution_evidence_sha256": _file_sha(Path(evidence)), "action": "no_semantic_update_single_trial_insufficient"}
    plan["plan_sha256"] = _sha(plan)
    marker = {"state": "rejected", "reason": "semantic_spine_learning_requires_at_least_two_same_task_trials", "post_state_sha256": pre}
    return dict(pre_state), marker, {"state_format": pre_state.get("state_format"), "semantic_policy_version": POLICY_VERSION,
        "pre_state_sha256": pre, "semantic_graph_audits": [], "plan": plan,
        "validation": {"passed": True, "reason": marker["reason"], "pre_state_sha256": pre}, "marker": marker, "post_state_sha256": pre,
        "diagnostic_no_learning": True}


def configure(run: Path) -> None:
    global _PHASE, _BANK_ROOT, _CANDIDATE_TASK_ID, _CANDIDATE_SCHEMA_ID
    audit = _audit(run); _PHASE = "external_validation"; _CANDIDATE_TASK_ID = audit["selected_task_ids"][0]; _CANDIDATE_SCHEMA_ID = audit["candidate_schema_id"]
    _BANK_ROOT = Path(str(audit["copromem_bank"]["path"]));
    base.SOURCE = REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_shared_acquisition_001"
    base.CONSTRUCTION = REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_1_exploratory_diagnostic_construction_003"
    base.PROTOCOL = PROTOCOL; base.ARMS = [ARM]; install_copromem_only_runtime(base, base.ARMS)
    base.FROZEN_TASK_IDS = [_CANDIDATE_TASK_ID]; base.EVALUATION_SPLIT = "train"; base.EVALUATION_SEEDS = (TRIAL_SEED,)
    base.HARD_CAP_USD = HARD_CAP_USD; base.CALL_LIMITS = {"executor": 30, "reme_lifecycle": 0, "reme_embedding": 0, "copromem_decomposition": 0}
    base.HISTORICAL_EXPOSURE = 0.0; base.COPRO_FIXED_ARM = "copromem_v6_2_7_fixed_unregistered"; base.COPRO_DYNAMIC_ARM = ARM; base.TASK_MAJOR_ARM_FIRST = True
    base.PREEXISTING_RUN_FILES = {ALLOCATION_NAME, "public-operation-intents.json"}; base.COPRO = _BANK_ROOT; base.identities = _bank_identities
    intents = _read(run / "public-operation-intents.json"); verify_intents(intents)
    def derive(instruction: str, domain: str, tool_meta: Mapping[str, Any], callable_registry: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return derive_task_query(instruction, domain, {**tool_meta, "public_operation_intents": intents}, callable_registry or _read(base.REG))
    def validate(record: Mapping[str, Any], *, instruction: str, public_tool_metadata: Mapping[str, Any], callable_registry: Mapping[str, Any]) -> None:
        validate_task_query(record, instruction=instruction, public_tool_metadata={**public_tool_metadata, "public_operation_intents": intents}, callable_registry=callable_registry)
    base.derive_task_query, base.validate_task_query, base.retrieval_record = derive, validate, _retrieval_record
    base.reproduce_retrieval = lambda state, task_query, callable_registry, provenance: reproduce_retrieval(state, task_query, callable_registry, provenance)
    base.semantic_task_batch_update = _single_trial_no_learning


def prepare(run: Path) -> None:
    run.mkdir(parents=True, exist_ok=True)
    intent = run / "public-operation-intents.json"
    if not intent.exists(): write_json(intent, build_intents("/home/xiqhq/copromem-appworld/data/api_docs/openapi"))
    configure(run); base.prepare(run)
    path = run / "template.json"; template = _read(path); audit = _audit(run)
    template["method"] = {"copromem": POLICY_VERSION, "retrieval": "one isolated externally attested terminal slice", "analysis_scope": "external admission validation; no efficacy claim"}
    template["method_policy"] = frozen_policy(); template["method_policy"]["single_trial_dynamic_update"] = "disabled"
    template["execution"]["provider_only"] = CHAT_PROVIDER
    template["evaluation"].update({"allocation_audit_sha256": _file_sha(run / ALLOCATION_NAME), "expected_trajectories": 1, "task_count": 1, "trial_count": 1, "phase": "external_validation"})
    template["external_admission"] = {"mode": "isolated_candidate_validation", "validation_task_id": audit["selected_task_ids"][0], "candidate_schema_id": audit["candidate_schema_id"]}
    template["budget"].update({"historical_settled_exposure": 0.0, "hard_cap_usd": HARD_CAP_USD}); template["runtime_identity_version"] = RUNTIME_IDENTITY_V3
    runtime, inputs = build_evaluation_identity_v3(root=ROOT, manifest=template)
    write_json(run / "runtime-identity.json", runtime); write_json(run / "runtime-identity.binding.json", {"runtime_identity_sha256": runtime["runtime_identity_sha256"], "runtime_identity_record_sha256": base.file_sha(run / "runtime-identity.json")})
    template["runtime_identity_inputs"] = inputs; template["runtime_identity_sha256"] = runtime["runtime_identity_sha256"]; template["runtime_identity_file_sha256"] = base.file_sha(run / "runtime-identity.json"); write_json(path, template)


def admit(run: Path) -> Path:
    audit = _audit(run); task, schema = audit["selected_task_ids"][0], audit["candidate_schema_id"]
    artifact = run / "artifacts" / task / ARM / "trial-1.json"
    journal = run / "journals" / f"evaluation_{ARM}_{task}_trial_1_seed_{TRIAL_SEED}.execution-evidence.jsonl"
    retrieval = run / "retrievals" / task / f"{ARM}-1.json"
    bank = _read(Path(str(audit["copromem_bank"]["path"])) / "fixed-bank.json")
    receipt = admit_external_validation(bank_sha256=_sha(bank), schema_ids=[schema], validation_task_id=task, artifact_path=artifact, journal_path=journal,
        expected_registry_sha256=str(_read(base.REG)["registry_sha256"]), retrieval_provenance_path=retrieval, retrieval_policy_sha256=frozen_policy()["policy_sha256"])
    target = run / "external-admission-receipt.json"
    if target.exists() and _read(target) != receipt: raise RuntimeError("external admission receipt conflicts with evidence")
    if not target.exists(): write_json(target, receipt)
    return target


def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("command", choices=["allocate", "prepare", "freeze", "preflight", "run", "admit"]); p.add_argument("--run", type=Path, required=True)
    p.add_argument("--inventory", type=Path); p.add_argument("--evaluation-allocation", type=Path); p.add_argument("--seed-bank", type=Path); p.add_argument("--task-id"); p.add_argument("--schema-id")
    a = p.parse_args(); run = a.run.resolve()
    if a.command == "allocate":
        if not all((a.inventory, a.evaluation_allocation, a.seed_bank, a.task_id, a.schema_id)): raise SystemExit("allocate requires --inventory --evaluation-allocation --seed-bank --task-id --schema-id")
        allocate(run, a.inventory.resolve(), a.evaluation_allocation.resolve(), a.seed_bank.resolve(), a.task_id, a.schema_id); return
    if a.command == "admit": admit(run); return
    if a.command == "prepare": prepare(run); return
    configure(run)
    if a.command == "freeze": base.freeze(run)
    elif a.command == "preflight":
        base.load(run); route = verify_locked_chat_route_available()
        if route.get("provider") != CHAT_PROVIDER: raise RuntimeError("locked provider route differs")
        write_json(run / "provider-route-preflight.json", route); base.st(run, "preflight_passed", provider_route=route)
    else: base.run(run)

if __name__ == "__main__": main()
