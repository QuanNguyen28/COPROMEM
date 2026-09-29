#!/usr/bin/env python3
"""Evaluation 004: hash-verified, non-recharging recovery of Evaluation 002.

This is an infrastructure successor only.  It imports the durable ten-item
prefix as evidence, reconstructs the one uncommitted CoProMem boundary offline,
and charges only calls dispatched after the successor starts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from decimal import Decimal
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from copromem.experiments.reme_copromem.contrastive_v6_runner import semantic_task_batch_update
from copromem.experiments.reme_copromem.copromem_dynamic_checkpoint import CoProMemDynamicCheckpointManager
from copromem.experiments.reme_copromem.live_summary import build_live_summary, reconcile_artifacts, reconcile_ledger, write_live_summary
from copromem.experiments.reme_copromem.recovery_import import copy_evidence_file, file_sha256, import_scored_artifact
from copromem.experiments.reme_copromem.runner import AppendOnlyLedger, write_json
from scripts import run_v61_exploratory_evaluation as base
from scripts import run_v62_task_conditioned_medium_evaluation_003 as prior
from scripts import run_v62_task_conditioned_medium_evaluation_002 as predecessor

PROTOCOL = "v6_2_task_conditioned_evaluation_004_recovery"
SOURCE_RUN = prior.SOURCE_RUN
SOURCE_MANIFEST_SHA256 = prior.SOURCE_MANIFEST_SHA256
HISTORICAL_EXPOSURE = 2.435839694
ALLOCATION_NAME = "allocation-audit.json"


def _canonical(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def _configure(run: pathlib.Path) -> None:
    predecessor._configure(run)
    base.PROTOCOL = PROTOCOL
    base.HISTORICAL_EXPOSURE = HISTORICAL_EXPOSURE
    base.PREEXISTING_RUN_FILES = {ALLOCATION_NAME, "custody-audit.json", "recovery-amendment.json", "recovery-import-audit.json"}
    base.summary = summary
    base._dynamic_checkpoint = _dynamic_checkpoint


def _source_manifest() -> dict[str, Any]:
    return prior._source_manifest()


def _prepare(run: pathlib.Path) -> None:
    source = _source_manifest()
    run.mkdir(parents=True, exist_ok=True)
    for name in (ALLOCATION_NAME, "custody-audit.json"):
        copy_evidence_file(SOURCE_RUN / name, run / name)
    _configure(run)
    amendment = {
        "version": "v6.2-evaluation-004-infrastructure-recovery-v1",
        "source_protocol": predecessor.PROTOCOL,
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "source_status_sha256": file_sha256(SOURCE_RUN / "runner-status.json"),
        "source_ledger_sha256": file_sha256(SOURCE_RUN / "ledger.jsonl"),
        "scientific_protocol_unchanged": True,
        "source_task_ids": source["evaluation"]["task_ids"], "source_arms": source["arms"],
        "import_rule": "ten hash-verified scored artifacts count once; their provider settlements remain historical and are never charged as successor arm costs",
        "recovery_rule": "reconstruct only the uncommitted first CoProMem Dynamic boundary offline from exactly the two durable source artifacts",
    }
    write_json(run / "recovery-amendment.json", amendment)
    base.prepare(run)
    template = json.loads((run / "template.json").read_text(encoding="utf-8"))
    template.update({"protocol": PROTOCOL, "recovery_amendment_sha256": file_sha256(run / "recovery-amendment.json"),
                     "predecessor_evaluation_002": {"manifest_sha256": SOURCE_MANIFEST_SHA256,
                        "completed_prefix_expected": 10, "imported_scientific_evidence": True,
                        "source_total_settled_exposure": HISTORICAL_EXPOSURE,
                        "predecessor_provider_calls_not_recharged": True}})
    template["budget"]["historical_settled_exposure"] = HISTORICAL_EXPOSURE
    write_json(run / "template.json", template)


def _source_settlement_ids() -> set[str]:
    rows = [json.loads(line) for line in (SOURCE_RUN / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    settled = {str(row["id"]) for row in rows if row.get("event") == "settle" and str(row.get("role", "")).startswith(("reme_lifecycle:reme-dynamic", "reme_embedding:reme-dynamic"))}
    if not settled:
        raise RuntimeError("source ReMe Dynamic settlements are absent")
    return settled


def _dynamic_checkpoint(run: pathlib.Path, manifest: dict[str, Any], dynamic: Any, verifier: Any):
    manager = base._dynamic_checkpoint_original(run, manifest, dynamic, verifier) if hasattr(base, "_dynamic_checkpoint_original") else None
    # ``base._dynamic_checkpoint`` is patched by _configure; retain its original once.
    if manager is not None:
        return manager
    raise RuntimeError("original dynamic checkpoint factory was not captured")


def _summary_payload(run: pathlib.Path, manifest: dict[str, Any], *, state: str, final: bool = False) -> dict[str, Any]:
    out = dict(build_live_summary(ledger_path=run / "ledger.jsonl", artifact_root=run / "artifacts",
        expected_tasks=manifest["evaluation"]["task_ids"], expected_seeds=manifest["evaluation"]["seeds"],
        historical_expected_usd=HISTORICAL_EXPOSURE, state=state, final=final,
        expected_trajectories=manifest["evaluation"]["expected_trajectories"], registered_arms=manifest["arms"]))
    imported = 0
    for row in reconcile_artifacts(run / "artifacts", expected_tasks=manifest["evaluation"]["task_ids"],
                                   expected_seeds=manifest["evaluation"]["seeds"], registered_arms=manifest["arms"]):
        if isinstance(row.get("carried_completed_from"), dict): imported += 1
    out.update({"imported_completed_trajectories": imported, "newly_completed_trajectories": out["completed"] - imported,
                "historical_infrastructure_exposure": HISTORICAL_EXPOSURE,
                "new_evaluation_cost": out["settled_evaluation_cost"],
                "combined_ledger_exposure": out["total_ledger_exposure"]})
    return out


def summary(run: pathlib.Path, manifest: dict[str, Any], *, state: str = "running", final: bool = False) -> None:
    write_live_summary(run / "live-summary.json", _summary_payload(run, manifest, state=state, final=final))


def _recover_copromem_boundary(run: pathlib.Path, manifest: dict[str, Any], imported: list[dict[str, Any]]) -> dict[str, Any]:
    fixed = json.loads((base.COPRO / "fixed-bank.json").read_text(encoding="utf-8"))
    registry = json.loads(base.REG.read_text(encoding="utf-8")); dynamic = json.loads(json.dumps(fixed, sort_keys=True))
    manager = CoProMemDynamicCheckpointManager(root=run / "copromem-dynamic-checkpoints",
        manifest_sha256=file_sha256(run / "manifest.json"), source_identity_sha256=base.digest({"git_commit": manifest["git_commit"]}),
        registry_sha256=registry["registry_sha256"], ordered_tasks=manifest["evaluation"]["task_ids"],
        fixed_initial_state=fixed, dynamic_initial_state=dynamic)
    task = str(manifest["evaluation"]["task_ids"][0]); pre = json.loads(json.dumps(dynamic, sort_keys=True))
    manager.freeze_task_pre_state(task, pre)
    artifacts = [json.loads((run / "artifacts" / task / base.COPRO_DYNAMIC_ARM / f"trial-{trial}.json").read_text(encoding="utf-8")) for trial in (1, 2)]
    retrievals = [json.loads((run / "retrievals" / task / f"{base.COPRO_DYNAMIC_ARM}-{trial}.json").read_text(encoding="utf-8")) for trial in (1, 2)]
    manager.record(task, "retrievals_materialized", task_query_hashes=[str(r["task_query"]["query_sha256"]) for r in retrievals], retrieval_hashes=[base.digest(r) for r in retrievals])
    manager.record(task, "trajectories_complete", artifact_hashes=[base.digest(a) for a in artifacts], scorer_evidence_hashes=[str(a["official_scorer_evidence"]["sha256"]) for a in artifacts])
    post, marker, audit = semantic_task_batch_update(artifacts=artifacts, registry=registry, pre_state=pre,
        evidence_paths=[str(a["execution_evidence_path"]) for a in artifacts], run_root=run)
    manager.record(task, "batch_ready", semantic_projection_hashes=[r["semantic_projection_sha256"] for r in audit["semantic_graph_audits"]])
    manager.record(task, "semantic_plan_persisted", plan_sha256=audit["plan"]["plan_sha256"])
    manager.record(task, "validation_persisted", validation_sha256=base.digest(audit["validation"]), validation_passed=bool(audit["validation"]["passed"]))
    manager.record(task, "commit_persisted", marker_sha256=base.digest(marker), state=marker["state"], winner_schema_id=marker.get("winner_schema_id"))
    manager.snapshot_post_state(task, post, marker_sha256=base.digest(marker), plan_sha256=audit["plan"]["plan_sha256"], validation_sha256=base.digest(audit["validation"]))
    manager.record(task, "next_task_authorized", post_state_sha256=base.digest(post))
    prefix = manager.reconcile(ledger_reconciled=True, fixed_current_state=fixed)
    if prefix["completed_task_count"] != 1 or prefix["next_task_id"] != manifest["evaluation"]["task_ids"][1]:
        raise RuntimeError("offline CoProMem recovery did not authorize exactly one boundary")
    return {"task_id": task, "exact_source_dynamic_artifacts": [i for i in imported if i["trajectory_id"].startswith(f"evaluation:{base.COPRO_DYNAMIC_ARM}:{task}:")],
        "pre_state_sha256": base.digest(pre), "post_state_sha256": base.digest(post), "marker_sha256": base.digest(marker),
        "plan_sha256": audit["plan"]["plan_sha256"], "validation_sha256": base.digest(audit["validation"]),
        "validation_passed": bool(audit["validation"]["passed"]), "next_task_id": prefix["next_task_id"]}


def recover(run: pathlib.Path) -> None:
    _configure(run)
    if (run / "recovery-import-audit.json").exists():
        raise RuntimeError("recovery import already exists")
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    if file_sha256(run / "manifest.json") != (run / "manifest.sha256").read_text(encoding="utf-8").strip():
        raise RuntimeError("recovery manifest hash mismatch")
    source = _source_manifest()
    if manifest["evaluation"]["task_ids"] != source["evaluation"]["task_ids"] or manifest["arms"] != source["arms"]:
        raise RuntimeError("recovery changes frozen allocation")
    ledger = AppendOnlyLedger(run / "ledger.jsonl", base.HARD_CAP_USD, manifest["budget"]["call_limits"])
    ledger.reserve("historical-construction-carry", HISTORICAL_EXPOSURE, {"role": "historical_carry_forward"})
    ledger.settle("historical-construction-carry", HISTORICAL_EXPOSURE, {"role": "historical_carry_forward"})
    imported=[]
    for path in prior._source_artifact_paths(source):
        imported.append(import_scored_artifact(source_artifact=path, source_run=SOURCE_RUN,
            target_artifact=run / "artifacts" / path.relative_to(SOURCE_RUN / "artifacts"), target_run=run,
            source_manifest_sha256=SOURCE_MANIFEST_SHA256))
    retrievals = prior._copy_retrievals(run, source)
    chain = prior._copy_reme_dynamic_chain(run)
    rows = reconcile_artifacts(run / "artifacts", expected_tasks=manifest["evaluation"]["task_ids"], expected_seeds=manifest["evaluation"]["seeds"], registered_arms=manifest["arms"])
    accounting = reconcile_ledger(run / "ledger.jsonl", historical_expected_usd=HISTORICAL_EXPOSURE, registered_arms=manifest["arms"])
    if len(rows) != 10 or accounting.unresolved_reservation_ids:
        raise RuntimeError("imported prefix is incomplete or ledger unresolved")
    copro = _recover_copromem_boundary(run, manifest, imported)
    audit = {"version": "v6.2-evaluation-004-import-v1", "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "source_ledger_sha256": file_sha256(SOURCE_RUN / "ledger.jsonl"), "source_dynamic_settlement_ids": sorted(_source_settlement_ids()),
        "historical_carried_exposure": HISTORICAL_EXPOSURE, "imported": imported, "retrievals": retrievals,
        "reme_dynamic_checkpoint_files": chain, "copromem_offline_task_boundary": copro,
        "no_source_provider_calls_recharged_to_successor": True, "scientific_protocol_unchanged": True}
    audit["audit_sha256"] = _canonical(audit); write_json(run / "recovery-import-audit.json", audit)
    summary(run, manifest, state="recovery_imported")
    base.st(run, "recovery_imported", manifest_sha256=file_sha256(run / "manifest.json"), imported_completed_trajectories=10, next_task_id=copro["next_task_id"])


def _install_source_marker_validation(run: pathlib.Path) -> None:
    """Patch only the target runner's marker validator for immutable prefix IDs."""
    original = base._validate_marker_settlements
    source_ids = _source_settlement_ids()
    def validator(path: pathlib.Path, marker: dict[str, Any]) -> None:
        if int(marker.get("ordered_update_index", 0)) <= 2:
            if not set(map(str, marker.get("newly_settled_lifecycle_or_embedding_ids", []))).issubset(source_ids):
                raise RuntimeError("imported ReMe marker has an unbound source settlement")
            return
        original(path, marker)
    base._validate_marker_settlements = validator


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=["prepare", "freeze", "recover", "preflight", "run"]); parser.add_argument("--run", type=pathlib.Path, required=True)
    args = parser.parse_args(); args.run = args.run.resolve()
    if not hasattr(base, "_dynamic_checkpoint_original"):
        base._dynamic_checkpoint_original = base._dynamic_checkpoint
    _install_source_marker_validation(args.run)
    if args.command == "prepare": _prepare(args.run); return
    _configure(args.run)
    if args.command == "freeze": base.freeze(args.run)
    elif args.command == "recover": recover(args.run)
    elif args.command == "preflight":
        base.load(args.run)
        if not (args.run / "recovery-import-audit.json").is_file(): raise RuntimeError("recovery import is required before preflight")
        base.st(args.run, "preflight_passed", manifest_sha256=file_sha256(args.run / "manifest.json"))
    else: base.run(args.run)


if __name__ == "__main__": main()
