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
from copromem.experiments.reme_copromem.recovery_import import RecoveryImportError
from copromem.experiments.reme_copromem.runner import write_json
from copromem.experiments.reme_copromem.runtime_identity_v3 import build_evaluation_identity_v3
from scripts import run_v61_exploratory_evaluation as base
from scripts import run_v625_safe_terminal_slice_100x3 as overlay

PROTOCOL = "v6_2_5_safe_terminal_slice_four_arm_overlay_recovery_008"
ORIGINAL = overlay.REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_2_5_safe_terminal_slice_four_arm_overlay_001"
SOURCE = overlay.REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_2_5_safe_terminal_slice_four_arm_overlay_011_recovery"
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
    """Read-only admission of E011, excluding its incomplete task as a whole."""
    original = load(ORIGINAL / "manifest.json")
    if sha(ORIGINAL / "manifest.json") != (ORIGINAL / "manifest.sha256").read_text().strip():
        raise RecoveryImportError("original manifest hash mismatch")
    tasks = list(original.get("evaluation", {}).get("task_ids", ())); seeds = list(original.get("evaluation", {}).get("seeds", ()))
    if original.get("protocol") != overlay.PROTOCOL or len(tasks) != 100 or seeds != list(overlay.TRIAL_SEEDS):
        raise RecoveryImportError("wrong original schedule")
    manifest = load(SOURCE / "manifest.json")
    if sha(SOURCE / "manifest.json") != (SOURCE / "manifest.sha256").read_text().strip():
        raise RecoveryImportError("E011 manifest hash mismatch")
    if manifest.get("protocol") != "v6_2_5_safe_terminal_slice_four_arm_overlay_recovery_007":
        raise RecoveryImportError("E011 protocol mismatch")
    custody = load(SOURCE / CUSTODY); recorded = custody.pop("custody_sha256", None)
    if recorded != canon(custody):
        raise RecoveryImportError("E011 custody hash mismatch")
    inherited = list(custody.get("artifacts", ())); inherited_sidecar = list(custody.get("preserved_nonlearning_scored_artifacts", ()))
    if len(inherited) != 41 or len(inherited_sidecar) != 2:
        raise RecoveryImportError("E011 inherited inventory differs")
    for pos, item in enumerate(inherited + inherited_sidecar, 1): verify_ref(item, pos)
    source_tasks = list(manifest["evaluation"]["task_ids"])
    if source_tasks != tasks[tasks.index("3d9a636_2"):]:
        raise RecoveryImportError("E011 task schedule differs")
    complete_tasks = source_tasks[:8]; incomplete_task = source_tasks[8]
    if incomplete_task != "6b6ca61_2" or source_tasks[9] != "6f4b9a5_2":
        raise RecoveryImportError("E011 continuation boundary differs")
    local: list[dict[str, Any]] = []
    for task in complete_tasks:
        for trial, seed in enumerate(seeds, 1): local.append(artifact_ref(SOURCE, task, trial, seed, len(inherited) + len(local) + 1))
    partial = [artifact_ref(SOURCE, incomplete_task, trial, seeds[trial - 1], len(inherited) + len(local) + trial)
               for trial in (1, 2)]
    observed = {(str(load(path)["task_id"]), int(load(path)["trial_id"])) for path in (SOURCE / "artifacts").glob("**/trial-*.json")}
    expected = {(task, trial) for task in complete_tasks for trial in (1, 2, 3)} | {(incomplete_task, 1), (incomplete_task, 2)}
    if observed != expected:
        raise RecoveryImportError("E011 local artifact grid differs")
    old_chains = list(custody.get("dynamic_checkpoint_chains", ()))
    if len(old_chains) != 10:
        raise RecoveryImportError("E011 inherited Dynamic checkpoint count differs")
    prior = str(old_chains[-1].get("post_state_sha256", ""))
    if not prior:
        raise RecoveryImportError("E011 inherited Dynamic state absent")
    chains = list(old_chains)
    for index, task in enumerate(complete_tasks, 1):
        item = checkpoint_ref(SOURCE / "copromem-dynamic-checkpoints" / "tasks" / f"{index:04d}-{task}", prior, len(chains) + 1)
        chains.append(item); prior = str(item["post_state_sha256"])
    failed_dir = SOURCE / "copromem-dynamic-checkpoints" / "tasks" / f"0009-{incomplete_task}"
    if not (failed_dir / "01-task_pre_state_frozen.json").is_file() or (failed_dir / "post-state.json").exists():
        raise RecoveryImportError("E011 incomplete task checkpoint differs")
    if load(failed_dir / "01-task_pre_state_frozen.json").get("pre_state_sha256") != prior:
        raise RecoveryImportError("E011 incomplete task does not begin at restored state")
    ledger_path = SOURCE / "ledger.jsonl"; ledger = [json.loads(line) for line in ledger_path.read_text().splitlines() if line]
    reserved = {str(row.get("id")) for row in ledger if row.get("event") == "reserve"}; settled = {str(row.get("id")) for row in ledger if row.get("event") == "settle"}
    if not reserved or reserved != settled:
        raise RecoveryImportError("E011 ledger has unresolved reservation")
    progress_path = SOURCE / "progress.jsonl"; progress = [json.loads(line) for line in progress_path.read_text().splitlines() if line]
    failures = [row for row in progress if row.get("event") == "runner_failed"]
    if len(failures) != 1 or failures[0].get("failure_class") != "LedgerReconciliationError":
        raise RecoveryImportError("E011 terminal failure differs")
    own_new = sum((Decimal(str(row["usd"])) for row in ledger if row.get("event") == "settle" and row.get("role") != "historical_carry_forward"), Decimal(0))
    history = Decimal(str(custody["historical_settled_exposure_usd"])) + own_new
    final_post = Path(str(chains[-1]["post_state"])); final_state = load(final_post)
    if digest(final_state.get("state")) != chains[-1]["post_state_sha256"]:
        raise RecoveryImportError("E011 restored bank state differs")
    return {"tasks": tasks, "seeds": seeds, "prefix": inherited + local, "sidecar": inherited_sidecar + partial,
            "chains": chains, "state": {"state": final_state["state"], "semantic_state_sha256": chains[-1]["post_state_sha256"]},
            "remaining": source_tasks[9:], "history": str(history), "source_ledger_sha256": sha(ledger_path),
            "source_ledger_rows": len(ledger), "failure": {"task_id": incomplete_task, "arm": overlay.ARM,
            "scored_trials_preserved": [1, 2], "unrun_trial": 3, "checkpoint_directory": str(failed_dir.resolve()),
            "checkpoint_pre_state_sha256": prior, "ledger": str(ledger_path.resolve()), "ledger_sha256": sha(ledger_path),
            "progress": str(progress_path.resolve()), "progress_sha256": sha(progress_path),
            "reason": "post-score live-summary accounting failure after two scored trials; entire incomplete Dynamic batch excluded to prevent replay", "provider_calls_replayed": False}}

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
               "dynamic_checkpoint_chains": src["chains"], "restored_dynamic_state_sha256": src["chains"][-1]["post_state_sha256"],
               "excluded_incomplete_batch": src["failure"], "next_task_id": src["remaining"][0], "remaining_task_count": len(src["remaining"]),
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
    template.update({"protocol": PROTOCOL, "recovery": {"custody_file_sha256": sha(run / CUSTODY), "imported_trajectory_count": len(src["prefix"]), "excluded_incomplete_batch": src["failure"], "next_task_id": src["remaining"][0]}})
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
    if digest(load(run / BANK / "fixed-bank.json")) != src["chains"][-1]["post_state_sha256"]: raise RecoveryImportError("successor bank mismatch")
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
