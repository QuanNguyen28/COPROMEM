#!/usr/bin/env python3
"""Immutable, no-replay continuation after an interrupted v6.2.5 overlay task.

This successor admits every scored source artifact by hash, restores only the
last complete Dynamic checkpoint, and excludes the one incomplete source trial.
It never alters the failed source run or reissues that trial's provider calls.
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
from scripts import run_v625_safe_terminal_slice_four_arm_overlay_recovery as prior

PROTOCOL = "v6_2_5_safe_terminal_slice_four_arm_overlay_recovery_003"
ORIGINAL = overlay.REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_2_5_safe_terminal_slice_four_arm_overlay_001"
SOURCE = overlay.REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_2_5_safe_terminal_slice_four_arm_overlay_003_recovery"
CUSTODY = "recovery-custody.json"
ADMISSION = "recovery-admission.json"
BANK = "recovery-initial-bank"
COMPLETE_SOURCE_TASKS = 9
PARTIAL_SOURCE_TRIALS = 2


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


def artifact_ref(run: Path, path: Path, expected: Mapping[str, Any], position: int) -> dict[str, Any]:
    row = load(path)
    if any(row.get(k) != v for k, v in expected.items()) or not isinstance(row.get("trajectory_id"), str):
        raise RecoveryImportError("scored artifact identity mismatch")
    journal = run / str(row.get("execution_evidence_path", ""))
    retrieval = run / "retrievals" / str(expected["task_id"]) / f"{expected['arm']}-{expected['trial_id']}.json"
    binding = retrieval.with_suffix(".binding.json")
    if not journal.is_file() or not retrieval.is_file() or not binding.is_file():
        raise RecoveryImportError("scored artifact custody is incomplete")
    return {"position": position, "identity": dict(expected), "trajectory_id": row["trajectory_id"],
            "artifact": str(path.resolve()), "artifact_sha256": sha(path),
            "journal": str(journal.resolve()), "journal_sha256": sha(journal),
            "retrieval": str(retrieval.resolve()), "retrieval_sha256": sha(retrieval),
            "binding": str(binding.resolve()), "binding_sha256": sha(binding)}


def source() -> dict[str, Any]:
    original_manifest = load(ORIGINAL / "manifest.json")
    if sha(ORIGINAL / "manifest.json") != (ORIGINAL / "manifest.sha256").read_text().strip():
        raise RecoveryImportError("original manifest hash mismatch")
    tasks = list(original_manifest.get("evaluation", {}).get("task_ids", ()))
    seeds = list(original_manifest.get("evaluation", {}).get("seeds", ()))
    if original_manifest.get("protocol") != overlay.PROTOCOL or original_manifest.get("arms") != [overlay.ARM] or len(tasks) != 100 or seeds != list(overlay.TRIAL_SEEDS):
        raise RecoveryImportError("wrong original schedule")
    prior_custody = load(SOURCE / prior.CUSTODY)
    prior_hash = prior_custody.pop("custody_sha256", None)
    if prior_hash != canon(prior_custody) or prior_custody.get("source_run") != str(ORIGINAL.resolve()):
        raise RecoveryImportError("prior custody is invalid")
    artifacts = list(prior_custody.get("artifacts", ()))
    if len(artifacts) != 9:
        raise RecoveryImportError("prior imported prefix is incomplete")
    for position, item in enumerate(artifacts, 1):
        if item.get("position") != position or sha(Path(item["artifact"])) != item.get("artifact_sha256") or sha(Path(item["journal"])) != item.get("journal_sha256") or sha(Path(item["retrieval"])) != item.get("retrieval_sha256") or sha(Path(item["binding"])) != item.get("binding_sha256"):
            raise RecoveryImportError("prior imported artifact hash mismatch")
    # Source tasks 4..12 are fully scored and have complete Dynamic updates.
    for task in tasks[3:12]:
        for trial, seed in enumerate(seeds, 1):
            path = SOURCE / "artifacts" / task / overlay.ARM / f"trial-{trial}.json"
            artifacts.append(artifact_ref(SOURCE, path, {"task_id": task, "arm": overlay.ARM, "trial_id": trial, "seed": seed}, len(artifacts) + 1))
    # Source task 13 has exactly two immutable, fully-scored artifacts. They
    # remain reportable historical observations, but cannot advance Dynamic
    # state because trial 3 has no score/artifact and must never be replayed.
    partial_task = tasks[12]
    for trial, seed in enumerate(seeds[:PARTIAL_SOURCE_TRIALS], 1):
        path = SOURCE / "artifacts" / partial_task / overlay.ARM / f"trial-{trial}.json"
        artifacts.append(artifact_ref(SOURCE, path, {"task_id": partial_task, "arm": overlay.ARM, "trial_id": trial, "seed": seed}, len(artifacts) + 1))
    source_artifacts = list((SOURCE / "artifacts").rglob("trial-*.json"))
    if len(source_artifacts) != COMPLETE_SOURCE_TASKS * len(seeds) + PARTIAL_SOURCE_TRIALS:
        raise RecoveryImportError("source contains unexpected scored artifact count")
    names = ("task_pre_state_frozen", "retrievals_materialized", "trajectories_complete", "batch_ready", "semantic_plan_persisted", "validation_persisted", "commit_persisted", "post_state_snapshot_persisted", "next_task_authorized")
    chains: list[dict[str, Any]] = []
    previous = prior_custody["restored_dynamic_state_sha256"]
    for index, task in enumerate(tasks[3:12], 1):
        root = SOURCE / "copromem-dynamic-checkpoints" / "tasks" / f"{index:04d}-{task}"
        records = [root / f"{number:02d}-{name}.json" for number, name in enumerate(names, 1)]
        pre, post = root / "pre-state.json", root / "post-state.json"
        if not all(path.is_file() for path in [pre, post, *records]):
            raise RecoveryImportError("source Dynamic checkpoint chain incomplete")
        pre_row, post_row = load(pre), load(post)
        if pre_row.get("semantic_state_sha256") != previous or post_row.get("semantic_state_sha256") != digest(post_row.get("state")):
            raise RecoveryImportError("source Dynamic checkpoint transition mismatch")
        previous = str(post_row["semantic_state_sha256"])
        chains.append({"task_id": task, "task_index": index, "pre_state_sha256": pre_row["semantic_state_sha256"],
                       "post_state": str(post.resolve()), "post_state_sha256": previous, "post_state_file_sha256": sha(post),
                       "records": [{"path": str(record.resolve()), "sha256": sha(record)} for record in records]})
    # The incomplete attempt has no scored artifact or terminal official score.
    incomplete_journal = SOURCE / "journals" / "evaluation_copromem_v6_2_5_dynamic_2d9f728_2_trial_3_seed_11003.jsonl"
    evidence_journal = incomplete_journal.with_suffix(".execution-evidence.jsonl")
    if partial_task != "2d9f728_2" or not incomplete_journal.is_file() or not evidence_journal.is_file():
        raise RecoveryImportError("expected incomplete source trajectory is absent")
    if (SOURCE / "artifacts" / partial_task / overlay.ARM / "trial-3.json").exists():
        raise RecoveryImportError("incomplete source trajectory unexpectedly became scored")
    ledger_path = SOURCE / "ledger.jsonl"
    try:
        ledger = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as exc:
        raise RecoveryImportError("source ledger unreadable") from exc
    reserved = {str(row.get("id")) for row in ledger if row.get("event") == "reserve"}
    settled = {str(row.get("id")) for row in ledger if row.get("event") == "settle"}
    if not reserved or reserved != settled:
        raise RecoveryImportError("source ledger has unresolved reservations")
    current_exposure = sum((Decimal(str(row.get("usd", 0))) for row in ledger if row.get("event") == "settle"), Decimal("0"))
    historical = Decimal(str(prior_custody["historical_settled_exposure_usd"])) + current_exposure
    return {"original_manifest": original_manifest, "original_manifest_sha256": sha(ORIGINAL / "manifest.json"),
            "source_manifest_sha256": sha(SOURCE / "manifest.json"), "source_runtime_identity_sha256": load(SOURCE / "runtime-identity.json")["runtime_identity_sha256"],
            "source_ledger_sha256": sha(ledger_path), "source_ledger_rows": len(ledger), "historical_exposure": str(historical),
            "artifacts": artifacts, "chains": chains, "state": load(Path(chains[-1]["post_state"])),
            "excluded_incomplete": {"identity": {"task_id": partial_task, "arm": overlay.ARM, "trial_id": 3, "seed": seeds[2]},
                                    "trajectory_id": f"evaluation:{overlay.ARM}:{partial_task}:trial=3:seed={seeds[2]}",
                                    "journal": str(incomplete_journal.resolve()), "journal_sha256": sha(incomplete_journal),
                                    "execution_evidence": str(evidence_journal.resolve()), "execution_evidence_sha256": sha(evidence_journal),
                                    "reason": "append-only execution evidence conflicts with replay; no scored artifact or terminal scorer evidence exists", "provider_calls_replayed": False},
            "remaining": tasks[13:]}


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != source.read_bytes():
        raise RecoveryImportError(f"conflicting immutable successor input: {target}")
    if not target.exists():
        shutil.copyfile(source, target)


def configure(run: Path, src: Mapping[str, Any]) -> None:
    overlay.configure(run)
    state, remaining = dict(src["state"]["state"]), list(src["remaining"])
    base.COPRO = run / BANK
    base.FROZEN_TASK_IDS = remaining
    base.ARMS = [overlay.ARM]
    base.COPRO_DYNAMIC_ARM = overlay.ARM
    base.COPRO_FIXED_ARM = "copromem_v6_2_5_fixed_unregistered"
    base.EVALUATION_SEEDS = tuple(overlay.TRIAL_SEEDS)
    base.CALL_LIMITS = {**overlay.CALL_LIMITS, "executor": len(remaining) * len(overlay.TRIAL_SEEDS) * 30}
    base.HARD_CAP_USD = overlay.HARD_CAP_USD
    base.HISTORICAL_EXPOSURE = float(Decimal(str(src["historical_exposure"])))
    base.PROTOCOL = PROTOCOL
    base.PREEXISTING_RUN_FILES = {overlay.ALLOCATION_NAME, "public-operation-intents.json", "external-admission-receipt.json", CUSTODY, BANK}
    base.identities = lambda: (load(base.CONSTRUCTION / "FINAL_CONSTRUCTION_REPORT.json"), {"state_sha256": digest(state)})


def prepare(run: Path) -> None:
    src = source()
    if run.exists() and any(run.iterdir()):
        raise RecoveryImportError("successor target must be empty")
    run.mkdir(parents=True)
    for name in (overlay.ALLOCATION_NAME, "public-operation-intents.json", "external-admission-receipt.json"):
        copy_file(ORIGINAL / name, run / name)
    custody = {"version": PROTOCOL, "original_run": str(ORIGINAL.resolve()), "source_run": str(SOURCE.resolve()),
               "original_manifest_sha256": src["original_manifest_sha256"], "source_manifest_sha256": src["source_manifest_sha256"],
               "source_runtime_identity_sha256": src["source_runtime_identity_sha256"], "source_ledger_sha256": src["source_ledger_sha256"],
               "source_ledger_rows": src["source_ledger_rows"], "historical_settled_exposure_usd": src["historical_exposure"],
               "imported_trajectory_count": len(src["artifacts"]), "imported_task_count": 12, "artifacts": src["artifacts"],
               "dynamic_checkpoint_chains": src["chains"], "restored_dynamic_state_sha256": src["chains"][-1]["post_state_sha256"],
               "excluded_incomplete_trajectory": src["excluded_incomplete"], "next_task_id": src["remaining"][0],
               "remaining_task_count": len(src["remaining"]), "composite_expected_scored_trajectories": len(src["artifacts"]) + len(src["remaining"]) * len(overlay.TRIAL_SEEDS),
               "source_immutable": True, "provider_calls_replayed": False}
    custody["custody_sha256"] = canon(custody)
    write_json(run / CUSTODY, custody)
    bank = run / BANK; bank.mkdir()
    write_json(bank / "fixed-bank.json", src["state"]["state"])
    write_json(bank / "semantic-admission-gate.json", {"state_sha256": custody["restored_dynamic_state_sha256"]})
    write_json(bank / "recovery-report.json", {"version": PROTOCOL, "custody_sha256": custody["custody_sha256"]})
    configure(run, src); base.prepare(run)
    template = load(run / "template.json")
    template.update({"protocol": PROTOCOL, "method": {"copromem": overlay.POLICY_VERSION, "retrieval": "v6.2.5 admitted retrieval; no-replay continuation from last complete Dynamic state", "analysis_scope": "continuation only; source evidence remains immutable"}, "method_policy": overlay.frozen_policy(), "runtime_identity_version": "runtime-content-identity-v3", "recovery": {"custody_file_sha256": sha(run / CUSTODY), "source_manifest_sha256": src["source_manifest_sha256"], "source_ledger_sha256": src["source_ledger_sha256"], "imported_trajectory_count": len(src["artifacts"]), "excluded_incomplete_trajectory": src["excluded_incomplete"]["trajectory_id"], "remaining_trajectory_count": len(src["remaining"]) * len(overlay.TRIAL_SEEDS), "restored_dynamic_state_sha256": custody["restored_dynamic_state_sha256"], "next_task_id": custody["next_task_id"]}})
    template["evaluation"].update({"task_ids": list(src["remaining"]), "task_count": len(src["remaining"]), "expected_trajectories": len(src["remaining"]) * len(overlay.TRIAL_SEEDS), "recovery_imported_trajectories": len(src["artifacts"]), "composite_expected_scored_trajectories": custody["composite_expected_scored_trajectories"], "allocation_audit_sha256": sha(run / overlay.ALLOCATION_NAME)})
    template["banks"]["copromem_sha256"] = custody["restored_dynamic_state_sha256"]
    template["budget"].update({"historical_settled_exposure": float(Decimal(src["historical_exposure"])), "hard_cap_usd": overlay.HARD_CAP_USD, "call_limits": dict(base.CALL_LIMITS)})
    template["execution"].update({"provider_only": overlay.CHAT_PROVIDER, "call_limits": dict(base.CALL_LIMITS)})
    runtime, inputs = build_evaluation_identity_v3(root=overlay.ROOT, manifest=template)
    write_json(run / "runtime-identity.json", runtime)
    write_json(run / "runtime-identity.binding.json", {"runtime_identity_sha256": runtime["runtime_identity_sha256"], "runtime_identity_record_sha256": sha(run / "runtime-identity.json")})
    template["runtime_identity_inputs"] = inputs; template["runtime_identity_sha256"] = runtime["runtime_identity_sha256"]; template["runtime_identity_file_sha256"] = sha(run / "runtime-identity.json")
    write_json(run / "template.json", template)


def verify(run: Path) -> dict[str, Any]:
    src = source(); custody = load(run / CUSTODY); recorded = custody.pop("custody_sha256", None)
    if recorded != canon(custody) or custody.get("source_ledger_sha256") != src["source_ledger_sha256"] or custody.get("artifacts") != src["artifacts"] or custody.get("dynamic_checkpoint_chains") != src["chains"] or custody.get("excluded_incomplete_trajectory") != src["excluded_incomplete"] or custody.get("next_task_id") != src["remaining"][0]:
        raise RecoveryImportError("recovery custody differs from immutable source")
    if digest(load(run / BANK / "fixed-bank.json")) != src["chains"][-1]["post_state_sha256"]:
        raise RecoveryImportError("successor initial bank differs from last complete Dynamic state")
    return src


def freeze(run: Path) -> None:
    src = verify(run); configure(run, src); base.freeze(run)


def preflight(run: Path) -> None:
    src = verify(run); configure(run, src); manifest = base.load(run)
    if manifest["evaluation"]["task_ids"] != src["remaining"]:
        raise RecoveryImportError("successor schedule is not the exact post-interruption suffix")
    route = overlay.verify_locked_chat_route_available()
    if route.get("provider") != overlay.CHAT_PROVIDER:
        raise RecoveryImportError("provider route changed")
    write_json(run / "provider-route-preflight.json", route)
    write_json(run / ADMISSION, {"version": PROTOCOL, "custody_file_sha256": sha(run / CUSTODY), "source_ledger_sha256": src["source_ledger_sha256"], "imported_trajectory_count": len(src["artifacts"]), "excluded_incomplete_trajectory": src["excluded_incomplete"]["trajectory_id"], "next_task_id": src["remaining"][0], "provider_calls_replayed": False})
    base.st(run, "preflight_passed", imported_completed_trajectories=len(src["artifacts"]), next_task_id=src["remaining"][0])


def run(run: Path) -> None:
    src = verify(run); configure(run, src); preflight(run); base.run(run)


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("prepare", "freeze", "preflight", "run")); parser.add_argument("--run", required=True, type=Path); args = parser.parse_args()
    {"prepare": prepare, "freeze": freeze, "preflight": preflight, "run": run}[args.command](args.run.resolve())


if __name__ == "__main__":
    main()