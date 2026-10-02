#!/usr/bin/env python3
"""Preregistered 100-task v6.2.2 parallel real-pilot runner.

This is deliberately a new entry point: the earlier three-task engineering
runner remains immutable.  It shares the maintained executor, scorer, ReMe
checkpoints, v6.2.2 retrieval binding, and frozen ReasoningBank bank.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from scripts import run_v61_exploratory_evaluation as base
from scripts import run_v622_parallel_baseline_pilot as parallel
from scripts import run_v622_semantic_spine_engineering as v622
from copromem.experiments.reme_copromem.runner import write_json
from copromem.experiments.reme_copromem.runtime_identity_v3 import build_evaluation_identity_v3
from copromem.experiments.reme_copromem.task_conditioned_retrieval_v622 import (
    POLICY_VERSION, derive_task_query, frozen_policy, reproduce_retrieval, retrieve, validate_task_query,
)
from copromem.integrations.reme.transport import PROVIDER as CHAT_PROVIDER, verify_locked_chat_route_available


PROTOCOL = "v6.2.2-real-pilot-100-v1"
ALLOCATION_NAME = "allocation-audit-real-100.json"
REASONINGBANK_ARM = "reasoningbank"
ARMS = ["no_memory", "official_upstream_reme_fixed", "official_upstream_reme_dynamic", REASONINGBANK_ARM,
        "copromem_v6_2_2_fixed", "copromem_v6_2_2_dynamic"]
SEEDS = [11001, 11002, 11003]
TASK_COUNT = 100
# The bound is the current 36-trajectory protocol scaled to 1,800 trajectories
# and is intentionally not based on observed cheap pilot calls.
CALL_LIMITS = {"executor": 54_000, "reme_lifecycle": 6_400, "reme_embedding": 25_600,
               "copromem_decomposition": 0}
HARD_CAP_USD = 1_500.0


def _load_allocation(run: Path) -> Mapping[str, Any]:
    path = run / ALLOCATION_NAME
    try: value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise RuntimeError("real-pilot allocation is unreadable") from exc
    selected = value.get("selected_task_ids")
    if (not isinstance(selected, list) or len(selected) != TASK_COUNT or len(set(selected)) != TASK_COUNT
            or value.get("payloads_opened") is not False
            or value.get("selection_source") != "public_pre_execution_metadata_only"
            or value.get("sufficient") is not True):
        raise RuntimeError("real-pilot allocation fails the public 100-task admission rule")
    return value


def _configure(run: Path) -> Mapping[str, Any]:
    allocation = _load_allocation(run)
    registry = json.loads((v622.ROOT / "research/reme_copromem_fixed_dynamic_review/appworld_public_tool_schema_registry_v5_3.json").read_text(encoding="utf-8"))
    if allocation.get("registry_sha256") != registry.get("registry_sha256"):
        raise RuntimeError("real-pilot allocation registry identity differs from the frozen callable registry")
    bank_record = allocation.get("copromem_bank")
    if not isinstance(bank_record, Mapping): raise RuntimeError("real-pilot allocation lacks a CoProMem bank binding")
    bank_root = parallel._external(str(bank_record.get("path") or ""))
    if not bank_root.is_absolute(): raise RuntimeError("real-pilot CoProMem bank path is not absolute")
    for name, field in (("fixed-bank.json", "fixed_bank_file_sha256"),
                        ("semantic-admission-gate.json", "admission_gate_file_sha256"),
                        ("recovery-report.json", "recovery_report_file_sha256")):
        path = bank_root / name
        if not path.is_file() or base.file_sha(path) != bank_record.get(field):
            raise RuntimeError(f"real-pilot CoProMem bank binding fails: {name}")
    historical = allocation.get("historical_settled_exposure_usd")
    if isinstance(historical, bool) or not isinstance(historical, (int, float)) or historical < 0:
        raise RuntimeError("real-pilot historical settled exposure is invalid")
    # Base orchestration owns all execution/checkpoint semantics.  These
    # assignments are scoped to this versioned entry point only.
    base.SOURCE = parallel.REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_shared_acquisition_001"
    base.CONSTRUCTION = parallel.REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_1_exploratory_diagnostic_construction_003"
    base.PROTOCOL = PROTOCOL; base.ARMS = list(ARMS); base.FROZEN_TASK_IDS = list(allocation["selected_task_ids"])
    base.EVALUATION_SEEDS = list(SEEDS); base.EVALUATION_SPLIT = "test_normal"; base.HARD_CAP_USD = HARD_CAP_USD
    base.CALL_LIMITS = dict(CALL_LIMITS); base.HISTORICAL_EXPOSURE = float(historical)
    base.COPRO_FIXED_ARM = "copromem_v6_2_2_fixed"; base.COPRO_DYNAMIC_ARM = "copromem_v6_2_2_dynamic"
    base.TASK_MAJOR_ARM_FIRST = True; base.PREEXISTING_RUN_FILES = {ALLOCATION_NAME, "custody-audit.json", "engineering-protocol.json"}
    base.COPRO = bank_root
    v622.V622_BANK_ROOT = bank_root
    if not hasattr(base, "identities_original"): base.identities_original = base.identities
    base.identities = v622._bank_identities
    base.derive_task_query = derive_task_query; base.validate_task_query = validate_task_query
    def retrieval_record(*, state: Mapping[str, Any], query_operations: list[str], registry_sha256: str,
                         task_query: Mapping[str, Any] | None = None,
                         callable_registry: Mapping[str, Any] | None = None):
        if task_query is None or callable_registry is None or registry_sha256 != callable_registry.get("registry_sha256"):
            raise ValueError("real-pilot v6.2.2 retrieval boundary is invalid")
        if list(query_operations) != list(task_query.get("canonical_query_operations", ())):
            raise ValueError("real-pilot v6.2.2 query operation boundary differs")
        guidance, provenance = retrieve(state, task_query, callable_registry)
        if guidance != reproduce_retrieval(state, task_query, callable_registry, provenance):
            raise ValueError("real-pilot v6.2.2 retrieval cannot reproduce offline")
        return guidance, provenance
    base.retrieval_record = retrieval_record; base.reproduce_retrieval = reproduce_retrieval
    base.semantic_task_batch_update = v622.semantic_spine_task_batch_update
    # Reuse only the frozen-bank ReasoningBank adapter; update its externally
    # visible ID before it is allowed to construct any provenance or ledger row.
    parallel.REASONINGBANK_ARM = REASONINGBANK_ARM; parallel.ALLOCATION_NAME = ALLOCATION_NAME
    parallel._ACTIVE_CONTEXT = None
    base.EXTRA_RUNTIME_FACTORY = parallel._capturing_factory
    base.EXTRA_ARM_KWARGS = parallel._arm_kwargs
    base.EXTRA_EXISTING_VALIDATOR = parallel._existing_validator
    base.EXTRA_TERMINAL_CHECK = parallel._terminal_check
    return allocation


def prepare(run: Path) -> None:
    allocation = _configure(run); base.prepare(run)
    path = run / "template.json"; template = json.loads(path.read_text(encoding="utf-8"))
    rb = parallel._rb_manifest_record(run)
    template["protocol"] = PROTOCOL; template["arms"] = list(ARMS)
    template["execution"]["provider_only"] = CHAT_PROVIDER
    template["evaluation"].update({"expected_trajectories": TASK_COUNT * len(SEEDS) * len(ARMS),
                                    "allocation_audit_sha256": base.file_sha(run / ALLOCATION_NAME),
                                    "pause_milestones": list(range(10, TASK_COUNT, 10))})
    template["banks"]["reasoningbank_sha256"] = rb["semantic_state_sha256"]
    template["method"] = {"copromem": POLICY_VERSION,
                          "retrieval": "task-supported semantic-spine projection; ambiguous schemas abstain",
                          "reasoningbank": "official top-1/no-abstention retrieval from a frozen engineering-validated bank",
                          "comparison_design": "shared executor/scorer/model/task/seed; preregistered real pilot",
                          "trial_semantics": "ordered stochastic labels, not provider-seed guarantees"}
    # Runtime identity v3 pins the top-level v6.2.2 policy hash.  Keep that
    # canonical policy shape and add the independent frozen-bank identity as
    # an extension; replacing it would make the manifest unverifiable.
    template["method_policy"] = dict(frozen_policy())
    template["method_policy"]["reasoningbank"] = dict(rb)
    template["budget"].update({"hard_cap_usd": HARD_CAP_USD, "historical_settled_exposure": allocation["historical_settled_exposure_usd"],
                                "historical_unresolved_reserved_exposure": allocation["historical_unresolved_reserved_exposure_usd"],
                                "reasoningbank_embedding_usd": TASK_COUNT * len(SEEDS) * 8192 * (0.02 / 1_000_000)})
    template["budget"]["all_in_usd"] += template["budget"]["reasoningbank_embedding_usd"] * 1.15
    runtime, inputs = build_evaluation_identity_v3(root=v622.ROOT, manifest=template)
    write_json(run / "runtime-identity.json", runtime)
    write_json(run / "runtime-identity.binding.json", {"runtime_identity_sha256": runtime["runtime_identity_sha256"],
               "runtime_identity_record_sha256": base.file_sha(run / "runtime-identity.json")})
    template["runtime_identity_inputs"] = inputs; template["runtime_identity_sha256"] = runtime["runtime_identity_sha256"]
    template["runtime_identity_file_sha256"] = base.file_sha(run / "runtime-identity.json")
    write_json(path, template)


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=["prepare", "freeze", "preflight", "run"])
    parser.add_argument("--run", required=True, type=Path); args = parser.parse_args(); run = args.run.resolve()
    _configure(run)
    if args.command == "prepare": prepare(run)
    elif args.command == "freeze": base.freeze(run)
    elif args.command == "preflight":
        base.load(run); parallel._rb_manifest_record(run)
        write_json(run / "provider-route-preflight.json", verify_locked_chat_route_available())
        base.st(run, "preflight_passed")
    else: base.run(run)


if __name__ == "__main__":
    main()
