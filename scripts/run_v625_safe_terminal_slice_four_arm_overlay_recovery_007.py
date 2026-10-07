#!/usr/bin/env python3
"""Immutable no-replay successor for E010's provider-interrupted Dynamic task.

The first two scored trials of the failed batch remain source evidence, but
are never fed into the Dynamic update: a batch update requires all three
officially scored trials.  Only the preceding complete checkpoint is restored.
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

PROTOCOL = "v6_2_5_safe_terminal_slice_four_arm_overlay_recovery_007"
ORIGINAL = overlay.REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_2_5_safe_terminal_slice_four_arm_overlay_001"
SOURCE = overlay.REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_2_5_safe_terminal_slice_four_arm_overlay_010_recovery"
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


def artifact_ref(task: str, trial: int, seed: int, position: int) -> dict[str, Any]:
    arm = overlay.ARM
    artifact = SOURCE / "artifacts" / task / arm / f"trial-{trial}.json"
    journal = SOURCE / "journals" / f"evaluation_{arm}_{task}_trial_{trial}_seed_{seed}.execution-evidence.jsonl"
    retrieval = SOURCE / "retrievals" / task / f"{arm}-{trial}.json"
    binding = SOURCE / "retrievals" / task / f"{arm}-{trial}.binding.json"
    row = load(artifact)
    identity = {"task_id": task, "trial_id": trial, "seed": seed, "arm": arm}
    if row.get("trajectory_id") != f"evaluation:{arm}:{task}:trial={trial}:seed={seed}":
        raise RecoveryImportError("unexpected successor trajectory identity")
    return {"position": position, "trajectory_id": row["trajectory_id"], "identity": identity,
            "artifact": str(artifact.resolve()), "artifact_sha256": sha(artifact),
            "journal": str(journal.resolve()), "journal_sha256": sha(journal),
            "retrieval": str(retrieval.resolve()), "retrieval_sha256": sha(retrieval),
            "binding": str(binding.resolve()), "binding_sha256": sha(binding)}


def checkpoint_325(prior: str) -> dict[str, Any]:
    directory = SOURCE / "copromem-dynamic-checkpoints" / "tasks" / "0001-325d6ec_2"
    pre = load(directory / "01-task_pre_state_frozen.json")
    post = load(directory / "post-state.json")
    if pre.get("pre_state_sha256") != prior or post.get("semantic_state_sha256") != digest(post.get("state")):
        raise RecoveryImportError("E007 complete checkpoint state mismatch")
    records = [{"path": str(p.resolve()), "sha256": sha(p)}
               for p in sorted(directory.glob("[0-9][0-9]-*.json"))]
    if len(records) != 9:
        raise RecoveryImportError("E007 checkpoint transition record count mismatch")
    return {"task_index": 10, "task_id": "325d6ec_2", "pre_state_sha256": prior,
            "post_state": str((directory / "post-state.json").resolve()),
            "post_state_file_sha256": sha(directory / "post-state.json"),
            "post_state_sha256": post["semantic_state_sha256"], "records": records}


def source() -> dict[str, Any]:
    """Validate E010 read-only and exclude its incomplete task as a whole.

    E010 recorded ten settled executor responses and nine AppWorld actions for
    trial one of ``3b8fb7a_2`` before the explicit 429.  There is no scored
    artifact and hence no valid three-trial Dynamic batch.  Replaying any part
    would repeat paid calls or evaluate an altered world state, so this
    successor retains immutable references and begins at the next task.
    """
    original = load(ORIGINAL / "manifest.json")
    if sha(ORIGINAL / "manifest.json") != (ORIGINAL / "manifest.sha256").read_text().strip():
        raise RecoveryImportError("original manifest hash mismatch")
    tasks = list(original.get("evaluation", {}).get("task_ids", ()))
    seeds = list(original.get("evaluation", {}).get("seeds", ()))
    if original.get("protocol") != overlay.PROTOCOL or len(tasks) != 100 or seeds != list(overlay.TRIAL_SEEDS):
        raise RecoveryImportError("wrong original schedule")
    custody = load(SOURCE / CUSTODY)
    recorded = custody.pop("custody_sha256", None)
    if recorded != canon(custody) or custody.get("next_task_id") != "3b8fb7a_2":
        raise RecoveryImportError("E010 inherited custody mismatch")
    prefix = list(custody.get("artifacts", ()))
    sidecar = list(custody.get("preserved_nonlearning_scored_artifacts", ()))
    if len(prefix) != 41 or len(sidecar) != 2:
        raise RecoveryImportError("E010 inherited artifact counts mismatch")
    for pos, item in enumerate(prefix, 1):
        verify_ref(item, pos)
    for pos, item in enumerate(sidecar, len(prefix) + 1):
        verify_ref(item, pos)
    chains = list(custody.get("dynamic_checkpoint_chains", ()))
    if len(chains) != 10:
        raise RecoveryImportError("E010 inherited checkpoint count mismatch")
    prior = str(chains[0].get("pre_state_sha256", ""))
    for chain in chains:
        if chain.get("pre_state_sha256") != prior:
            raise RecoveryImportError("inherited checkpoint predecessor mismatch")
        post_path = Path(str(chain.get("post_state", "")))
        post = load(post_path)
        if sha(post_path) != chain.get("post_state_file_sha256") or post.get("semantic_state_sha256") != chain.get("post_state_sha256"):
            raise RecoveryImportError("inherited checkpoint post-state mismatch")
        prior = str(chain["post_state_sha256"])
    state_path = SOURCE / BANK / "fixed-bank.json"
    state = load(state_path)
    if digest(state) != chains[-1].get("post_state_sha256"):
        raise RecoveryImportError("E010 frozen bank differs from last complete checkpoint")
    failed_task, failed_trial, failed_seed = "3b8fb7a_2", 1, seeds[0]
    failed_journal = SOURCE / "journals" / f"evaluation_{overlay.ARM}_{failed_task}_trial_{failed_trial}_seed_{failed_seed}.jsonl"
    failed_evidence = failed_journal.with_suffix(".execution-evidence.jsonl")
    if not failed_journal.is_file() or not failed_evidence.is_file() or (SOURCE / "artifacts" / failed_task / overlay.ARM / "trial-1.json").exists():
        raise RecoveryImportError("E010 incomplete trial evidence mismatch")
    journal_rows = [json.loads(line) for line in failed_journal.read_text(encoding="utf-8").splitlines() if line]
    if not journal_rows or journal_rows[-1].get("event") != "action_applied" or int(journal_rows[-1].get("index", -1)) != 8:
        raise RecoveryImportError("E010 partial journal is not the expected settled-action prefix")
    ledger_path = SOURCE / "ledger.jsonl"
    ledger = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line]
    reserved = {str(row.get("id")) for row in ledger if row.get("event") == "reserve"}
    settled = {str(row.get("id")) for row in ledger if row.get("event") == "settle"}
    if not reserved or reserved != settled:
        raise RecoveryImportError("E010 ledger contains unresolved reservation")
    executor_rows = [row for row in ledger if str(row.get("role", "")).startswith("executor:")]
    if len([row for row in executor_rows if row.get("event") == "reserve"]) != 10:
        raise RecoveryImportError("E010 executor reservation count mismatch")
    if not any(row.get("outcome") == "transport_outcome_unknown_conservative_bound" for row in ledger):
        raise RecoveryImportError("E010 terminal provider outcome is not conservatively settled")
    progress_path = SOURCE / "progress.jsonl"
    progress_rows = [json.loads(line) for line in progress_path.read_text(encoding="utf-8").splitlines() if line]
    failure_rows = [row for row in progress_rows if row.get("event") == "call_failed" and row.get("http_status") == 429]
    if len(failure_rows) != 1:
        raise RecoveryImportError("E010 must contain exactly one terminal 429 record")
    index = tasks.index(failed_task)
    remaining = tasks[index + 1:]
    if not remaining:
        raise RecoveryImportError("E010 has no legal successor task")
    new_exposure = sum((Decimal(str(row.get("usd", 0))) for row in ledger
                        if row.get("event") == "settle" and row.get("role") != "historical_carry_forward"), Decimal("0"))
    history = Decimal(str(custody["historical_settled_exposure_usd"])) + new_exposure
    return {"tasks": tasks, "seeds": seeds, "prefix": prefix, "sidecar": sidecar, "chains": chains,
            "state": {"state": state, "semantic_state_sha256": digest(state)}, "remaining": remaining,
            "history": str(history), "source_ledger_sha256": sha(ledger_path), "source_ledger_rows": len(ledger),
            "failure": {"task_id": failed_task, "arm": overlay.ARM, "failed_trial_id": failed_trial,
                        "failed_seed": failed_seed, "journal": str(failed_journal.resolve()), "journal_sha256": sha(failed_journal),
                        "execution_evidence": str(failed_evidence.resolve()), "execution_evidence_sha256": sha(failed_evidence),
                        "ledger": str(ledger_path.resolve()), "ledger_sha256": sha(ledger_path),
                        "progress": str(progress_path.resolve()), "progress_sha256": sha(progress_path),
                        "failed_call_id": failure_rows[0].get("id"), "failure_record_sha256": canon(failure_rows[0]),
                        "settled_executor_reservations": 10,
                        "reason": "explicit provider 429 after settled partial execution; whole task excluded to prevent replay",
                        "provider_calls_replayed": False}}


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
        raise RecoveryImportError("recovery custody differs from immutable E007 source")
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

