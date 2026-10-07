#!/usr/bin/env python3
"""Isolated semantic-spine acquisition for CoProMem v6.2.7 seed diversity.

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
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
os.environ.setdefault("COPROMEM_EVALUATION_RUNNER", str(pathlib.Path(__file__).resolve()))

from copromem.experiments.reme_copromem.runner import write_json
from copromem.experiments.reme_copromem.contrastive_v6_runner import semantic_spine_task_batch_update
from copromem.experiments.reme_copromem.runtime_identity_v3 import IDENTITY_VERSION as RUNTIME_IDENTITY_V3, build_evaluation_identity_v3
from copromem.experiments.reme_copromem import task_conditioned_retrieval_v622 as seed_query
from copromem.experiments.reme_copromem.task_conditioned_retrieval_v627 import (
    POLICY_VERSION, derive_task_query, frozen_policy, reproduce_retrieval, retrieve,
    validate_task_query,
)
from scripts import run_v61_exploratory_evaluation as base
from scripts import run_v622_semantic_spine_engineering as v622


PROTOCOL = "v6_2_7_seed_acquisition_002"
RUN_NAME = PROTOCOL
ARMS = ["copromem_v6_2_7_dynamic"]
PUBLIC_APPS = ("amazon", "file_system", "gmail", "phone", "simple_note", "spotify", "splitwise", "todoist", "venmo")
SEED_APP_COUNT = 4
SEED_TASKS_PER_APP = 1
CALL_LIMITS = {"executor": 480, "reme_lifecycle": 0, "reme_embedding": 0,
               "copromem_decomposition": 0}
HARD_CAP_USD = 35
ALLOCATION_NAME = "allocation-audit-v627-seed-acquisition.json"
V627_BANK_ROOT: pathlib.Path | None = None
REVIEW = pathlib.Path(os.environ.get("COPROMEM_REVIEW_ROOT", "/mnt/e/Project/AAMAS/COPROMEM-review"))
def _external(path: str) -> pathlib.Path:
    if os.name == "posix" and len(path) >= 3 and path[1:3] == ":\\":
        return pathlib.Path("/mnt/" + path[0].lower() + path[2:].replace("\\", "/"))
    return pathlib.Path(path)


def _bank_identities() -> tuple[dict[str, Any], dict[str, Any]]:
    if V627_BANK_ROOT is None:
        raise RuntimeError("v6.2.7 bank root is not configured")
    # Read the immutable ReMe construction report directly. Calling the legacy
    # helper after rebinding ``base.COPRO`` makes that helper observe the new
    # v6.2.7 bank through its module global and compare it with the v6.1 hash.
    report_path = base.CONSTRUCTION / "FINAL_CONSTRUCTION_REPORT.json"
    if not report_path.is_file():
        raise RuntimeError("shared ReMe construction report is absent")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("shared_bank_sha256") != "6c3bc799ec0beb034fd2b81ee0d5cbf6e89a14f3a5a39ebf70d34853686b00a0":
        raise RuntimeError("shared ReMe bank identity is invalid")
    gate_path = V627_BANK_ROOT / "semantic-admission-gate.json"
    bank_path = V627_BANK_ROOT / "fixed-bank.json"
    if not gate_path.is_file() or not bank_path.is_file():
        raise RuntimeError("v6.2.7 admitted bank artifacts are absent")
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    bank = json.loads(bank_path.read_text(encoding="utf-8"))
    if (gate.get("version") != "copromem-v6.2.2-bank-admission-v1" or gate.get("passed") is not True
            or gate.get("provider_calls") != 0 or gate.get("state_sha256") != base.digest(bank)):
        raise RuntimeError("v6.2.7 bank admission identity is invalid")
    return report, gate


def _retrieval_record(*, state: Mapping[str, Any], query_operations: list[str], registry_sha256: str,
                      task_query: Mapping[str, Any] | None = None,
                      callable_registry: Mapping[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    """No-guidance acquisition boundary; learned evidence never feeds itself."""
    if callable_registry is None or task_query is None:
        raise ValueError("seed acquisition requires frozen query provenance")
    if registry_sha256 != callable_registry.get("registry_sha256"):
        raise ValueError("seed acquisition registry differs")
    if list(query_operations) != list(task_query.get("canonical_query_operations", ())):
        raise ValueError("seed acquisition query boundary differs")
    provenance={"policy_version":"copromem-v6.2.7-seed-no-guidance-v1",
                "pre_state_semantic_sha256":base.digest(state),"task_query":dict(task_query),
                "task_query_sha256":task_query["query_sha256"],"registry_sha256":registry_sha256,
                "selection_decision":"acquisition_no_self_guidance","selected_schema_id":None,
                "selected_schema_ids":[],"guidance":"","guidance_sha256":base.digest(""),"guidance_nonempty":False}
    provenance["retrieval_sha256"]=base.digest(provenance)
    return "",provenance


def _reproduce_seed(state: Mapping[str, Any], task_query: Mapping[str, Any], callable_registry: Mapping[str, Any], provenance: Mapping[str, Any]) -> str:
    guidance, expected=_retrieval_record(state=state,query_operations=list(task_query["canonical_query_operations"]),registry_sha256=str(callable_registry["registry_sha256"]),task_query=task_query,callable_registry=callable_registry)
    if dict(provenance)!=expected: raise ValueError("seed acquisition provenance does not reproduce")
    return guidance

def _configure(run: pathlib.Path) -> None:
    audit_path = run / ALLOCATION_NAME
    if not audit_path.is_file():
        raise RuntimeError("frozen v6.2.7 seed acquisition allocation is absent")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    selected = audit.get("selected_task_ids")
    expected_seed_tasks = SEED_APP_COUNT * SEED_TASKS_PER_APP
    if (audit.get("version") != "v6.2.7-seed-acquisition-allocation-v1" or not isinstance(selected, list)
            or len(selected) != expected_seed_tasks or len(set(selected)) != expected_seed_tasks or audit.get("split") != "train"):
        raise RuntimeError("v6.2.7 seed allocation is invalid")
    selected_apps = audit.get("selected_apps")
    if (not isinstance(selected_apps, list) or len(selected_apps) != SEED_APP_COUNT
            or selected_apps != sorted(set(selected_apps))
            or any(app not in PUBLIC_APPS for app in selected_apps)):
        raise RuntimeError("v6.2.7 seed app diversity allocation is invalid")
    base.PROTOCOL = PROTOCOL; base.SOURCE = REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_shared_acquisition_001"; base.CONSTRUCTION = REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_1_exploratory_diagnostic_construction_003"; base.ARMS = list(ARMS); base.FROZEN_TASK_IDS = list(selected)
    base.EVALUATION_SPLIT = "train"; base.EVALUATION_SEEDS = (11001, 11002)
    base.HARD_CAP_USD = HARD_CAP_USD; base.CALL_LIMITS = {**CALL_LIMITS, "executor": len(selected) * 2 * 30}
    base.HISTORICAL_EXPOSURE = 0.0; base.COPRO_FIXED_ARM = "copromem_v6_2_7_fixed_unregistered"
    base.COPRO_DYNAMIC_ARM = ARMS[0]; base.TASK_MAJOR_ARM_FIRST = True
    base.PREEXISTING_RUN_FILES = {ALLOCATION_NAME}
    bank = _external(str(audit["seed_bank"]["path"])); global V627_BANK_ROOT
    V627_BANK_ROOT = bank; base.COPRO = bank; v622.V622_BANK_ROOT = bank; base.identities = v622._bank_identities
    base.derive_task_query = seed_query.derive_task_query; base.validate_task_query = seed_query.validate_task_query
    base.retrieval_record = _retrieval_record; base.reproduce_retrieval = _reproduce_seed
    # Isolated seed acquisition may retain malformed native read attempts as
    # audit-only rows.  They never enter the semantic graph; invalid writes
    # and every ordinary runner remain fail-closed.
    def seed_update(**kwargs: Any):
        return semantic_spine_task_batch_update(**kwargs, discard_schema_invalid_reads=True)
    base.semantic_task_batch_update = seed_update


def allocate(run: pathlib.Path, inventory_path: pathlib.Path, evaluation_allocation: pathlib.Path, bank_root: pathlib.Path) -> None:
    if run.exists() and any(run.iterdir()): raise RuntimeError("allocation target must be empty")
    inventory=json.loads(inventory_path.read_text(encoding="utf-8")); evaluation=json.loads(evaluation_allocation.read_text(encoding="utf-8"))
    excluded=set(evaluation.get("selected_task_ids", ()))
    consumed_root = REVIEW / "artifacts/research/official_reme_copromem_pilot"
    for prior in consumed_root.glob("v6_2_7_seed_acquisition_*"):
        for artifact in prior.glob("artifacts/*/*/trial-*.json"):
            try: excluded.add(str(json.loads(artifact.read_text(encoding="utf-8")).get("task_id") or ""))
            except (OSError, json.JSONDecodeError): pass
    rows=[row for row in inventory.get("unseen_train_tasks", []) if isinstance(row,dict) and str(row.get("task_id")) not in excluded]
    groups=defaultdict(list)
    for row in rows:
        text=str(row.get("instruction", "")).lower(); task=str(row.get("task_id", "")); family=task.rsplit("_",1)[0]
        apps=[app for app in PUBLIC_APPS if app.replace("_", " ") in text or app in text]
        if len(apps)==1: groups[apps[0]].append((family,task))
    selected=[]
    available: list[tuple[str, list[str]]] = []
    for app in PUBLIC_APPS:
        families=defaultdict(list)
        for family,task in groups[app]: families[family].append(task)
        # Dynamic learning receives two independent seeds for every selected
        # task, so it does not need two task IDs from one family.  Requiring
        # sibling IDs needlessly exhausts a public train inventory after a
        # prior no-replay acquisition attempt.
        viable=sorted((family,sorted(tasks)) for family,tasks in families.items() if tasks)
        if viable:
            _family,tasks=viable[0]
            available.append((app, tasks[:SEED_TASKS_PER_APP]))
    if len(available) < SEED_APP_COUNT:
        raise RuntimeError("fewer than four fresh single-app acquisition candidates remain")
    chosen = available[:SEED_APP_COUNT]
    for _app, tasks in chosen:
        selected.extend(tasks)
    state=json.loads((bank_root/"fixed-bank.json").read_text(encoding="utf-8"))
    gate=json.loads((bank_root/"semantic-admission-gate.json").read_text(encoding="utf-8"))
    value={"version":"v6.2.7-seed-acquisition-allocation-v1","split":"train","selected_task_ids":selected,
           "selected_apps":[app for app,_tasks in chosen],
           "selected_task_ids_sha256":hashlib.sha256(json.dumps(selected,separators=(",",":")).encode()).hexdigest(),
           "evaluation_exclusion_sha256":hashlib.sha256(json.dumps(sorted(excluded),separators=(",",":")).encode()).hexdigest(),
           "seed_bank":{"path":str(bank_root.resolve()),"fixed_bank_sha256":hashlib.sha256((bank_root/"fixed-bank.json").read_bytes()).hexdigest(),"gate_sha256":hashlib.sha256((bank_root/"semantic-admission-gate.json").read_bytes()).hexdigest(),"state_sha256":base.digest(state)},
           "inventory_sha256":hashlib.sha256(inventory_path.read_bytes()).hexdigest(),"provider_calls":0,"payloads_opened":False}
    if gate.get("state_sha256") != value["seed_bank"]["state_sha256"]: raise RuntimeError("seed bank gate differs")
    run.mkdir(parents=True,exist_ok=False); write_json(run/ALLOCATION_NAME,value)

def prepare(run: pathlib.Path) -> None:
    _configure(run)
    base.prepare(run)
    template_path = run / "template.json"
    template = json.loads(template_path.read_text(encoding="utf-8"))
    allocation_bytes = (run / ALLOCATION_NAME).read_bytes()
    count = len(template["evaluation"]["task_ids"])
    template["method"] = {
        "copromem": POLICY_VERSION,
        "retrieval": "task-supported semantic-spine projection; ambiguous schemas abstain",
        "analysis_scope": "engineering integration validation; not efficacy or superiority evidence",
    }
    template["method_policy"] = frozen_policy()
    template["evaluation"].update({
        "allocation_audit_sha256": hashlib.sha256(allocation_bytes).hexdigest(),
        "expected_trajectories": count * len(base.EVALUATION_SEEDS) * len(ARMS),
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
    parser=argparse.ArgumentParser(); parser.add_argument("command",choices=["allocate","prepare","freeze","preflight","run"]); parser.add_argument("--run",required=True,type=pathlib.Path); parser.add_argument("--inventory",type=pathlib.Path); parser.add_argument("--evaluation-allocation",type=pathlib.Path); parser.add_argument("--seed-bank",type=pathlib.Path); args=parser.parse_args(); args.run=args.run.resolve()
    if args.command=="allocate":
        if not(args.inventory and args.evaluation_allocation and args.seed_bank): raise SystemExit("allocate requires --inventory --evaluation-allocation --seed-bank")
        allocate(args.run,args.inventory.resolve(),args.evaluation_allocation.resolve(),args.seed_bank.resolve()); return
    _configure(args.run)
    if args.command=="prepare": prepare(args.run)
    elif args.command=="freeze": base.freeze(args.run)
    elif args.command=="preflight": base.load(args.run); base.st(args.run,"preflight_passed")
    else: base.run(args.run)

if __name__=="__main__": main()
