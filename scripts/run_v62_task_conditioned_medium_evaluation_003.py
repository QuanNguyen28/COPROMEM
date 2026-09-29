#!/usr/bin/env python3
"""Immutable-prefix recovery successor for v6.2 Evaluation 002.

The successor contains no task selection.  It rebinds only hash-verified local
evidence from the stopped predecessor, completes the not-yet-started CoProMem
task-boundary transaction offline, and then delegates remaining work to the
maintained five-arm runner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from copromem.experiments.reme_copromem.contrastive_v6_runner import semantic_task_batch_update
from copromem.experiments.reme_copromem.copromem_dynamic_checkpoint import CoProMemDynamicCheckpointManager
from copromem.experiments.reme_copromem.live_summary import reconcile_artifacts, reconcile_ledger
from copromem.experiments.reme_copromem.recovery_import import copy_evidence_file, file_sha256, import_scored_artifact
from copromem.experiments.reme_copromem.runner import write_json
from scripts import run_v61_exploratory_evaluation as base
from scripts import run_v62_task_conditioned_medium_evaluation_002 as predecessor


PROTOCOL = "v6_2_task_conditioned_evaluation_003_recovery"
SOURCE_PROTOCOL = "v6_2_task_conditioned_evaluation_002"
SOURCE_MANIFEST_SHA256 = "61370ee495bfa33502ab494369a7bb07903272068d2009753e719fabb5e5fb1b"
SOURCE_RUN = ROOT / "artifacts/research/official_reme_copromem_pilot/v6_2_task_conditioned_evaluation_002"
ALLOCATION_NAME = "allocation-audit.json"
HISTORICAL_EXPOSURE = predecessor.HISTORICAL_EXPOSURE


def _canonical(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def _configure(run: pathlib.Path) -> None:
    predecessor._configure(run)
    base.PROTOCOL = PROTOCOL
    base.HISTORICAL_EXPOSURE = HISTORICAL_EXPOSURE
    base.PREEXISTING_RUN_FILES = {ALLOCATION_NAME, "custody-audit.json", "recovery-amendment.json"}


def _source_manifest() -> dict[str, Any]:
    path = SOURCE_RUN / "manifest.json"
    if not path.is_file() or file_sha256(path) != SOURCE_MANIFEST_SHA256:
        raise RuntimeError("Evaluation 002 manifest identity mismatch")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("protocol") != SOURCE_PROTOCOL:
        raise RuntimeError("Evaluation 002 protocol identity mismatch")
    return value


def _prepare(run: pathlib.Path) -> None:
    source = _source_manifest()
    run.mkdir(parents=True, exist_ok=True)
    for name in (ALLOCATION_NAME, "custody-audit.json"):
        copy_evidence_file(SOURCE_RUN / name, run / name)
    _configure(run)
    amendment = {
        "version": "v6.2-evaluation-003-infrastructure-recovery-v1",
        "source_protocol": SOURCE_PROTOCOL,
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "source_status_sha256": file_sha256(SOURCE_RUN / "runner-status.json"),
        "source_ledger_sha256": file_sha256(SOURCE_RUN / "ledger.jsonl"),
        "scientific_protocol_unchanged": True,
        "source_task_ids": source["evaluation"]["task_ids"],
        "source_arms": source["arms"],
        "repairs": ["semantic-bank legacy-container compatibility", "v6.2 restart ledger arm registration"],
        "recovery_rule": "import only hash-verified scored artifacts; complete only the unstarted offline CoProMem task boundary",
    }
    write_json(run / "recovery-amendment.json", amendment)
    base.prepare(run)
    template = json.loads((run / "template.json").read_text(encoding="utf-8"))
    template["protocol"] = PROTOCOL
    template["predecessor_evaluation_002"] = {
        "manifest_sha256": SOURCE_MANIFEST_SHA256,
        "status_sha256": amendment["source_status_sha256"],
        "ledger_sha256": amendment["source_ledger_sha256"],
        "completed_prefix_expected": 10,
        "imported_scientific_evidence": True,
        "infrastructure_recovery_only": True,
    }
    template["recovery_amendment_sha256"] = file_sha256(run / "recovery-amendment.json")
    write_json(run / "template.json", template)


def _source_artifact_paths(source_manifest: dict[str, Any]) -> list[pathlib.Path]:
    artifacts = sorted((SOURCE_RUN / "artifacts").glob("**/*.json"))
    rows = reconcile_artifacts(SOURCE_RUN / "artifacts", expected_tasks=source_manifest["evaluation"]["task_ids"],
                               expected_seeds=source_manifest["evaluation"]["seeds"], registered_arms=source_manifest["arms"])
    if len(artifacts) != 10 or len(rows) != 10:
        raise RuntimeError("Evaluation 002 completed artifact prefix is not exactly ten valid trajectories")
    first = str(source_manifest["evaluation"]["task_ids"][0])
    if any(str(row["task_id"]) != first for row in rows):
        raise RuntimeError("Evaluation 002 completed artifacts exceed the first frozen task boundary")
    return artifacts


def _copy_retrievals(run: pathlib.Path, source_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    task = str(source_manifest["evaluation"]["task_ids"][0])
    for arm in (base.COPRO_FIXED_ARM, base.COPRO_DYNAMIC_ARM):
        for trial in range(1, len(source_manifest["evaluation"]["seeds"]) + 1):
            source = SOURCE_RUN / "retrievals" / task / f"{arm}-{trial}.json"
            target = run / "retrievals" / task / source.name
            records.append({"relative_path": str(source.relative_to(SOURCE_RUN)).replace("\\", "/"),
                            "source_sha256": file_sha256(source),
                            "target_sha256": copy_evidence_file(source, target)})
    return records


def _copy_reme_dynamic_chain(run: pathlib.Path) -> list[dict[str, Any]]:
    source_root = SOURCE_RUN / "reme-dynamic-checkpoints"
    records: list[dict[str, Any]] = []
    for source in sorted(path for path in source_root.rglob("*") if path.is_file()):
        target = run / "reme-dynamic-checkpoints" / source.relative_to(source_root)
        records.append({"relative_path": str(source.relative_to(source_root)).replace("\\", "/"),
                        "source_sha256": file_sha256(source),
                        "target_sha256": copy_evidence_file(source, target)})
    return records


def _recover_copromem_boundary(run: pathlib.Path, manifest: dict[str, Any]) -> dict[str, Any]:
    fixed = json.loads((base.COPRO / "fixed-bank.json").read_text(encoding="utf-8"))
    registry = json.loads(base.REG.read_text(encoding="utf-8"))
    dynamic = json.loads(json.dumps(fixed, sort_keys=True))
    manager = CoProMemDynamicCheckpointManager(
        root=run / "copromem-dynamic-checkpoints", manifest_sha256=file_sha256(run / "manifest.json"),
        source_identity_sha256=base.digest({"git_commit": manifest.get("git_commit", "offline-shadow")}),
        registry_sha256=registry["registry_sha256"], ordered_tasks=manifest["evaluation"]["task_ids"],
        fixed_initial_state=fixed, dynamic_initial_state=dynamic)
    prefix = manager.reconcile(ledger_reconciled=True, fixed_current_state=fixed)
    if prefix["completed_task_count"] or prefix["next_transition"] != "task_pre_state_frozen":
        raise RuntimeError("Evaluation 003 CoProMem recovery prefix is not empty")
    task = str(manifest["evaluation"]["task_ids"][0])
    pre = json.loads(json.dumps(dynamic, sort_keys=True))
    manager.freeze_task_pre_state(task, pre)
    artifacts = [json.loads((run / "artifacts" / task / base.COPRO_DYNAMIC_ARM / f"trial-{trial}.json").read_text(encoding="utf-8"))
                 for trial in range(1, len(manifest["evaluation"]["seeds"]) + 1)]
    retrievals = [json.loads((run / "retrievals" / task / f"{base.COPRO_DYNAMIC_ARM}-{trial}.json").read_text(encoding="utf-8"))
                  for trial in range(1, len(manifest["evaluation"]["seeds"]) + 1)]
    manager.record(task, "retrievals_materialized",
                   task_query_hashes=[str(row["task_query"]["query_sha256"]) for row in retrievals],
                   retrieval_hashes=[base.digest(row) for row in retrievals])
    manager.record(task, "trajectories_complete", artifact_hashes=[base.digest(row) for row in artifacts],
                   scorer_evidence_hashes=[str(row["official_scorer_evidence"]["sha256"]) for row in artifacts])
    post, marker, audit = semantic_task_batch_update(
        artifacts=artifacts, registry=registry, pre_state=pre,
        evidence_paths=[str(row["execution_evidence_path"]) for row in artifacts], run_root=run)
    manager.record(task, "batch_ready", semantic_projection_hashes=[row["semantic_projection_sha256"] for row in audit["semantic_graph_audits"]])
    manager.record(task, "semantic_plan_persisted", plan_sha256=audit["plan"]["plan_sha256"])
    manager.record(task, "validation_persisted", validation_sha256=base.digest(audit["validation"]),
                   validation_passed=bool(audit["validation"]["passed"]))
    manager.record(task, "commit_persisted", marker_sha256=base.digest(marker), state=marker["state"],
                   winner_schema_id=marker.get("winner_schema_id"))
    manager.snapshot_post_state(task, post, marker_sha256=base.digest(marker), plan_sha256=audit["plan"]["plan_sha256"],
                                validation_sha256=base.digest(audit["validation"]))
    manager.record(task, "next_task_authorized", post_state_sha256=base.digest(post))
    state = manager.reconcile(ledger_reconciled=True, fixed_current_state=fixed)
    if state["completed_task_count"] != 1 or state["next_task_id"] != manifest["evaluation"]["task_ids"][1]:
        raise RuntimeError("Evaluation 003 CoProMem recovery did not authorize exactly one task boundary")
    return {"task_id": task, "pre_state_sha256": base.digest(pre), "post_state_sha256": base.digest(post),
            "marker_sha256": base.digest(marker), "audit_sha256": base.digest(audit),
            "validation_passed": bool(audit["validation"]["passed"]), "next_task_id": state["next_task_id"]}


def recover(run: pathlib.Path) -> None:
    _configure(run)
    manifest = base.load(run)
    source_manifest = _source_manifest()
    if manifest["evaluation"]["task_ids"] != source_manifest["evaluation"]["task_ids"] or manifest["arms"] != source_manifest["arms"]:
        raise RuntimeError("recovery manifest changes frozen scientific allocation")
    if (run / "recovery-import-audit.json").exists():
        raise RuntimeError("recovery import already exists; use run reconciliation")
    source_rows = _source_artifact_paths(source_manifest)
    copy_evidence_file(SOURCE_RUN / "ledger.jsonl", run / "ledger.jsonl")
    imported = []
    for source in source_rows:
        target = run / "artifacts" / source.relative_to(SOURCE_RUN / "artifacts")
        imported.append(import_scored_artifact(source_artifact=source, source_run=SOURCE_RUN, target_artifact=target,
                                               target_run=run, source_manifest_sha256=SOURCE_MANIFEST_SHA256))
    retrievals = _copy_retrievals(run, source_manifest)
    reme_chain = _copy_reme_dynamic_chain(run)
    copied = reconcile_artifacts(run / "artifacts", expected_tasks=manifest["evaluation"]["task_ids"],
                                 expected_seeds=manifest["evaluation"]["seeds"], registered_arms=manifest["arms"])
    ledger = reconcile_ledger(run / "ledger.jsonl", historical_expected_usd=HISTORICAL_EXPOSURE, registered_arms=manifest["arms"])
    if len(copied) != 10 or ledger.unresolved_reservation_ids:
        raise RuntimeError("recovery import evidence or ledger is incomplete")
    copro = _recover_copromem_boundary(run, manifest)
    audit = {"version": "v6.2-evaluation-003-import-v1", "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
             "source_artifact_count": len(imported), "imported": imported, "retrievals": retrievals,
             "reme_dynamic_checkpoint_files": reme_chain, "copromem_offline_task_boundary": copro,
             "source_ledger_sha256": file_sha256(SOURCE_RUN / "ledger.jsonl"),
             "target_ledger_sha256": file_sha256(run / "ledger.jsonl"),
             "ledger_unresolved": list(ledger.unresolved_reservation_ids),
             "scientific_protocol_unchanged": True}
    audit["audit_sha256"] = _canonical(audit)
    write_json(run / "recovery-import-audit.json", audit)
    base.summary(run, manifest, state="recovery_imported")
    base.st(run, "recovery_imported", manifest_sha256=file_sha256(run / "manifest.json"),
            imported_completed_trajectories=len(imported), next_task_id=copro["next_task_id"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "freeze", "recover", "preflight", "run"])
    parser.add_argument("--run", type=pathlib.Path, required=True)
    args = parser.parse_args(); args.run = args.run.resolve()
    if args.command == "prepare":
        _prepare(args.run)
        return
    _configure(args.run)
    if args.command == "freeze":
        base.freeze(args.run)
    elif args.command == "recover":
        recover(args.run)
    elif args.command == "preflight":
        base.load(args.run)
        if not (args.run / "recovery-import-audit.json").is_file():
            raise RuntimeError("recovery import is required before preflight")
        base.st(args.run, "preflight_passed", manifest_sha256=file_sha256(args.run / "manifest.json"))
    else:
        base.run(args.run)


if __name__ == "__main__":
    main()
