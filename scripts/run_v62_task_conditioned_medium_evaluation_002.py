#!/usr/bin/env python3
"""Clean, non-importing successor to the failed v6.2 Evaluation 001.

The scientific design is unchanged.  The only accounting difference is that
Evaluation 001's settled infrastructure cost is carried once as historical
exposure and is never attributed to an Evaluation 002 arm.
"""
from __future__ import annotations

import argparse
import hashlib
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
from scripts import run_v62_task_conditioned_medium_evaluation as evaluation_001


PROTOCOL = "v6_2_task_conditioned_evaluation_002"
ALLOCATION_NAME = "allocation-audit.json"
HISTORICAL_EXPOSURE = 2.417682693


def _configure(run: pathlib.Path) -> None:
    evaluation_001._configure(run)
    base.PROTOCOL = PROTOCOL
    base.HISTORICAL_EXPOSURE = HISTORICAL_EXPOSURE
    base.PREEXISTING_RUN_FILES = {ALLOCATION_NAME, "custody-audit.json"}


def _prepare(run: pathlib.Path) -> None:
    _configure(run)
    base.prepare(run)
    template = json.loads((run / "template.json").read_text(encoding="utf-8"))
    audit = json.loads((run / ALLOCATION_NAME).read_text(encoding="utf-8"))
    template["evaluation"].update({
        "allocation_audit_sha256": hashlib.sha256((run / ALLOCATION_NAME).read_bytes()).hexdigest(),
        "task_family_ids": audit["selected_family_ids"],
        "allocation_kind": "public_inventory_round_robin_compatibility_conditioned",
    })
    template["predecessor_evaluation_001"] = {
        "manifest_sha256": "1f0855ee93ebbb8c22c60711cb6c9ccfb52e78cd6b4f1b73f9d525f1da11b316",
        "classification": "INFRASTRUCTURE_FAILED_VALIDATOR_BUG",
        "settled_infrastructure_exposure_usd": 0.00147015,
        "scientific_results_imported": False,
    }
    template["budget"]["historical_settled_exposure"] = HISTORICAL_EXPOSURE
    write_json(run / "template.json", template)


def _final_reports(run: pathlib.Path, manifest, marker, marker_file_sha256):
    base._write_final_reports(run, manifest, marker, marker_file_sha256)
    summary = json.loads((run / "live-summary.json").read_text(encoding="utf-8"))
    report = build_report(artifact_root=run / "artifacts", manifest=manifest, live_summary=summary)
    write_report(run, report)
    return report


def main() -> None:
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
