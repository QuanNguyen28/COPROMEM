#!/usr/bin/env python3
"""Restart-safe four-arm continuation after an interrupted unscored source attempt."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from copromem.experiments.reme_copromem.runner import AppendOnlyLedger, execute_trajectory, official_post, services, write_json
from copromem.experiments.reme_copromem.runtime_identity_v3 import IDENTITY_VERSION, build_evaluation_identity_v3
from copromem.experiments.reme_copromem.live_summary import reconcile_ledger
from copromem.experiments.reme_copromem.evidence_contract import validate as validate_execution_evidence
from copromem.integrations.reme.dynamic_checkpoint import DynamicUpdateIdentity, ReMeDynamicCheckpointManager
from copromem.integrations.reme.fixed_checkpoint import ReMeFixedIntegrityManager
from copromem.integrations.reme.bank import semantic_bank_hash
from copromem.integrations.reme.lifecycle import dynamic_post_trial_update
from copromem.integrations.reme.transport import PROVIDER as CHAT_PROVIDER, verify_locked_chat_route_available
from scripts import run_v61_exploratory_evaluation as base
from scripts import run_v622_parallel_real_pilot as real
from scripts import run_v622_parallel_baseline_pilot as parallel


PROTOCOL = "v6.2.2-four-arm-continuation-recovery-063"
SOURCE_RUN = parallel.REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_2_2_real_pilot_100_062_four_arm_successor"
FOUR_ARMS = ["no_memory", "official_upstream_reme_fixed", "official_upstream_reme_dynamic", "reasoningbank"]
CUSTODY = "four-arm-successor-custody.json"


def _source_artifact(task: str, arm: str, trial: int) -> Path:
    return SOURCE_RUN / "artifacts" / task / arm / f"trial-{trial}.json"


def _new_dynamic_order(manifest: Mapping[str, Any]) -> list[DynamicUpdateIdentity]:
    """Only Dynamic trajectories absent from immutable source evidence update here."""
    return [DynamicUpdateIdentity(f"evaluation:official_upstream_reme_dynamic:{task}:trial={trial}:seed={seed}", task, trial, seed)
            for task in manifest["evaluation"]["task_ids"]
            for trial, seed in enumerate(manifest["evaluation"]["seeds"], 1)
            if not _source_artifact(task, "official_upstream_reme_dynamic", trial).is_file()]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"invalid JSON object: {path.name}")
    return value


def _source() -> tuple[dict[str, Any], list[str], Path, str, float]:
    manifest = _load(SOURCE_RUN / "manifest.json")
    if _sha(SOURCE_RUN / "manifest.json") != (SOURCE_RUN / "manifest.sha256").read_text().strip():
        raise RuntimeError("source manifest hash mismatch")
    tasks = list(manifest["evaluation"]["task_ids"]); seeds = list(manifest["evaluation"]["seeds"])
    completed = 0
    for task in tasks:
        if all((SOURCE_RUN / "artifacts" / task / arm / f"trial-{trial}.json").is_file()
               for arm in FOUR_ARMS for trial in range(1, len(seeds) + 1)):
            completed += 1
        else:
            break
    if completed != 3:
        raise RuntimeError(f"source four-arm prefix differs: expected 3 tasks, found {completed}")
    # Task four contains only the six durable No Memory/Fixed records.  The
    # Dynamic attempt has a reservation and journal but no artifact, and the
    # ReasoningBank records were never opened.  Any other post-prefix artifact
    # would make this recovery ambiguous.
    partial = {(task, arm, trial) for task in tasks[completed:] for arm in FOUR_ARMS
               for trial in range(1, len(seeds) + 1)
               if (SOURCE_RUN / "artifacts" / task / arm / f"trial-{trial}.json").is_file()}
    expected_partial = {(tasks[3], arm, trial) for arm in ("no_memory", "official_upstream_reme_fixed")
                        for trial in range(1, len(seeds) + 1)}
    if partial != expected_partial:
        raise RuntimeError("source post-prefix artifact inventory is ambiguous")
    snapshot = SOURCE_RUN / "reme-dynamic-checkpoints" / "snapshots" / "update-0009.jsonl"
    marker = SOURCE_RUN / "reme-dynamic-checkpoints" / "markers" / "update-0009.json"
    if not snapshot.is_file() or not marker.is_file() or semantic_bank_hash(snapshot) != _load(marker).get("post_update_semantic_sha256"):
        raise RuntimeError("source ReMe Dynamic checkpoint 0177 is invalid")
    ledger = [json.loads(line) for line in (SOURCE_RUN / "ledger.jsonl").read_text().splitlines()]
    reserve = {str(row["id"]): Decimal(str(row["usd"])) for row in ledger if row.get("event") == "reserve"}
    settled = {str(row["id"]): Decimal(str(row["usd"])) for row in ledger if row.get("event") == "settle"}
    unresolved = set(reserve) - set(settled)
    expected_unresolved = {
        "1791311356877590259-executor:official_upstream_reme_dynamic:21abae1_3:trial=1:seed=11001",
    }
    if unresolved != expected_unresolved:
        raise RuntimeError("source unresolved reservation set differs")
    exposure = sum(settled.values(), Decimal("0")) + sum((reserve[item] for item in unresolved), Decimal("0"))
    return manifest, tasks[completed:], snapshot, semantic_bank_hash(snapshot), float(exposure)


def _custody(run: Path) -> dict[str, Any]:
    source, remaining, snapshot, snapshot_hash, exposure = _source()
    body = {"version": "four-arm-successor-custody-v1", "source_run": str(SOURCE_RUN),
            "source_manifest_sha256": _sha(SOURCE_RUN / "manifest.json"),
            "source_runtime_identity_sha256": source["runtime_identity_sha256"],
            "source_ledger_sha256": _sha(SOURCE_RUN / "ledger.jsonl"),
            "source_completed_task_count": 3, "source_completed_trajectory_count": 42,
            "source_arms": FOUR_ARMS, "next_task_id": remaining[0], "remaining_task_ids": remaining,
            "reme_dynamic_snapshot": str(snapshot), "reme_dynamic_snapshot_sha256": _sha(snapshot),
            "reme_dynamic_semantic_sha256": snapshot_hash,
            "source_effective_historical_exposure_usd": str(exposure),
            "source_unresolved_reservation_ids": [
                "1791299343795213926-reme_embedding:reme-fixed",
                "1791305783400558009-executor:copromem_v6_2_2_fixed:0de03ea_3:trial=3:seed=11003",
            ]}
    body["record_sha256"] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return body


def configure(run: Path) -> dict[str, Any]:
    # Reuse the maintained executor/ReasoningBank adapter configuration, then
    # narrow the successor schedule before any manifest is built.
    real._configure(run)
    custody = _load(run / CUSTODY)
    source, remaining, _snapshot, _snapshot_hash, exposure = _source()
    if custody != _custody(run):
        raise RuntimeError("four-arm custody record drift")
    base.PROTOCOL = PROTOCOL; base.ARMS = list(FOUR_ARMS); base.FROZEN_TASK_IDS = remaining
    base.EVALUATION_SEEDS = list(source["evaluation"]["seeds"]); base.HISTORICAL_EXPOSURE = exposure
    base.CALL_LIMITS = {"executor": len(remaining) * len(base.EVALUATION_SEEDS) * 4 * 30,
                        "reme_lifecycle": len(remaining) * len(base.EVALUATION_SEEDS) * 8,
                        "reme_embedding": len(remaining) * len(base.EVALUATION_SEEDS) * 32,
                        "reasoningbank_embedding": len(remaining) * len(base.EVALUATION_SEEDS),
                        "copromem_decomposition": 0}
    base.HARD_CAP_USD = 1500.0; base.PREEXISTING_RUN_FILES = {real.ALLOCATION_NAME, CUSTODY}
    base._dynamic_order = _new_dynamic_order
    return custody


def prepare(run: Path) -> None:
    custody = _custody(run); run.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(SOURCE_RUN / real.ALLOCATION_NAME, run / real.ALLOCATION_NAME)
    write_json(run / CUSTODY, custody)
    configure(run); base.prepare(run)
    template = _load(run / "template.json")
    template["protocol"] = PROTOCOL; template["arms"] = FOUR_ARMS
    # Six scored source artifacts on the interrupted fourth task are custody
    # references, not copied or replayed into this successor.
    template["evaluation"].update({"expected_trajectories": 450,
                                   "source_completed_trajectory_count": 42})
    template["execution"]["provider_only"] = CHAT_PROVIDER
    rb = parallel._rb_manifest_record(run)
    template["banks"]["reasoningbank_sha256"] = rb["semantic_state_sha256"]
    template["method_policy"] = dict(real.frozen_policy())
    template["method_policy"]["reasoningbank"] = dict(rb)
    template["evaluation"]["allocation_audit_sha256"] = base.file_sha(run / real.ALLOCATION_NAME)
    template["method"] = {"comparison_design": "four-arm continuation after immutable CoProMem pause",
                           "copromem": "not scheduled in this successor", "reasoningbank": "frozen bank",
                           "source_prefix": "42 immutable source trajectories; one reserved but unscored attempt is carried as conservative historical exposure"}
    template["successor_custody_sha256"] = custody["record_sha256"]
    template["runtime_identity_version"] = IDENTITY_VERSION
    runtime, inputs = build_evaluation_identity_v3(root=real.v622.ROOT, manifest=template)
    write_json(run / "runtime-identity.json", runtime)
    write_json(run / "runtime-identity.binding.json", {"runtime_identity_sha256": runtime["runtime_identity_sha256"], "runtime_identity_record_sha256": base.file_sha(run / "runtime-identity.json")})
    template["runtime_identity_inputs"] = inputs; template["runtime_identity_sha256"] = runtime["runtime_identity_sha256"]; template["runtime_identity_file_sha256"] = base.file_sha(run / "runtime-identity.json")
    write_json(run / "template.json", template)


def _checkpoint(run: Path, manifest: Mapping[str, Any], service: Any, verifier: Any, initial_hash: str) -> ReMeDynamicCheckpointManager:
    ledger_path = run / "ledger.jsonl"
    def dump(path: Path) -> None: official_post(service.base_url, "dump_memory", {"dump_file_path": str(path)})
    def load(path: Path) -> None: official_post(service.base_url, "load_memory", {"load_file_path": str(path), "clear_existing": True})
    def verify(snapshot: Path, target: Path) -> None:
        official_post(verifier.base_url, "load_memory", {"load_file_path": str(snapshot), "clear_existing": True})
        official_post(verifier.base_url, "dump_memory", {"dump_file_path": str(target)})
    return ReMeDynamicCheckpointManager(root=run / "reme-dynamic-checkpoints", ordered_updates=base._dynamic_order(manifest),
        dump_current=dump, load_current=load, dump_verifier=verify,
        official_update=lambda agent, score, event: dynamic_post_trial_update(agent, score, event),
        ledger_offset=lambda: ledger_path.stat().st_size if ledger_path.exists() else 0,
        settled_ids=lambda offset: base._settled_after(ledger_path, offset),
        validate_settlements=lambda offset, ids: base._validate_dynamic_settlements(ledger_path, offset, ids),
        validate_marker_settlements=lambda marker: base._validate_marker_settlements(ledger_path, marker),
        verify_no_provider_calls=lambda offset: base._verify_verifier_no_provider(ledger_path, offset),
        initial_semantic_hash=initial_hash,
        validate_evidence=lambda result: validate_execution_evidence(result, run_root=run, expected_registry_sha256=json.loads(base.REG.read_text())["registry_sha256"]),
        event=lambda row: base.ev(run, row.pop("event"), **row))


def run(run: Path) -> None:
    # Locators and arm configuration must be installed before ``base.load``
    # verifies the immutable shared-bank identities.
    custody = configure(run); manifest = base.load(run); lock = run / "runner.lock"
    if lock.exists(): raise RuntimeError("duplicate runner")
    write_json(lock, {"pid": os.getpid()})
    ledger = AppendOnlyLedger(run / "ledger.jsonl", base.HARD_CAP_USD, manifest["budget"]["call_limits"])
    if not base._has_ledger_reservation(run / "ledger.jsonl", "historical-construction-carry"):
        ledger.reserve("historical-construction-carry", base.HISTORICAL_EXPOSURE, {"role": "historical_carry_forward"}); ledger.settle("historical-construction-carry", base.HISTORICAL_EXPOSURE, {"role": "historical_carry_forward"})
    base._runtime_checkpoint(run, manifest, "startup"); api_key = base.key(); base.st(run, "running", manifest_sha256=base.file_sha(run / "manifest.json"))
    registry = _load(base.REG); context = base.EXTRA_RUNTIME_FACTORY(run, manifest, ledger, api_key, registry)
    owned: dict[str, Any] = {}
    try:
        with services(run, run / "ledger.jsonl", run / "progress.jsonl", base.HARD_CAP_USD, ["reme-fixed", "reme-dynamic", "reme-dynamic-verifier"], lifecycle_input_ceiling=base.LIFECYCLE_INPUT_CEILING) as svc:
            owned = svc; shared = base.CONSTRUCTION / "reme/shared-bank.jsonl"
            for name in ("reme-fixed", "reme-dynamic"): official_post(svc[name].base_url, "load_memory", {"load_file_path": str(shared), "clear_existing": True})
            source_snapshot = Path(str(custody["reme_dynamic_snapshot"])); official_post(svc["reme-dynamic"].base_url, "load_memory", {"load_file_path": str(source_snapshot), "clear_existing": True})
            fixed = ReMeFixedIntegrityManager(root=run / "reme-fixed-integrity", frozen_semantic_hash=manifest["banks"]["reme_shared_sha256"], dump_current=lambda path: official_post(svc["reme-fixed"].base_url, "dump_memory", {"dump_file_path": str(path)}))
            fixed_marker = fixed.checkpoint(label="initial")
            dynamic = _checkpoint(run, manifest, svc["reme-dynamic"], svc["reme-dynamic-verifier"], str(custody["reme_dynamic_semantic_sha256"]))
            dynamic.restore_latest()
            for position, task in enumerate(manifest["evaluation"]["task_ids"], 1):
                base._runtime_checkpoint(run, manifest, f"task-{position:04d}-before-open"); base.guard(manifest, run, "task")
                for arm in FOUR_ARMS:
                    for trial, seed in enumerate(manifest["evaluation"]["seeds"], 1):
                        path = run / "artifacts" / task / arm / f"trial-{trial}.json"
                        source_path = _source_artifact(task, arm, trial)
                        if source_path.is_file():
                            # Original bytes stay at the original path.  It is
                            # an already scored prefix member and must never be
                            # re-executed merely because its successor differs.
                            validate_execution_evidence(_load(source_path), run_root=SOURCE_RUN,
                                                        expected_registry_sha256=registry["registry_sha256"])
                            continue
                        if path.is_file():
                            row = _load(path); parallel._existing_validator(context, run, manifest, arm, task, trial, seed, path, row)
                            if arm == "official_upstream_reme_dynamic" and base._dynamic_order(manifest).index(DynamicUpdateIdentity.from_result(row)) >= dynamic.reconcile()["completed_count"]: raise RuntimeError("existing Dynamic artifact lacks checkpoint")
                            continue
                        kwargs: dict[str, Any] = {}
                        if arm.startswith("official_upstream_reme"): kwargs["memory_base_url"] = svc["reme-fixed" if arm.endswith("fixed") else "reme-dynamic"].base_url
                        if arm == "official_upstream_reme_dynamic": kwargs.update({"post_score_update": dynamic.callback(path), "post_score_update_strict": True})
                        kwargs.update(base.EXTRA_ARM_KWARGS(context, run, manifest, arm, task, trial, seed, path))
                        runtime = _load(run / "runtime-identity.json")
                        execute_trajectory(run=run, progress=run / "progress.jsonl", ledger=ledger, api_key=api_key, all_task_ids=manifest["evaluation"]["task_ids"], arm=arm, task_id=task, trial_id=trial, seed=seed, max_actions=30, temperature=.7, phase="evaluation", artifact_path=path, execution_evidence={"registry_path": str(base.REG.resolve()), "registry_sha256": registry["registry_sha256"], "runtime_identity_sha256": runtime["runtime_identity_sha256"], "runtime_identity_record_sha256": base.file_sha(run / "runtime-identity.json")}, **kwargs)
                        if not path.is_file(): raise RuntimeError("executor returned without artifact")
                        base.summary(run, manifest)
                fixed_marker = fixed.checkpoint(label=f"task-{position:04d}", predecessor_checkpoint_sha256=fixed_marker["checkpoint_sha256"]); base.summary(run, manifest)
            base._runtime_checkpoint(run, manifest, "terminal"); base.summary(run, manifest, state="completed", final=True)
            if dynamic.reconcile()["completed_count"] != len(base._dynamic_order(manifest)): raise RuntimeError("Dynamic checkpoint prefix incomplete at terminal")
            parallel._terminal_check(run, manifest)
            terminal = {"version": "four-arm-terminal-v1", "manifest_sha256": base.file_sha(run / "manifest.json"), "custody_sha256": custody["record_sha256"], "artifact_inventory_sha256": base._inventory_hash(run / "artifacts"), "ledger_sha256": base.file_sha(run / "ledger.jsonl"), "reme_dynamic_checkpoint_chain_sha256": base._inventory_hash(run / "reme-dynamic-checkpoints")}
            terminal["record_sha256"] = hashlib.sha256(json.dumps(terminal, sort_keys=True, separators=(",", ":")).encode()).hexdigest(); write_json(run / "terminal-reconciliation.json", terminal)
            base.st(run, "completed", manifest_sha256=terminal["manifest_sha256"], terminal_reconciliation_sha256=terminal["record_sha256"])
    except BaseException as exc:
        base.st(run, "failed", failure_class=type(exc).__name__, failure_message=str(exc)[:240]); base.ev(run, "runner_failed", failure_class=type(exc).__name__)
        try: base.summary(run, manifest, state="failed")
        except Exception: pass
        raise
    finally:
        if lock.exists(): lock.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=["prepare", "freeze", "preflight", "run"]); parser.add_argument("--run", required=True, type=Path); args = parser.parse_args(); run_path = args.run.resolve()
    if args.command == "prepare": prepare(run_path)
    elif args.command == "freeze": configure(run_path); base.freeze(run_path)
    elif args.command == "preflight":
        configure(run_path); base.load(run_path); write_json(run_path / "provider-route-preflight.json", verify_locked_chat_route_available()); base.st(run_path, "preflight_passed")
    else: run(run_path)


if __name__ == "__main__": main()



