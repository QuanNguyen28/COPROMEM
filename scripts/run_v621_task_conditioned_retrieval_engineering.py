#!/usr/bin/env python3
"""Versioned 30-trajectory engineering runner for CoProMem v6.2.1.

This is a configuration layer over the maintained v6.1 five-arm orchestration,
not a fork of its executor, scorer, checkpoint, or ReMe lifecycle.  Its sole
method change is the public, task-conditioned CoProMem retrieval boundary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
from collections.abc import Mapping
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
os.environ.setdefault("COPROMEM_EVALUATION_RUNNER", str(pathlib.Path(__file__).resolve()))

from copromem.experiments.reme_copromem.runner import write_json
from copromem.experiments.reme_copromem.task_conditioned_retrieval_v621 import (
    POLICY_VERSION, derive_task_query, frozen_policy, reproduce_retrieval, retrieve,
    validate_task_query,
)
from scripts import run_v61_exploratory_evaluation as base


PROTOCOL = "v6_2_1_task_conditioned_retrieval_engineering_001"
RUN_NAME = "v6_2_1_task_conditioned_retrieval_engineering_001"
ARMS = ["no_memory", "official_upstream_reme_fixed", "official_upstream_reme_dynamic",
        "copromem_v6_2_1_fixed", "copromem_v6_2_1_dynamic"]
CALL_LIMITS = {"executor": 900, "reme_lifecycle": 128, "reme_embedding": 512,
               "copromem_decomposition": 0}
HISTORICAL_EXPOSURE = 3.416430479
HARD_CAP_USD = 300
ALLOCATION_NAME = "allocation-audit.json"


def _retrieval_record(*, state: Mapping[str, Any], query_operations: list[str], registry_sha256: str,
                      task_query: Mapping[str, Any] | None = None,
                      callable_registry: Mapping[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    """Adapter preserving the maintained runner call boundary exactly."""
    if callable_registry is None or task_query is None:
        raise ValueError("v6.2.1 retrieval requires frozen registry and public query provenance")
    if registry_sha256 != callable_registry.get("registry_sha256"):
        raise ValueError("v6.2.1 runner registry identity mismatch")
    if list(query_operations) != list(task_query.get("canonical_query_operations", ())):
        raise ValueError("v6.2.1 query operation boundary mismatch")
    guidance, provenance = retrieve(state, task_query, callable_registry)
    if guidance != reproduce_retrieval(state, task_query, callable_registry, provenance):
        raise ValueError("v6.2.1 retrieval cannot reproduce offline")
    return guidance, provenance


def _configure(run: pathlib.Path) -> None:
    audit_path = run / ALLOCATION_NAME
    if not audit_path.is_file():
        raise RuntimeError("frozen public engineering allocation audit is absent")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    selected = audit.get("selected_task_ids")
    if not isinstance(selected, list) or len(selected) != 3 or len(set(selected)) != 3:
        raise RuntimeError("v6.2.1 engineering allocation requires exactly three distinct task IDs")
    if audit.get("payloads_opened") is not False or audit.get("selection_source") != "public_pre_execution_metadata_only":
        raise RuntimeError("v6.2.1 allocation is not pre-payload public-only evidence")
    if audit.get("compatible_task_count") != 2 or audit.get("negative_control_count") != 1:
        raise RuntimeError("v6.2.1 allocation must preregister two compatible tasks and one negative control")
    base.PROTOCOL = PROTOCOL
    base.ARMS = list(ARMS)
    base.FROZEN_TASK_IDS = list(selected)
    base.EVALUATION_SPLIT = str(audit.get("split") or "test_normal")
    base.HARD_CAP_USD = HARD_CAP_USD
    base.CALL_LIMITS = dict(CALL_LIMITS)
    base.HISTORICAL_EXPOSURE = HISTORICAL_EXPOSURE
    base.COPRO_FIXED_ARM = "copromem_v6_2_1_fixed"
    base.COPRO_DYNAMIC_ARM = "copromem_v6_2_1_dynamic"
    base.TASK_MAJOR_ARM_FIRST = True
    base.PREEXISTING_RUN_FILES = {ALLOCATION_NAME, "engineering-protocol.json"}
    # These assignments are intentionally localized to this versioned entry
    # point.  Historical v6/v6.2 runners retain their frozen retrieval method.
    base.derive_task_query = derive_task_query
    base.validate_task_query = validate_task_query
    base.retrieval_record = _retrieval_record


def prepare(run: pathlib.Path) -> None:
    _configure(run)
    base.prepare(run)
    template_path = run / "template.json"
    template = json.loads(template_path.read_text(encoding="utf-8"))
    allocation_bytes = (run / ALLOCATION_NAME).read_bytes()
    template["method"] = {
        "copromem": POLICY_VERSION,
        "retrieval": "public task terminal-effect compatibility with committed response-attested prerequisites",
        "analysis_scope": "engineering integration validation; not efficacy or superiority evidence",
    }
    template["method_policy"] = frozen_policy()
    template["evaluation"].update({
        "allocation_audit_sha256": hashlib.sha256(allocation_bytes).hexdigest(),
        "expected_trajectories": 30,
        "compatible_task_count": 2,
        "negative_control_count": 1,
    })
    template["budget"].update({"historical_settled_exposure": HISTORICAL_EXPOSURE,
                                "hard_cap_usd": HARD_CAP_USD})
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
