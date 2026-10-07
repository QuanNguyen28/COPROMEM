#!/usr/bin/env python3
"""Hash-bound continuation of E068: retain 312 immutable results, run only 144 missing grid entries."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
from functools import lru_cache
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

PROTOCOL = "v6.2.2-four-arm-continuation-recovery-069"
SOURCE_RUN = parallel.REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_2_2_real_pilot_100_068_four_arm_recovery"
FOUR_ARMS = ["no_memory", "official_upstream_reme_fixed", "official_upstream_reme_dynamic", "reasoningbank"]
CUSTODY = "four-arm-successor-custody.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"invalid JSON object: {path}")
    return value


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _source_root(path: Path) -> Path:
    return path.parents[3]


def _key(row: Mapping[str, Any]) -> tuple[str, str, int, int]:
    return str(row["task_id"]), str(row["arm"]), int(row["trial_id"]), int(row["seed"])


def _source_records(manifest: Mapping[str, Any]) -> dict[tuple[str, str, int, int], dict[str, str]]:
    expected = {(task, arm, trial, seed) for task in manifest["evaluation"]["task_ids"] for arm in FOUR_ARMS
                for trial, seed in enumerate(manifest["evaluation"]["seeds"], 1)}
    records: dict[tuple[str, str, int, int], dict[str, str]] = {}
    def admit(path: Path, claimed: str | None = None) -> None:
        if not path.is_file():
            raise RuntimeError(f"missing immutable source artifact: {path}")
        if claimed is not None and _sha(path) != claimed:
            raise RuntimeError("immutable source artifact hash mismatch")
        row = _load(path); key = _key(row)
        if key not in expected or key in records:
            raise RuntimeError("source artifact grid is out of scope or duplicated")
        records[key] = {"path": str(path), "sha256": _sha(path)}
    for path in sorted((SOURCE_RUN / "artifacts").glob("**/trial-*.json")):
        admit(path)
    upstream = _load(SOURCE_RUN / CUSTODY)
    body = dict(upstream); observed = body.pop("record_sha256", None)
    if observed != _digest(body):
        raise RuntimeError("E068 predecessor custody hash mismatch")
    for item in upstream.get("carried_artifacts", []):
        path = Path(str(item["path"]))
        # Only the sixteen predecessor entries whose key is on E068's schedule
        # are part of this continuation; all remain at their source path.
        if path.is_file():
            row = _load(path)
            if _key(row) in expected:
                admit(path, str(item["sha256"]))
    if len(records) != 312:
        raise RuntimeError(f"E068 immutable prefix differs: expected 312 artifacts, found {len(records)}")
    return records


@lru_cache(maxsize=1)
def _source() -> tuple[dict[str, Any], dict[tuple[str, str, int, int], dict[str, str]], list[tuple[str, str, int, int]], Path, str, Decimal, list[str]]:
    manifest = _load(SOURCE_RUN / "manifest.json")
    if _sha(SOURCE_RUN / "manifest.json") != (SOURCE_RUN / "manifest.sha256").read_text(encoding="utf-8").strip():
        raise RuntimeError("E068 manifest hash mismatch")
    if list(manifest.get("arms", manifest["evaluation"].get("arms", []))) != FOUR_ARMS:
        raise RuntimeError("E068 arm schedule differs")
    records = _source_records(manifest)
    expected = [(task, arm, trial, seed) for task in manifest["evaluation"]["task_ids"] for arm in FOUR_ARMS
                for trial, seed in enumerate(manifest["evaluation"]["seeds"], 1)]
    missing = [key for key in expected if key not in records]
    if len(expected) != 456 or len(missing) != 144:
        raise RuntimeError("E068 composite schedule inventory differs")
    # All retained artifacts form the first 26 complete task blocks; this
    # prevents a skipped or reordered source suffix from being admitted.
    counts = [sum(k[0] == task for k in records) for task in manifest["evaluation"]["task_ids"]]
    if counts != [12] * 26 + [0] * 12:
        raise RuntimeError("E068 source prefix is not the expected contiguous 26-task prefix")
    rows = [json.loads(line) for line in (SOURCE_RUN / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    reserve = {str(row["id"]): Decimal(str(row["usd"])) for row in rows if row.get("event") == "reserve"}
    settle = {str(row["id"]): Decimal(str(row["usd"])) for row in rows if row.get("event") == "settle"}
    unresolved = sorted(set(reserve) - set(settle))
    failed_id = "1791346729899770172-executor:no_memory:9dabbc9_2:trial=1:seed=11001"
    if unresolved != [failed_id]:
        raise RuntimeError("E068 unresolved reservation inventory differs")
    # Failed call had no scored artifact, execution evidence, or action. It is
    # historical conservative exposure, never replayed as a source artifact.
    evidence = SOURCE_RUN / "journals" / "evaluation_no_memory_9dabbc9_2_trial_1_seed_11001.execution-evidence.jsonl"
    if evidence.exists() and evidence.read_text(encoding="utf-8").strip():
        raise RuntimeError("failed E068 call has execution evidence and cannot be retried")
    marker = SOURCE_RUN / "reme-dynamic-checkpoints" / "markers" / "update-0075.json"
    snapshot = SOURCE_RUN / "reme-dynamic-checkpoints" / "snapshots" / "update-0075.jsonl"
    markers = sorted((SOURCE_RUN / "reme-dynamic-checkpoints" / "markers").glob("update-*.json"))
    if len(markers) != 75 or not marker.is_file() or not snapshot.is_file():
        raise RuntimeError("E068 Dynamic checkpoint prefix differs")
    latest = _load(marker)
    state_hash = semantic_bank_hash(snapshot)
    if state_hash != latest.get("post_update_semantic_sha256"):
        raise RuntimeError("E068 Dynamic snapshot semantic hash differs")
    dynamic_records = sum(1 for key in records if key[1] == "official_upstream_reme_dynamic")
    if dynamic_records != 78:
        raise RuntimeError("E068 composite Dynamic artifact cardinality differs")
    exposure = sum(settle.values(), Decimal("0")) + sum((reserve[key] for key in unresolved), Decimal("0"))
    return manifest, records, missing, snapshot, state_hash, exposure, unresolved


def _new_dynamic_order(manifest: Mapping[str, Any]) -> list[DynamicUpdateIdentity]:
    _source_manifest, _records, missing, _snap, _hash, _exposure, _unresolved = _source()
    return [DynamicUpdateIdentity(f"evaluation:official_upstream_reme_dynamic:{task}:trial={trial}:seed={seed}", task, trial, seed)
            for task, arm, trial, seed in missing if arm == "official_upstream_reme_dynamic"]


def _custody() -> dict[str, Any]:
    source, records, missing, snapshot, state_hash, exposure, unresolved = _source()
    body: dict[str, Any] = {
        "version": "four-arm-successor-custody-v4",
        "source_run": str(SOURCE_RUN),
        "source_manifest_sha256": _sha(SOURCE_RUN / "manifest.json"),
        "source_runtime_identity_sha256": source["runtime_identity_sha256"],
        "source_ledger_sha256": _sha(SOURCE_RUN / "ledger.jsonl"),
        "source_prior_custody_sha256": _load(SOURCE_RUN / CUSTODY)["record_sha256"],
        "source_completed_trajectory_count": len(records),
        "successor_new_trajectory_count": len(missing),
        "source_arms": FOUR_ARMS,
        "source_effective_historical_exposure_usd": str(exposure),
        "source_unresolved_reservation_ids": unresolved,
        "reme_dynamic_snapshot": str(snapshot),
        "reme_dynamic_snapshot_sha256": _sha(snapshot),
        "reme_dynamic_semantic_sha256": state_hash,
        "reme_dynamic_completed_checkpoint_count": 75,
        "next_task_id": missing[0][0],
        "missing_grid": [{"task_id": t, "arm": a, "trial_id": tr, "seed": s} for t, a, tr, s in missing],
        "carried_artifacts": [{"task_id": k[0], "arm": k[1], "trial_id": k[2], "seed": k[3], **v} for k, v in sorted(records.items())],
    }
    body["record_sha256"] = _digest(body)
    return body


def configure(run: Path) -> dict[str, Any]:
    real._configure(run)
    custody = _load(run / CUSTODY)
    if custody != _custody():
        raise RuntimeError("successor custody drift")
    source, _records, missing, _snapshot, _state_hash, exposure, _unresolved = _source()
    base.PROTOCOL = PROTOCOL; base.ARMS = list(FOUR_ARMS)
    base.FROZEN_TASK_IDS = list(source["evaluation"]["task_ids"])
    base.EVALUATION_SEEDS = list(source["evaluation"]["seeds"]); base.HISTORICAL_EXPOSURE = float(exposure)
    dynamic_missing = sum(1 for key in missing if key[1] == "official_upstream_reme_dynamic")
    base.CALL_LIMITS = {"executor": len(missing) * 30, "reme_lifecycle": dynamic_missing * 8,
                        "reme_embedding": dynamic_missing * 32, "reasoningbank_embedding": sum(1 for key in missing if key[1] == "reasoningbank"), "copromem_decomposition": 0}
    base.HARD_CAP_USD = 1500.0; base.PREEXISTING_RUN_FILES = {real.ALLOCATION_NAME, CUSTODY}; base._dynamic_order = _new_dynamic_order
    return custody


def prepare(run: Path) -> None:
    source, _records, missing, _snapshot, _hash, _exposure, _unresolved = _source()
    run.mkdir(parents=True, exist_ok=True); shutil.copy2(SOURCE_RUN / real.ALLOCATION_NAME, run / real.ALLOCATION_NAME)
    write_json(run / CUSTODY, _custody()); configure(run); base.prepare(run)
    template = _load(run / "template.json"); template["protocol"] = PROTOCOL; template["arms"] = FOUR_ARMS
    template["evaluation"].update({"expected_trajectories": 456, "source_completed_trajectory_count": 312, "successor_new_trajectory_count": len(missing)})
    template["execution"]["provider_only"] = CHAT_PROVIDER
    rb = parallel._rb_manifest_record(run); template["banks"]["reasoningbank_sha256"] = rb["semantic_state_sha256"]
    template["method_policy"] = dict(real.frozen_policy()); template["method_policy"]["reasoningbank"] = dict(rb)
    template["evaluation"]["allocation_audit_sha256"] = base.file_sha(run / real.ALLOCATION_NAME)
    template["method"] = {"comparison_design": "four-arm continuation from E068 immutable prefix", "copromem": "not scheduled", "reasoningbank": "frozen bank", "source_prefix": "312 immutable scored artifacts; 144 missing trajectories only"}
    template["successor_custody_sha256"] = _custody()["record_sha256"]; template["runtime_identity_version"] = IDENTITY_VERSION
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
        official_post(verifier.base_url, "load_memory", {"load_file_path": str(snapshot), "clear_existing": True}); official_post(verifier.base_url, "dump_memory", {"dump_file_path": str(target)})
    return ReMeDynamicCheckpointManager(root=run / "reme-dynamic-checkpoints", ordered_updates=base._dynamic_order(manifest), dump_current=dump, load_current=load, dump_verifier=verify,
        official_update=lambda agent, score, event: dynamic_post_trial_update(agent, score, event), ledger_offset=lambda: ledger_path.stat().st_size if ledger_path.exists() else 0,
        settled_ids=lambda offset: base._settled_after(ledger_path, offset), validate_settlements=lambda offset, ids: base._validate_dynamic_settlements(ledger_path, offset, ids),
        validate_marker_settlements=lambda marker: base._validate_marker_settlements(ledger_path, marker), verify_no_provider_calls=lambda offset: base._verify_verifier_no_provider(ledger_path, offset),
        initial_semantic_hash=initial_hash, validate_evidence=lambda result: validate_execution_evidence(result, run_root=run, expected_registry_sha256=json.loads(base.REG.read_text(encoding="utf-8"))["registry_sha256"]), event=lambda row: base.ev(run, row.pop("event"), **row))


def _validate_completion(run: Path, manifest: Mapping[str, Any], custody: Mapping[str, Any]) -> None:
    registry = _load(base.REG); expected = {(task, arm, trial, seed) for task in manifest["evaluation"]["task_ids"] for arm in FOUR_ARMS for trial, seed in enumerate(manifest["evaluation"]["seeds"], 1)}
    carried: set[tuple[str, str, int, int]] = set()
    for item in custody["carried_artifacts"]:
        path = Path(str(item["path"]))
        if not path.is_file() or _sha(path) != item["sha256"]: raise RuntimeError("immutable carried artifact changed")
        row = _load(path); validate_execution_evidence(row, run_root=_source_root(path), expected_registry_sha256=registry["registry_sha256"]); carried.add(_key(row))
    owned: set[tuple[str, str, int, int]] = set()
    for path in (run / "artifacts").glob("**/trial-*.json"):
        row = _load(path); parallel._existing_validator(None, run, manifest, str(row["arm"]), str(row["task_id"]), int(row["trial_id"]), int(row["seed"]), path, row); owned.add(_key(row))
    if carried & owned or carried | owned != expected: raise RuntimeError("composite completion inventory is incomplete, duplicated, or reordered")
    reconciliation = reconcile_ledger(run / "ledger.jsonl", historical_expected_usd=base.HISTORICAL_EXPOSURE, registered_arms=FOUR_ARMS)
    if reconciliation.unresolved_reservation_ids: raise RuntimeError("successor has unresolved reservations at terminal")


def run(run: Path) -> None:
    custody = configure(run); manifest = base.load(run); lock = run / "runner.lock"
    if lock.exists(): raise RuntimeError("duplicate runner")
    write_json(lock, {"pid": os.getpid()}); ledger = AppendOnlyLedger(run / "ledger.jsonl", base.HARD_CAP_USD, manifest["budget"]["call_limits"])
    if not base._has_ledger_reservation(run / "ledger.jsonl", "historical-e068-carry"):
        ledger.reserve("historical-e068-carry", base.HISTORICAL_EXPOSURE, {"role": "historical_carry_forward_e068"}); ledger.settle("historical-e068-carry", base.HISTORICAL_EXPOSURE, {"role": "historical_carry_forward_e068"})
    base._runtime_checkpoint(run, manifest, "startup"); api_key = base.key(); base.st(run, "running", manifest_sha256=base.file_sha(run / "manifest.json")); registry = _load(base.REG); context = base.EXTRA_RUNTIME_FACTORY(run, manifest, ledger, api_key, registry)
    try:
        source_records = _source()[1]
        with services(run, run / "ledger.jsonl", run / "progress.jsonl", base.HARD_CAP_USD, ["reme-fixed", "reme-dynamic", "reme-dynamic-verifier"], lifecycle_input_ceiling=base.LIFECYCLE_INPUT_CEILING) as svc:
            shared = base.CONSTRUCTION / "reme/shared-bank.jsonl"
            for name in ("reme-fixed", "reme-dynamic"): official_post(svc[name].base_url, "load_memory", {"load_file_path": str(shared), "clear_existing": True})
            official_post(svc["reme-dynamic"].base_url, "load_memory", {"load_file_path": str(custody["reme_dynamic_snapshot"]), "clear_existing": True})
            fixed = ReMeFixedIntegrityManager(root=run / "reme-fixed-integrity", frozen_semantic_hash=manifest["banks"]["reme_shared_sha256"], dump_current=lambda path: official_post(svc["reme-fixed"].base_url, "dump_memory", {"dump_file_path": str(path)})); fixed_marker = fixed.checkpoint(label="initial")
            dynamic = _checkpoint(run, manifest, svc["reme-dynamic"], svc["reme-dynamic-verifier"], str(custody["reme_dynamic_semantic_sha256"])); dynamic.restore_latest()
            for position, task in enumerate(manifest["evaluation"]["task_ids"], 1):
                base._runtime_checkpoint(run, manifest, f"task-{position:04d}-before-open"); base.guard(manifest, run, "task")
                for arm in FOUR_ARMS:
                    for trial, seed in enumerate(manifest["evaluation"]["seeds"], 1):
                        key = (task, arm, trial, seed); path = run / "artifacts" / task / arm / f"trial-{trial}.json"
                        if key in source_records:
                            source_path = Path(source_records[key]["path"]); row = _load(source_path); validate_execution_evidence(row, run_root=_source_root(source_path), expected_registry_sha256=registry["registry_sha256"]); continue
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
            base._runtime_checkpoint(run, manifest, "terminal"); base.summary(run, manifest, state="completed", final=False); _validate_completion(run, manifest, custody)
            if dynamic.reconcile()["completed_count"] != len(base._dynamic_order(manifest)): raise RuntimeError("Dynamic checkpoint continuation incomplete")
            parallel._terminal_check(run, manifest)
            terminal = {"version": "four-arm-terminal-v2", "manifest_sha256": base.file_sha(run / "manifest.json"), "custody_sha256": custody["record_sha256"], "artifact_inventory_sha256": base._inventory_hash(run / "artifacts"), "ledger_sha256": base.file_sha(run / "ledger.jsonl"), "reme_dynamic_checkpoint_chain_sha256": base._inventory_hash(run / "reme-dynamic-checkpoints")}; terminal["record_sha256"] = _digest(terminal); write_json(run / "terminal-reconciliation.json", terminal); base.st(run, "completed", manifest_sha256=terminal["manifest_sha256"], terminal_reconciliation_sha256=terminal["record_sha256"])
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
    elif args.command == "preflight": configure(run_path); base.load(run_path); write_json(run_path / "provider-route-preflight.json", verify_locked_chat_route_available()); base.st(run_path, "preflight_passed")
    else: run(run_path)

if __name__ == "__main__": main()
