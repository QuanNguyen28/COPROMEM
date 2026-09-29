#!/usr/bin/env python3
"""Dedicated v6.2, 30-task held-out exploratory evaluation entry point."""
from __future__ import annotations

import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
os.environ.setdefault("COPROMEM_EVALUATION_RUNNER", str(pathlib.Path(__file__).resolve()))

from copromem.experiments.reme_copromem.medium_reporting import build_report, write_report
from copromem.experiments.reme_copromem.runner import write_json
from scripts import run_v61_exploratory_evaluation as base


RUN_NAME = "v6_2_task_conditioned_evaluation_001"
ALLOCATION_NAME = "allocation-audit.json"
ARMS = ["no_memory", "official_upstream_reme_fixed", "official_upstream_reme_dynamic",
        "copromem_v6_2_fixed", "copromem_v6_2_dynamic"]
CALL_LIMITS = {"executor": 9000, "reme_lifecycle": 512, "reme_embedding": 4096,
               "copromem_decomposition": 0}


def _configure(run: pathlib.Path) -> None:
    audit_path = run / ALLOCATION_NAME
    if not audit_path.is_file():
        raise RuntimeError("frozen public allocation audit is absent")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    selected = audit.get("selected_task_ids")
    if not isinstance(selected, list) or len(selected) != 30 or len(set(selected)) != 30:
        raise RuntimeError("medium allocation must contain exactly 30 unique task IDs")
    if audit.get("split") != "test_normal" or audit.get("payloads_opened") is not False:
        raise RuntimeError("allocation is not a public-only test_normal allocation")
    base.PROTOCOL = "v6_2_task_conditioned_evaluation_001"
    base.ARMS = list(ARMS)
    base.FROZEN_TASK_IDS = list(selected)
    base.EVALUATION_SPLIT = "test_normal"
    base.HARD_CAP_USD = 300
    base.CALL_LIMITS = dict(CALL_LIMITS)
    base.COPRO_FIXED_ARM = "copromem_v6_2_fixed"
    base.COPRO_DYNAMIC_ARM = "copromem_v6_2_dynamic"
    base.TASK_MAJOR_ARM_FIRST = True
    base.PREEXISTING_RUN_FILES = {ALLOCATION_NAME, "custody-audit.json"}


def _prepare(run: pathlib.Path) -> None:
    _configure(run)
    base.prepare(run)
    template = json.loads((run / "template.json").read_text(encoding="utf-8"))
    audit = json.loads((run / ALLOCATION_NAME).read_text(encoding="utf-8"))
    template["evaluation"].update({"allocation_audit_sha256": __import__("hashlib").sha256((run / ALLOCATION_NAME).read_bytes()).hexdigest(),
                                   "task_family_ids": audit["selected_family_ids"],
                                   "allocation_kind": "public_inventory_round_robin_compatibility_conditioned"})
    template["method"] = {"copromem": "v6.2 task-conditioned contrastive common-core; abstract guidance",
                          "reme_dynamic_trial_semantics": "sequential_online_adaptation"}
    template["analysis"] = {"primary": "copromem_v6_2_dynamic versus official_upstream_reme_dynamic",
                            "unit": "task-level mean over two ordered stochastic trials",
                            "bootstrap": "deterministic 4000-draw task bootstrap"}
    write_json(run / "template.json", template)


def _final_reports(run: pathlib.Path, manifest, marker, marker_file_sha256):
    # Preserve the base terminal binding, then replace its intentionally terse
    # report with the frozen medium-scale task-level analysis.
    base._write_final_reports(run, manifest, marker, marker_file_sha256)
    summary = json.loads((run / "live-summary.json").read_text(encoding="utf-8"))
    report = build_report(artifact_root=run / "artifacts", manifest=manifest, live_summary=summary)
    write_report(run, report)
    return report


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "freeze", "preflight", "run"])
    parser.add_argument("--run", required=True, type=pathlib.Path)
    args = parser.parse_args(); args.run = args.run.resolve()
    _configure(args.run)
    if args.command == "prepare":
        _prepare(args.run)
    elif args.command == "freeze":
        base.freeze(args.run)
    elif args.command == "preflight":
        base.load(args.run); base.st(args.run, "preflight_passed")
    else:
        original = base._write_final_reports
        try:
            base._write_final_reports = _final_reports
            base.run(args.run)
        finally:
            base._write_final_reports = original


if __name__ == "__main__":
    main()
