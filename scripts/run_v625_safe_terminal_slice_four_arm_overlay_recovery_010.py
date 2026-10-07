#!/usr/bin/env python3
"""Immutable no-replay successor for E011's post-score summary failure.

The two scored trials in E011's incomplete Dynamic batch remain source evidence
but are not fed into an update: Dynamic requires the complete three-trial batch.
Only the preceding complete checkpoint is restored.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from copromem.contrastive_graph_v6 import digest
from copromem.experiments.reme_copromem.contrastive_v6_runner import semantic_spine_task_batch_update
from copromem.experiments.reme_copromem.recovery_import import RecoveryImportError
from copromem.experiments.reme_copromem.runner import write_json
from copromem.experiments.reme_copromem.runtime_identity_v3 import build_evaluation_identity_v3
from scripts import run_v61_exploratory_evaluation as base
from scripts import run_v625_safe_terminal_slice_100x3 as overlay
from scripts import run_v625_safe_terminal_slice_four_arm_overlay_recovery_009 as prior

PROTOCOL = "v6_2_5_safe_terminal_slice_four_arm_overlay_recovery_010"
ORIGINAL = overlay.REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_2_5_safe_terminal_slice_four_arm_overlay_001"
SOURCE = overlay.REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_2_5_safe_terminal_slice_four_arm_overlay_013_recovery"
CUSTODY = "recovery-custody.json"
ADMISSION = "recovery-admission.json"
BANK = "recovery-initial-bank"


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecoveryImportError(f"unreadable evidence: {path}") from exc
    if not isinstance(value, dict):
        raise RecoveryImportError("evidence is not a JSON object")
    return value


def sha(path: Path) -> str:
    if not path.is_file():
        raise RecoveryImportError(f"evidence missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canon(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify_ref(item: Mapping[str, Any], position: int) -> None:
    if item.get("position") != position:
        raise RecoveryImportError("recovery artifact order changed")
    identity = item.get("identity")
    artifact = load(Path(str(item.get("artifact", ""))))
    if not isinstance(identity, Mapping) or artifact.get("trajectory_id") != item.get("trajectory_id"):
        raise RecoveryImportError("recovery artifact identity mismatch")
    if (artifact.get("task_id"), artifact.get("trial_id"), artifact.get("seed")) != (
        identity.get("task_id"), identity.get("trial_id"), identity.get("seed")):
        raise RecoveryImportError("recovery artifact task identity mismatch")
    for key in ("artifact", "journal", "retrieval", "binding"):
        if sha(Path(str(item.get(key, "")))) != item.get(f"{key}_sha256"):
            raise RecoveryImportError(f"recovery artifact {key} hash mismatch")


def artifact_ref(root: Path, task: str, trial: int, seed: int, position: int) -> dict[str, Any]:
    arm = overlay.ARM
    artifact = root / "artifacts" / task / arm / f"trial-{trial}.json"
    journal = root / "journals" / f"evaluation_{arm}_{task}_trial_{trial}_seed_{seed}.execution-evidence.jsonl"
    retrieval = root / "retrievals" / task / f"{arm}-{trial}.json"
    binding = root / "retrievals" / task / f"{arm}-{trial}.binding.json"
    row = load(artifact)
    identity = {"task_id": task, "trial_id": trial, "seed": seed, "arm": arm}
    if row.get("trajectory_id") != f"evaluation:{arm}:{task}:trial={trial}:seed={seed}":
        raise RecoveryImportError("unexpected successor trajectory identity")
    return {"position": position, "trajectory_id": row["trajectory_id"], "identity": identity,
            "artifact": str(artifact.resolve()), "artifact_sha256": sha(artifact),
            "journal": str(journal.resolve()), "journal_sha256": sha(journal),
            "retrieval": str(retrieval.resolve()), "retrieval_sha256": sha(retrieval),
            "binding": str(binding.resolve()), "binding_sha256": sha(binding)}


def checkpoint_ref(task_dir: Path, expected_pre: str, position: int) -> dict[str, Any]:
    pre = load(task_dir / "01-task_pre_state_frozen.json")
    post_path = task_dir / "post-state.json"; post = load(post_path)
    records = [{"path": str(path.resolve()), "sha256": sha(path)}
               for path in sorted(task_dir.glob("[0-9][0-9]-*.json"))]
    if (pre.get("pre_state_sha256") != expected_pre or post.get("semantic_state_sha256") != digest(post.get("state"))
            or len(records) != 9):
        raise RecoveryImportError("source Dynamic checkpoint transition differs")
    return {"task_index": position, "task_id": str(post.get("task_id") or task_dir.name.split("-", 1)[-1]),
            "pre_state_sha256": expected_pre, "post_state": str(post_path.resolve()),
            "post_state_file_sha256": sha(post_path), "post_state_sha256": post["semantic_state_sha256"],
            "records": records}


def source() -> dict[str, Any]:
    """Admit E013's complete scored batch without replaying any provider call.

    E013 stopped after the three scored trials of its first new task because
    its inherited bank had a content-proven v6.1 semantic prefix plus v6.2.2
    spine schemas.  The repaired semantic-spine validator accepts precisely
    that mixed, attested representation and rejects raw or v6.1-only banks.
    """
    previous = prior.source()
    manifest = load(SOURCE / "manifest.json")
    if sha(SOURCE / "manifest.json") != (SOURCE / "manifest.sha256").read_text().strip():
        raise RecoveryImportError("E013 manifest hash mismatch")
    if manifest.get("protocol") != prior.PROTOCOL:
        raise RecoveryImportError("wrong E013 protocol")
    custody = load(SOURCE / CUSTODY)
    recorded = custody.pop("custody_sha256", None)
    if recorded != canon(custody):
        raise RecoveryImportError("E013 custody hash mismatch")
    if custody.get("artifacts") != previous["prefix"] or custody.get("restored_dynamic_state_sha256") != previous["state"]["semantic_state_sha256"]:
        raise RecoveryImportError("E013 predecessor custody differs")
    tasks = list(manifest.get("evaluation", {}).get("task_ids", ()))
    seeds = list(manifest.get("evaluation", {}).get("seeds", ()))
    if tasks != previous["remaining"] or seeds != previous["seeds"]:
        raise RecoveryImportError("E013 schedule differs from admitted predecessor")
    task = tasks[0]
    local = [artifact_ref(SOURCE, task, trial, seed, len(previous["prefix"]) + trial)
             for trial, seed in enumerate(seeds, 1)]
    observed = {(load(path).get("task_id"), int(load(path).get("trial_id")))
                for path in (SOURCE / "artifacts").glob("**/trial-*.json")}
    if observed != {(task, 1), (task, 2), (task, 3)}:
        raise RecoveryImportError("E013 completed artifact grid differs")
    checkpoint = SOURCE / "copromem-dynamic-checkpoints" / "tasks" / f"0001-{task}"
    pre = load(checkpoint / "01-task_pre_state_frozen.json")
    snapshot = load(checkpoint / "pre-state.json")
    prior_hash = previous["state"]["semantic_state_sha256"]
    if pre.get("pre_state_sha256") != prior_hash or snapshot.get("semantic_state_sha256") != prior_hash or digest(snapshot.get("state")) != prior_hash:
        raise RecoveryImportError("E013 frozen pre-state differs from predecessor")
    artifacts = [load(Path(str(item["artifact"]))) for item in local]
    evidence_paths = [str(item.get("execution_evidence_path", "")) for item in artifacts]
    if len(artifacts) != 3 or any(not value for value in evidence_paths):
        raise RecoveryImportError("E013 batch evidence is incomplete")
    registry = load(base.REG)
    post, marker, audit = semantic_spine_task_batch_update(
        artifacts=artifacts, registry=registry, pre_state=snapshot["state"],
        evidence_paths=evidence_paths, run_root=SOURCE)
    if audit.get("pre_state_sha256") != prior_hash or audit.get("post_state_sha256") != digest(post):
        raise RecoveryImportError("E013 reconstructed update identity differs")
    records = [{"path": str(path.resolve()), "sha256": sha(path)} for path in sorted(checkpoint.glob("*.json"))]
    reconstructed = {
        "task_id": task, "source_checkpoint_directory": str(checkpoint.resolve()),
        "pre_state_sha256": prior_hash, "post_state_sha256": digest(post),
        "marker_sha256": digest(marker), "audit_sha256": digest(audit),
        "artifact_trajectory_ids": [item["trajectory_id"] for item in local],
        "evidence_paths": evidence_paths, "source_checkpoint_records": records,
        "validator_compatibility": audit.get("pre_state_compatibility"),
    }
    ledger_path = SOURCE / "ledger.jsonl"
    ledger = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line]
    reserved = {str(row.get("id")) for row in ledger if row.get("event") == "reserve"}
    settled = {str(row.get("id")) for row in ledger if row.get("event") == "settle"}
    if not reserved or reserved != settled:
        raise RecoveryImportError("E013 ledger has unresolved reservation")
    own = sum((Decimal(str(row["usd"])) for row in ledger if row.get("event") == "settle" and row.get("role") != "historical_carry_forward"), Decimal(0))
    history = Decimal(str(previous["history"])) + own
    chains = list(previous["chains"]) + [{
        "task_index": len(previous["chains"]) + 1, "task_id": task,
        "pre_state_sha256": prior_hash, "post_state_sha256": digest(post),
        "reconstructed_from_immutable_scored_batch": True,
        "source_checkpoint_records": records,
    }]
    remaining = tasks[1:]
    if len(previous["prefix"]) + len(local) != 87 or len(remaining) != 71:
        raise RecoveryImportError("E014 successor schedule is not exactly 300 trajectories")
    return {"tasks": previous["tasks"], "seeds": seeds, "prefix": previous["prefix"] + local, "sidecar": [],
            "chains": chains, "state": {"state": post, "semantic_state_sha256": digest(post)},
            "remaining": remaining, "history": str(history), "source_ledger_sha256": sha(ledger_path),
            "source_ledger_rows": len(ledger), "reconstructed_update": reconstructed,
            "failure": {"task_id": task, "reason": "E013 stopped after complete scored batch before its semantic-spine commit; E014 reconstructs the update from immutable E013 evidence", "provider_calls_replayed": False}}
def configure(run: Path, src: Mapping[str, Any]) -> None:
    overlay.configure(run)
    state = dict(src["state"]["state"])
    base.COPRO = run / BANK; base.FROZEN_TASK_IDS = list(src["remaining"]); base.ARMS = [overlay.ARM]
    base.COPRO_DYNAMIC_ARM = overlay.ARM; base.COPRO_FIXED_ARM = "copromem_v6_2_5_fixed_unregistered"
    base.EVALUATION_SEEDS = tuple(overlay.TRIAL_SEEDS); base.CALL_LIMITS = {**overlay.CALL_LIMITS, "executor": len(src["remaining"]) * 3 * 30}
    base.HARD_CAP_USD = overlay.HARD_CAP_USD; base.HISTORICAL_EXPOSURE = float(Decimal(str(src["history"])))
    base.PROTOCOL = PROTOCOL; base.PREEXISTING_RUN_FILES = {overlay.ALLOCATION_NAME, "public-operation-intents.json", "external-admission-receipt.json", CUSTODY, BANK, "runtime-identity.binding.json"}
    base.identities = lambda: (load(base.CONSTRUCTION / "FINAL_CONSTRUCTION_REPORT.json"), {"state_sha256": digest(state)})


def prepare(run: Path) -> None:
    src = source()
    if run.exists() and any(run.iterdir()): raise RecoveryImportError("successor target must be empty")
    run.mkdir(parents=True)
    for name in (overlay.ALLOCATION_NAME, "public-operation-intents.json", "external-admission-receipt.json"):
        shutil.copyfile(ORIGINAL / name, run / name)
    custody = {"version": PROTOCOL, "original_run": str(ORIGINAL.resolve()), "source_run": str(SOURCE.resolve()),
               "source_manifest_sha256": sha(SOURCE / "manifest.json"), "source_runtime_identity_sha256": load(SOURCE / "runtime-identity.json")["runtime_identity_sha256"],
               "source_ledger_sha256": src["source_ledger_sha256"], "source_ledger_rows": src["source_ledger_rows"],
               "historical_settled_exposure_usd": src["history"], "imported_trajectory_count": len(src["prefix"]),
               "preserved_nonlearning_scored_trajectory_count": len(src["sidecar"]), "artifacts": src["prefix"], "preserved_nonlearning_scored_artifacts": src["sidecar"],
               "dynamic_checkpoint_chains": src["chains"], "restored_dynamic_state_sha256": src["state"]["semantic_state_sha256"],
               "excluded_incomplete_batch": src["failure"], "reconstructed_update": src["reconstructed_update"], "next_task_id": src["remaining"][0], "remaining_task_count": len(src["remaining"]),
               "composite_expected_learning_trajectories": len(src["prefix"]) + len(src["remaining"]) * 3,
               "composite_expected_scored_trajectories": len(src["prefix"]) + len(src["sidecar"]) + len(src["remaining"]) * 3,
               "source_immutable": True, "provider_calls_replayed": False}
    custody["custody_sha256"] = canon(custody); write_json(run / CUSTODY, custody)
    bank = run / BANK; bank.mkdir(); write_json(bank / "fixed-bank.json", src["state"]["state"]); write_json(bank / "semantic-admission-gate.json", {"state_sha256": custody["restored_dynamic_state_sha256"]})
    configure(run, src); base.prepare(run)
    # ``base.prepare`` deliberately knows nothing about v6.2.5's semantic
    # method policy.  Recovery must materialize the same identity inputs as
    # the overlay before constructing its own v3 runtime identity.
    template = load(run / "template.json")
    allocation = (run / overlay.ALLOCATION_NAME).read_bytes()
    audit = overlay._audit(run)
    template["method"] = {
        "copromem": overlay.POLICY_VERSION,
        "retrieval": "admitted named-app action-and-object safe terminal slice; v6.2.2 semantic safety guards retained",
        "analysis_scope": "CoProMem v6.2.5 Dynamic overlay no-replay successor; source evidence and costs remain separate",
    }
    template["method_policy"] = overlay.frozen_policy()
    template["execution"]["provider_only"] = overlay.CHAT_PROVIDER
    template["evaluation"].update({"allocation_audit_sha256": hashlib.sha256(allocation).hexdigest(),
                                   "trial_count": len(overlay.TRIAL_SEEDS), "phase": str(audit["phase"]),
                                   "overlay_four_arm_allocation_sha256": audit["four_arm_allocation_sha256"]})
    template["external_admission"] = {
        "mode": "admitted_retrieval", "receipt_file_sha256": sha(run / "external-admission-receipt.json"),
        "receipt_sha256": load(run / "external-admission-receipt.json")["receipt_sha256"],
    }
    template["runtime_identity_version"] = overlay.RUNTIME_IDENTITY_V3
    template.update({"protocol": PROTOCOL, "recovery": {"custody_file_sha256": sha(run / CUSTODY), "imported_trajectory_count": len(src["prefix"]), "excluded_incomplete_batch": src["failure"], "reconstructed_update": src["reconstructed_update"], "next_task_id": src["remaining"][0]}})
    template["evaluation"].update({"task_ids": list(src["remaining"]), "task_count": len(src["remaining"]), "expected_trajectories": len(src["remaining"]) * 3, "recovery_imported_trajectories": len(src["prefix"]), "composite_expected_scored_trajectories": custody["composite_expected_scored_trajectories"]})
    template["banks"]["copromem_sha256"] = custody["restored_dynamic_state_sha256"]
    template["budget"].update({"historical_settled_exposure": float(Decimal(src["history"]))}); runtime, inputs = build_evaluation_identity_v3(root=overlay.ROOT, manifest=template)
    write_json(run / "runtime-identity.json", runtime)
    template["runtime_identity_inputs"] = inputs; template["runtime_identity_sha256"] = runtime["runtime_identity_sha256"]; template["runtime_identity_file_sha256"] = sha(run / "runtime-identity.json"); write_json(run / "template.json", template)
    # This sidecar is a production dispatch prerequisite.  Write it after the
    # final template materialization and prove its two identity domains are
    # exact before freeze can proceed.
    binding = run / "runtime-identity.binding.json"
    expected_binding = {"runtime_identity_sha256": runtime["runtime_identity_sha256"], "runtime_identity_record_sha256": sha(run / "runtime-identity.json")}
    write_json(binding, expected_binding)
    if load(binding) != expected_binding:
        raise RecoveryImportError("runtime identity binding was not persisted")


def verify(run: Path) -> dict[str, Any]:
    src = source(); custody = load(run / CUSTODY); recorded = custody.pop("custody_sha256", None)
    if recorded != canon(custody) or custody.get("artifacts") != src["prefix"] or custody.get("preserved_nonlearning_scored_artifacts") != src["sidecar"] or custody.get("excluded_incomplete_batch") != src["failure"]:
        raise RecoveryImportError("recovery custody differs from immutable E011 source")
    if digest(load(run / BANK / "fixed-bank.json")) != src["state"]["semantic_state_sha256"]: raise RecoveryImportError("successor bank mismatch")
    return src


def freeze(run: Path) -> None: src = verify(run); configure(run, src); base.freeze(run)
def preflight(run: Path) -> None:
    src = verify(run); configure(run, src); manifest = base.load(run)
    if manifest["evaluation"]["task_ids"] != src["remaining"]: raise RecoveryImportError("successor schedule mismatch")
    route = overlay.verify_locked_chat_route_available(); write_json(run / "provider-route-preflight.json", route)
    write_json(run / ADMISSION, {"version": PROTOCOL, "custody_file_sha256": sha(run / CUSTODY), "source_ledger_sha256": src["source_ledger_sha256"], "imported_trajectory_count": len(src["prefix"]), "preserved_nonlearning_scored_trajectory_count": len(src["sidecar"]), "next_task_id": src["remaining"][0], "provider_calls_replayed": False})
    base.st(run, "preflight_passed", imported_completed_trajectories=len(src["prefix"]), next_task_id=src["remaining"][0])
def run(run: Path) -> None: src = verify(run); configure(run, src); preflight(run); base.run(run)
def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("prepare", "freeze", "preflight", "run")); parser.add_argument("--run", required=True, type=Path); args = parser.parse_args()
    {"prepare": prepare, "freeze": freeze, "preflight": preflight, "run": run}[args.command](args.run.resolve())
if __name__ == "__main__": main()



