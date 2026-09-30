#!/usr/bin/env python3
"""Evaluation 005: a hash-bound continuation of the immutable 20-item prefix.

This entry point never alters Evaluation 004.  It first materializes an atomic
copy of its scored evidence, proves the shared recovery-state marker, and
replays only deterministic local CoProMem checkpoint construction.  The first
provider-capable operation is therefore the next frozen trajectory, not a
historical lifecycle, embedding, executor, scorer, or acquisition operation.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from typing import Any, Mapping

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
os.environ.setdefault("COPROMEM_EVALUATION_RUNNER", str(pathlib.Path(__file__).resolve()))

from copromem.contrastive_graph_v6 import digest
from copromem.experiments.reme_copromem.contrastive_v6_runner import semantic_task_batch_update, scorer_evidence_sha256
from copromem.experiments.reme_copromem.copromem_dynamic_checkpoint import CoProMemDynamicCheckpointManager
from copromem.experiments.reme_copromem.live_summary import reconcile_artifacts, reconcile_ledger
from copromem.experiments.reme_copromem.recovery_import import (RecoveryImportError, canonical_sha256,
                                                                  copy_evidence_file, file_sha256,
                                                                  import_scored_artifact)
from copromem.experiments.reme_copromem.runner import AppendOnlyLedger, write_json
from copromem.experiments.reme_copromem.v62_recovery_prefix import NEXT, import_real_prefix, validate_real_prefix
from copromem.experiments.reme_copromem.v62_recovery_start import admit
from copromem.experiments.reme_copromem.v62_recovery_state import assemble, publish
from copromem.experiments.reme_copromem.medium_reporting import build_report, write_report
from scripts import run_v61_exploratory_evaluation as base
from scripts import run_v62_task_conditioned_medium_evaluation as scientific


PROTOCOL = "v6_2_task_conditioned_evaluation_005_recovery"
SOURCE_RUN = ROOT / "artifacts/research/official_reme_copromem_pilot/v6_2_task_conditioned_evaluation_004_recovery"
SOURCE_MANIFEST_SHA256 = "f93bbed7f2811fd736866d3d6ace3212e719007923e7cd5e672060aed24a803f"
FORENSIC = ROOT / "research/reme_copromem_fixed_dynamic_review/v6_2_evaluation_004_keyerror_forensic.json"
HISTORICAL_EXPOSURE = 2.435839694
RECOVERY_IDENTITY_KEY = "recovery_successor_identity"
PREFIX_NAME = "recovery-execution-prefix.json"
_BASE_FINAL_REPORTS = base._write_final_reports
_BASE_SUMMARY = base.summary


def summary(run: pathlib.Path, manifest: dict[str, Any], *, state: str = "running", final: bool = False) -> None:
    """Keep the maintained ledger-derived summary after successor configuration."""
    _BASE_SUMMARY(run, manifest, state=state, final=final)


def _identity(manifest: Mapping[str, Any]) -> dict[str, str]:
    return {"protocol": PROTOCOL, "source_commit": str(manifest["git_commit"])}


def _source_manifest() -> dict[str, Any]:
    path = SOURCE_RUN / "manifest.json"
    if not path.is_file() or file_sha256(path) != SOURCE_MANIFEST_SHA256:
        raise RuntimeError("Evaluation 004 source manifest identity mismatch")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("evaluation", {}).get("expected_trajectories") != 300:
        raise RuntimeError("Evaluation 004 source has the wrong frozen denominator")
    return value


def _configure(run: pathlib.Path) -> None:
    scientific._configure(run)
    base.PROTOCOL = PROTOCOL
    base.HISTORICAL_EXPOSURE = HISTORICAL_EXPOSURE
    base.PREEXISTING_RUN_FILES = {
        "allocation-audit.json", "custody-audit.json", "recovery-amendment.json",
        "recovery-import-spec.json", "recovery_import_complete.json", "recovery-state.json",
        PREFIX_NAME,
    }
    base.summary = summary
    base._dynamic_checkpoint = _dynamic_checkpoint


def _copy_public_preallocation_files(run: pathlib.Path) -> None:
    for name in ("allocation-audit.json", "custody-audit.json"):
        source = SOURCE_RUN / name
        if not source.is_file():
            raise RuntimeError(f"Evaluation 004 public preallocation evidence is absent: {name}")
        copy_evidence_file(source, run / name)


def prepare(run: pathlib.Path) -> None:
    run.mkdir(parents=True, exist_ok=True)
    _copy_public_preallocation_files(run)
    _configure(run)
    source = _source_manifest()
    if list(source["evaluation"]["task_ids"]) != list(base.FROZEN_TASK_IDS) or list(source["arms"]) != list(base.ARMS):
        raise RuntimeError("recovery would change the frozen scientific allocation")
    amendment = {
        "version": "v6.2-evaluation-005-recovery-v1",
        "source_protocol": str(source.get("protocol")),
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "source_ledger_sha256": file_sha256(SOURCE_RUN / "ledger.jsonl"),
        "source_status_sha256": file_sha256(SOURCE_RUN / "runner-status.json"),
        "prefix_count": 20,
        "scientific_protocol_unchanged": True,
        "import_rule": "twenty source artifacts are copied through atomic envelopes and count once; no source provider call is recharged or replayed",
        "dynamic_rule": "ReMe Dynamic restores only reload-tested source snapshots; CoProMem task boundaries are reconstructed locally from exact imported artifacts",
    }
    write_json(run / "recovery-amendment.json", amendment)
    base.prepare(run)
    template = json.loads((run / "template.json").read_text(encoding="utf-8"))
    template.update({
        "protocol": PROTOCOL,
        "recovery_amendment_sha256": file_sha256(run / "recovery-amendment.json"),
        "predecessor_evaluation_004": {
            "manifest_sha256": SOURCE_MANIFEST_SHA256,
            "completed_prefix_expected": 20,
            "scientific_evidence_imported": True,
            "source_total_settled_exposure": HISTORICAL_EXPOSURE,
            "provider_calls_not_recharged": True,
        },
    })
    template["budget"]["historical_settled_exposure"] = HISTORICAL_EXPOSURE
    write_json(run / "template.json", template)


def freeze(run: pathlib.Path) -> None:
    _configure(run)
    base.freeze(run)


def _source_settlements() -> set[str]:
    ids: set[str] = set()
    # The source itself binds the final ten artifacts; its predecessor binds
    # the imported first ten.  Both are immutable historical ledger evidence.
    for ledger in (SOURCE_RUN / "ledger.jsonl", SOURCE_RUN.parent / "v6_2_task_conditioned_evaluation_002" / "ledger.jsonl"):
        for line in ledger.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("event") == "settle" and str(row.get("role", "")).startswith(("reme_lifecycle:reme-dynamic", "reme_embedding:reme-dynamic")):
                ids.add(str(row["id"]))
    if not ids:
        raise RuntimeError("source ReMe Dynamic lifecycle settlement IDs are absent")
    return ids


def _install_source_marker_validation() -> None:
    source_ids = _source_settlements()
    original = base._validate_marker_settlements

    def validate(path: pathlib.Path, marker: dict[str, Any]) -> None:
        if int(marker.get("ordered_update_index", 0)) <= 4:
            ids = set(map(str, marker.get("newly_settled_lifecycle_or_embedding_ids", [])))
            if not ids or not ids.issubset(source_ids):
                raise RuntimeError("imported ReMe Dynamic marker has an unbound source settlement")
            return
        original(path, marker)

    base._validate_marker_settlements = validate


def _dynamic_checkpoint(run: pathlib.Path, manifest: dict[str, Any], dynamic: Any, verifier: Any):
    if not hasattr(base, "_dynamic_checkpoint_original"):
        raise RuntimeError("original ReMe Dynamic checkpoint factory was not captured")
    return base._dynamic_checkpoint_original(run, manifest, dynamic, verifier)


def _copy_retrievals(run: pathlib.Path, source_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    copied: list[dict[str, str]] = []
    for row in source_rows:
        identity = row["identity"]
        arm = str(identity["arm"])
        if arm not in {base.COPRO_FIXED_ARM, base.COPRO_DYNAMIC_ARM}:
            continue
        source = SOURCE_RUN / "retrievals" / str(identity["task_id"]) / f"{arm}-{identity['trial_id']}.json"
        target = run / "retrievals" / str(identity["task_id"]) / source.name
        copied.append({"relative_path": str(target.relative_to(run)).replace("\\", "/"),
                       "source_sha256": file_sha256(source), "target_sha256": copy_evidence_file(source, target)})
    return copied


def _copy_reme_chain(run: pathlib.Path) -> list[dict[str, str]]:
    source_root = SOURCE_RUN / "reme-dynamic-checkpoints"
    records: list[dict[str, str]] = []
    for source in sorted(path for path in source_root.rglob("*") if path.is_file()):
        target = run / "reme-dynamic-checkpoints" / source.relative_to(source_root)
        records.append({"relative_path": str(source.relative_to(source_root)).replace("\\", "/"),
                        "source_sha256": file_sha256(source), "target_sha256": copy_evidence_file(source, target)})
    return records


def _import_scored_prefix(run: pathlib.Path, source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    imported: list[dict[str, Any]] = []
    for source in source_rows:
        identity = source["identity"]
        target = run / "artifacts" / str(identity["task_id"]) / str(identity["arm"]) / f"trial-{identity['trial_id']}.json"
        imported.append(import_scored_artifact(source_artifact=pathlib.Path(str(source["artifact_path"])),
                                               source_run=SOURCE_RUN, target_artifact=target, target_run=run,
                                               source_manifest_sha256=str(source["source_manifest_sha256"])))
    return imported


def _recover_copromem_prefix(run: pathlib.Path, manifest: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    fixed = json.loads((base.COPRO / "fixed-bank.json").read_text(encoding="utf-8"))
    registry = json.loads(base.REG.read_text(encoding="utf-8"))
    dynamic = json.loads(json.dumps(fixed, ensure_ascii=False, sort_keys=True))
    manager = CoProMemDynamicCheckpointManager(
        root=run / "copromem-dynamic-checkpoints", manifest_sha256=file_sha256(run / "manifest.json"),
        source_identity_sha256=digest({"git_commit": manifest["git_commit"]}), registry_sha256=registry["registry_sha256"],
        ordered_tasks=manifest["evaluation"]["task_ids"], fixed_initial_state=fixed, dynamic_initial_state=dynamic,
    )
    records: list[dict[str, Any]] = []
    for task in list(manifest["evaluation"]["task_ids"])[:2]:
        pre = json.loads(json.dumps(dynamic, ensure_ascii=False, sort_keys=True))
        manager.freeze_task_pre_state(task, pre)
        artifacts = [json.loads((run / "artifacts" / task / base.COPRO_DYNAMIC_ARM / f"trial-{trial}.json").read_text(encoding="utf-8"))
                     for trial in range(1, 3)]
        retrievals = [json.loads((run / "retrievals" / task / f"{base.COPRO_DYNAMIC_ARM}-{trial}.json").read_text(encoding="utf-8"))
                      for trial in range(1, 3)]
        manager.record(task, "retrievals_materialized", task_query_hashes=[str(item["task_query"]["query_sha256"]) for item in retrievals],
                       retrieval_hashes=[digest(item) for item in retrievals])
        manager.record(task, "trajectories_complete", artifact_hashes=[digest(item) for item in artifacts],
                       scorer_evidence_hashes=[scorer_evidence_sha256(item) for item in artifacts])
        post, marker, audit = semantic_task_batch_update(artifacts=artifacts, registry=registry, pre_state=pre,
            evidence_paths=[str(item["execution_evidence_path"]) for item in artifacts], run_root=run)
        manager.record(task, "batch_ready", semantic_projection_hashes=[item["semantic_projection_sha256"] for item in audit["semantic_graph_audits"]])
        manager.record(task, "semantic_plan_persisted", plan_sha256=audit["plan"]["plan_sha256"])
        manager.record(task, "validation_persisted", validation_sha256=digest(audit["validation"]), validation_passed=bool(audit["validation"]["passed"]))
        manager.record(task, "commit_persisted", marker_sha256=digest(marker), state=marker["state"], winner_schema_id=marker.get("winner_schema_id"))
        manager.snapshot_post_state(task, post, marker_sha256=digest(marker), plan_sha256=audit["plan"]["plan_sha256"], validation_sha256=digest(audit["validation"]))
        manager.record(task, "next_task_authorized", post_state_sha256=digest(post))
        records.append({"task_id": task, "pre_state_sha256": digest(pre), "post_state_sha256": digest(post),
                        "marker_sha256": digest(marker), "validation_sha256": digest(audit["validation"])})
        dynamic = post
    prefix = manager.reconcile(ledger_reconciled=True, fixed_current_state=fixed)
    expected = state["copromem_dynamic"]
    if (prefix["completed_task_count"] != 2 or prefix["next_task_id"] != NEXT["task_id"]
            or digest(dynamic) != expected["restored_semantic_state_sha256"]):
        raise RuntimeError("recovered CoProMem Dynamic prefix differs from the published custody state")
    return {"records": records, "next_task_id": prefix["next_task_id"], "semantic_state_sha256": digest(dynamic)}


def recover(run: pathlib.Path) -> None:
    _configure(run)
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    if file_sha256(run / "manifest.json") != (run / "manifest.sha256").read_text(encoding="utf-8").strip():
        raise RuntimeError("recovery manifest hash mismatch")
    identity = _identity(manifest)
    import_real_prefix(target_run=run, source_run=SOURCE_RUN, expected_manifest_sha256=SOURCE_MANIFEST_SHA256,
                       successor_identity=identity, recovery_bindings={"next": NEXT, "manifest_sha256": file_sha256(run / "manifest.json")})
    state = assemble(imported_root=run, source_run=SOURCE_RUN, forensic_json=FORENSIC,
                     successor_identity=identity, historical_exposure=HISTORICAL_EXPOSURE,
                     expected_envelope_inventory_sha256=None)
    publish(root=run, state=state)
    admitted = admit(marker_root=run, expected_source_identity=identity, expected_manifest_sha256=SOURCE_MANIFEST_SHA256)
    if admitted.next != NEXT:
        raise RuntimeError("published recovery marker does not admit the exact next trajectory")
    source_rows = validate_real_prefix(source_run=SOURCE_RUN, expected_manifest_sha256=SOURCE_MANIFEST_SHA256)
    ledger = AppendOnlyLedger(run / "ledger.jsonl", base.HARD_CAP_USD, manifest["budget"]["call_limits"])
    ledger.reserve("historical-construction-carry", HISTORICAL_EXPOSURE, {"role": "historical_carry_forward"})
    ledger.settle("historical-construction-carry", HISTORICAL_EXPOSURE, {"role": "historical_carry_forward"})
    imported = _import_scored_prefix(run, source_rows)
    retrievals = _copy_retrievals(run, source_rows)
    reme = _copy_reme_chain(run)
    rows = reconcile_artifacts(run / "artifacts", expected_tasks=manifest["evaluation"]["task_ids"],
                               expected_seeds=manifest["evaluation"]["seeds"], registered_arms=manifest["arms"])
    accounting = reconcile_ledger(run / "ledger.jsonl", historical_expected_usd=HISTORICAL_EXPOSURE, registered_arms=manifest["arms"])
    if len(rows) != 20 or accounting.unresolved_reservation_ids:
        raise RuntimeError("recovery import has an invalid scored prefix or unresolved ledger reservation")
    copro = _recover_copromem_prefix(run, manifest, state)
    record = {"version": "v6.2-evaluation-005-execution-prefix-v1", "recovery_state_sha256": state["recovery_state_sha256"],
              "imported": imported, "retrievals": retrievals, "reme_dynamic_checkpoint_files": reme,
              "copromem_dynamic": copro, "next": admitted.next, "historical_exposure": HISTORICAL_EXPOSURE}
    record["record_sha256"] = canonical_sha256(record)
    write_json(run / PREFIX_NAME, record)
    base.summary(run, manifest, state="recovery_imported")
    base.st(run, "recovery_imported", manifest_sha256=file_sha256(run / "manifest.json"), imported_completed_trajectories=20,
            next_task_id=NEXT["task_id"])


def preflight(run: pathlib.Path) -> None:
    _configure(run); _install_source_marker_validation()
    manifest = base.load(run)
    if not (run / PREFIX_NAME).is_file() or not (run / "recovery-state.json").is_file():
        raise RuntimeError("complete recovery import is required before preflight")
    identity = _identity(manifest)
    admitted = admit(marker_root=run, expected_source_identity=identity, expected_manifest_sha256=SOURCE_MANIFEST_SHA256)
    prefix = json.loads((run / PREFIX_NAME).read_text(encoding="utf-8"))
    if prefix.get("record_sha256") != canonical_sha256({key: value for key, value in prefix.items() if key != "record_sha256"}):
        raise RuntimeError("recovery execution-prefix record is invalid")
    if prefix.get("next") != admitted.next or prefix.get("copromem_dynamic", {}).get("next_task_id") != NEXT["task_id"]:
        raise RuntimeError("recovery execution prefix does not bind the exact next task")
    base.st(run, "preflight_passed", manifest_sha256=file_sha256(run / "manifest.json"), imported_completed_trajectories=20,
            next_task_id=NEXT["task_id"])


def run(run: pathlib.Path) -> None:
    _configure(run); _install_source_marker_validation()
    preflight(run)
    def final_reports(run_root: pathlib.Path, manifest: dict[str, Any], marker: dict[str, Any], marker_file_sha256: str):
        _BASE_FINAL_REPORTS(run_root, manifest, marker, marker_file_sha256)
        summary = json.loads((run_root / "live-summary.json").read_text(encoding="utf-8"))
        report = build_report(artifact_root=run_root / "artifacts", manifest=manifest, live_summary=summary)
        write_report(run_root, report)
        return report

    original = base._write_final_reports
    try:
        base._write_final_reports = final_reports
        base.run(run)
    finally:
        base._write_final_reports = original


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "freeze", "recover", "preflight", "run"])
    parser.add_argument("--run", required=True, type=pathlib.Path)
    args = parser.parse_args(); args.run = args.run.resolve()
    if not hasattr(base, "_dynamic_checkpoint_original"):
        base._dynamic_checkpoint_original = base._dynamic_checkpoint
    if args.command == "prepare":
        prepare(args.run)
    elif args.command == "freeze":
        freeze(args.run)
    elif args.command == "recover":
        recover(args.run)
    elif args.command == "preflight":
        preflight(args.run)
    else:
        run(args.run)


if __name__ == "__main__":
    main()
