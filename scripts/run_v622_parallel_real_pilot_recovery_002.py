#!/usr/bin/env python3
"""Hash-bound continuation of the nine scored trajectories from real pilot 001.

The predecessor remains immutable.  This entry point copies its exact
artifact/journal/scorer bytes through an atomic recovery marker, restores the
three completed ReMe Dynamic checkpoints read-only, and admits only the next
registered ReasoningBank trajectory.  It never replays a predecessor call.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import sys
import time
from decimal import Decimal
from typing import Any, Mapping

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
os.environ.setdefault("COPROMEM_EVALUATION_RUNNER", str(pathlib.Path(__file__).resolve()))

from copromem.experiments.reme_copromem.recovery_import import (
    RecoveryImportError, canonical_sha256, copy_evidence_file, file_sha256,
    import_scored_artifact, publish_atomic_import,
)
from copromem.experiments.reme_copromem.runner import AppendOnlyLedger, write_json
from copromem.experiments.reme_copromem.runtime_identity_v3 import build_evaluation_identity_v3
from scripts import run_v61_exploratory_evaluation as base
from scripts import run_v622_parallel_real_pilot as real


PROTOCOL = "v6.2.2-real-pilot-100-recovery-002-v1"
# The clean detached runtime may live outside the review worktree; predecessor
# artifacts are deliberately addressed through the same explicit E-backed
# review root used by the real-pilot entry point.
SOURCE_RUN = real.parallel.REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_2_2_real_pilot_100_001"
PREFIX_COUNT = 9
PREFIX_NAME = "recovery-prefix.json"
IMPORT_MARKER = "recovery_import_complete.json"
PREEXISTING = {
    real.ALLOCATION_NAME, "custody-audit.json", "engineering-protocol.json",
    "recovery-amendment.json",
}
# ``run_v61_exploratory_evaluation`` and the ledger reconciler use this
# canonical identifier.  A recovery must use the same single carry record;
# writing a recovery-specific alias would make the base runner append a second
# carry and correctly fail closed.
HISTORICAL_CARRY_ID = "historical-construction-carry"


def _load(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecoveryImportError(f"unreadable recovery evidence: {path.name}") from exc
    if not isinstance(value, dict):
        raise RecoveryImportError(f"recovery evidence has wrong shape: {path.name}")
    return value


def _ledger_rows(root: pathlib.Path) -> list[dict[str, Any]]:
    path = root / "ledger.jsonl"
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    except (OSError, json.JSONDecodeError) as exc:
        raise RecoveryImportError("source ledger is unreadable") from exc
    if not all(isinstance(row, dict) for row in rows):
        raise RecoveryImportError("source ledger contains a non-object row")
    return rows


def _source_manifest() -> tuple[dict[str, Any], str]:
    path = SOURCE_RUN / "manifest.json"
    value = _load(path)
    if file_sha256(path) != (SOURCE_RUN / "manifest.sha256").read_text(encoding="utf-8").strip():
        raise RecoveryImportError("source manifest hash mismatch")
    if value.get("evaluation", {}).get("expected_trajectories") != 1800:
        raise RecoveryImportError("source denominator is not 1,800")
    if value.get("protocol") != real.PROTOCOL:
        raise RecoveryImportError("source protocol is not the real pilot 001 protocol")
    return value, file_sha256(path)


def _expected_prefix(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    tasks = list(manifest["evaluation"]["task_ids"])
    seeds = list(manifest["evaluation"]["seeds"])
    arms = list(manifest["arms"])
    if not tasks or len(seeds) != 3 or list(arms) != list(real.ARMS):
        raise RecoveryImportError("source schedule differs from the frozen real-pilot schedule")
    first = str(tasks[0]); out: list[dict[str, Any]] = []
    for arm in arms:
        for trial, seed in enumerate(seeds, 1):
            out.append({"task_id": first, "arm": str(arm), "trial_id": trial, "seed": int(seed)})
    return out[:PREFIX_COUNT]


def _source_prefix() -> tuple[dict[str, Any], str, list[dict[str, Any]], Decimal, set[str]]:
    manifest, manifest_sha = _source_manifest()
    expected = _expected_prefix(manifest)
    observed: list[dict[str, Any]] = []
    for item in expected:
        path = SOURCE_RUN / "artifacts" / item["task_id"] / item["arm"] / f"trial-{item['trial_id']}.json"
        row = _load(path)
        if any(row.get(key) != value for key, value in item.items()):
            raise RecoveryImportError("source artifact does not match the frozen prefix identity")
        if not isinstance(row.get("trajectory_id"), str) or not row["trajectory_id"]:
            raise RecoveryImportError("source artifact has no trajectory identity")
        if not isinstance(row.get("execution_evidence_path"), str) or not isinstance(row.get("official_scorer_evidence"), Mapping):
            raise RecoveryImportError("source artifact lacks ordinary evidence bindings")
        observed.append({"identity": item, "path": path, "sha256": file_sha256(path), "trajectory_id": row["trajectory_id"]})
    extra = sorted((SOURCE_RUN / "artifacts").glob("**/trial-*.json"))
    if len(extra) != PREFIX_COUNT or len({item["trajectory_id"] for item in observed}) != PREFIX_COUNT:
        raise RecoveryImportError("source scored prefix is incomplete, duplicate, or contains extra artifacts")
    rows = _ledger_rows(SOURCE_RUN)
    reserve = {str(row.get("id")) for row in rows if row.get("event") == "reserve"}
    settle = {str(row.get("id")) for row in rows if row.get("event") == "settle"}
    if not reserve or reserve != settle:
        raise RecoveryImportError("source ledger has unresolved or unmatched calls")
    exposure = sum((Decimal(str(row.get("usd", 0))) for row in rows if row.get("event") == "settle"), Decimal("0"))
    dynamic_ids = {str(row["id"]) for row in rows if row.get("event") == "settle" and str(row.get("role", "")).startswith(("reme_lifecycle:reme-dynamic", "reme_embedding:reme-dynamic"))}
    if not dynamic_ids:
        raise RecoveryImportError("source ReMe Dynamic settlements are absent")
    return manifest, manifest_sha, observed, exposure, dynamic_ids


def _validate_dynamic_chain() -> list[pathlib.Path]:
    root = SOURCE_RUN / "reme-dynamic-checkpoints"
    required = []
    for index in range(1, 4):
        intent = root / "intents" / f"update-{index:04d}.json"
        marker = root / "markers" / f"update-{index:04d}.json"
        snapshot = root / "snapshots" / f"update-{index:04d}.jsonl"
        if not all(path.is_file() for path in (intent, marker, snapshot, intent.with_suffix(".sha256.json"))):
            raise RecoveryImportError("source ReMe Dynamic prefix is incomplete")
    # Copy every checkpoint file; unknown directories/files are rejection-prone
    # and therefore part of the immutable source inventory rather than ignored.
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise RecoveryImportError("source ReMe Dynamic checkpoint inventory is empty")
    return files


def _configure(run: pathlib.Path, *, historical_exposure: Decimal | None = None) -> None:
    real._configure(run)
    base.PROTOCOL = PROTOCOL
    base.PREEXISTING_RUN_FILES = set(PREEXISTING)
    if historical_exposure is not None:
        base.HISTORICAL_EXPOSURE = float(historical_exposure)


def _copy_preallocation(run: pathlib.Path) -> None:
    for name in (real.ALLOCATION_NAME, "custody-audit.json", "engineering-protocol.json"):
        source = SOURCE_RUN / name
        if not source.is_file():
            raise RecoveryImportError(f"source preallocation record is absent: {name}")
        copy_evidence_file(source, run / name)


def prepare(run: pathlib.Path) -> None:
    source, source_sha, prefix, exposure, _ids = _source_prefix()
    _validate_dynamic_chain()
    run.mkdir(parents=True, exist_ok=True)
    _copy_preallocation(run)
    # ``real.prepare`` deliberately calls its own configurator.  At this
    # point the run must therefore contain only that entry point's three
    # permitted preallocation files.  Recovery records are added immediately
    # afterward and then incorporated into the successor runtime identity.
    real.prepare(run)
    amendment = {
        "version": PROTOCOL,
        "source_run": str(SOURCE_RUN.resolve()),
        "source_manifest_sha256": source_sha,
        "source_ledger_sha256": file_sha256(SOURCE_RUN / "ledger.jsonl"),
        "source_status_sha256": file_sha256(SOURCE_RUN / "runner-status.json"),
        "source_prefix_count": PREFIX_COUNT,
        "source_total_settled_exposure": str(exposure),
        "import_rule": "copy exactly nine scored artifacts through a content-addressed atomic marker; never replay source calls",
        "dynamic_rule": "restore only the three source-completed ReMe Dynamic checkpoints and bind their settlements to the immutable source ledger",
    }
    write_json(run / "recovery-amendment.json", amendment)
    _configure(run, historical_exposure=exposure)
    template_path = run / "template.json"; template = _load(template_path)
    template.update({"protocol": PROTOCOL, "recovery_amendment_sha256": file_sha256(run / "recovery-amendment.json"),
                     "predecessor": {"manifest_sha256": source_sha, "prefix_count": PREFIX_COUNT,
                                     "source_total_settled_exposure": str(exposure), "provider_calls_not_replayed": True}})
    template["budget"]["historical_settled_exposure"] = float(exposure)
    runtime, inputs = build_evaluation_identity_v3(root=ROOT, manifest=template)
    write_json(run / "runtime-identity.json", runtime)
    write_json(run / "runtime-identity.binding.json", {"runtime_identity_sha256": runtime["runtime_identity_sha256"],
               "runtime_identity_record_sha256": file_sha256(run / "runtime-identity.json")})
    template["runtime_identity_inputs"] = inputs; template["runtime_identity_sha256"] = runtime["runtime_identity_sha256"]
    template["runtime_identity_file_sha256"] = file_sha256(run / "runtime-identity.json")
    write_json(template_path, template)


def freeze(run: pathlib.Path) -> None:
    _source, _sha, _prefix, exposure, _ids = _source_prefix()
    _configure(run, historical_exposure=exposure)
    base.freeze(run)


def _install_source_marker_validation(source_ids: set[str]) -> None:
    original = base._validate_marker_settlements
    def validate(path: pathlib.Path, marker: dict[str, Any]) -> None:
        if int(marker.get("ordered_update_index", 0)) <= 3:
            ids = {str(value) for value in marker.get("newly_settled_lifecycle_or_embedding_ids", [])}
            if not ids or not ids.issubset(source_ids):
                raise RecoveryImportError("imported ReMe Dynamic marker has an unbound source settlement")
            return
        original(path, marker)
    base._validate_marker_settlements = validate


def recover(run: pathlib.Path) -> None:
    source, source_sha, prefix, exposure, dynamic_ids = _source_prefix()
    chain = _validate_dynamic_chain()
    _configure(run, historical_exposure=exposure)
    manifest = base.load(run)
    if file_sha256(run / "manifest.json") != (run / "manifest.sha256").read_text(encoding="utf-8").strip():
        raise RecoveryImportError("successor manifest hash mismatch")
    expected_ids = [item["trajectory_id"] for item in prefix]
    # ``prefix`` carries local ``Path`` objects for the importer.  The frozen
    # specification must instead be portable, JSON-serializable custody data;
    # bind only the immutable artifact identities and their byte hashes.
    prefix_inventory = [
        {"identity": item["identity"], "sha256": item["sha256"],
         "trajectory_id": item["trajectory_id"]}
        for item in prefix
    ]
    spec = {"version": PROTOCOL, "source_run": str(SOURCE_RUN.resolve()), "source_manifest_sha256": source_sha,
            "source_ledger_sha256": file_sha256(SOURCE_RUN / "ledger.jsonl"), "successor_manifest_sha256": file_sha256(run / "manifest.json"),
            "expected_trajectory_ids": expected_ids, "source_prefix_artifact_sha256": canonical_sha256(prefix_inventory),
            "source_dynamic_checkpoint_inventory_sha256": canonical_sha256([{"path": str(path.relative_to(SOURCE_RUN)), "sha256": file_sha256(path)} for path in chain])}
    def materialize(staging: pathlib.Path):
        write_json(staging / "recovery-import-spec.json", spec)
        records = []
        for position, item in enumerate(prefix, 1):
            identity = item["identity"]
            target = staging / "artifacts" / identity["task_id"] / identity["arm"] / f"trial-{identity['trial_id']}.json"
            record = import_scored_artifact(source_artifact=item["path"], source_run=SOURCE_RUN, target_artifact=target,
                                            target_run=staging, source_manifest_sha256=source_sha)
            records.append({"trajectory_id": record["trajectory_id"], "position": position,
                            "source_artifact_sha256": record["source_artifact_sha256"], "target_artifact_sha256": record["target_artifact_sha256"],
                            "journal_sha256": record["execution_evidence_sha256"], "scorer_sha256": record["scorer_evidence_sha256"]})
        for path in chain:
            copy_evidence_file(path, staging / "reme-dynamic-checkpoints" / path.relative_to(SOURCE_RUN / "reme-dynamic-checkpoints"))
        prefix_record = {"version": PROTOCOL, "source_manifest_sha256": source_sha,
                         "source_ledger_sha256": spec["source_ledger_sha256"], "source_total_settled_exposure": str(exposure),
                         "imported_trajectory_ids": expected_ids, "dynamic_checkpoint_count": 3,
                         "next": {"task_id": manifest["evaluation"]["task_ids"][0], "arm": real.REASONINGBANK_ARM, "trial_id": 1, "seed": manifest["evaluation"]["seeds"][0]}}
        prefix_record["record_sha256"] = canonical_sha256(prefix_record)
        write_json(staging / PREFIX_NAME, prefix_record)
        return records
    marker = publish_atomic_import(target_run=run, specification=spec, materialize=materialize)
    ledger = AppendOnlyLedger(run / "ledger.jsonl", base.HARD_CAP_USD, manifest["budget"]["call_limits"])
    ledger.reserve(HISTORICAL_CARRY_ID, float(exposure), {"role": "historical_carry_forward"})
    ledger.settle(HISTORICAL_CARRY_ID, float(exposure), {"role": "historical_carry_forward"})
    _install_source_marker_validation(dynamic_ids)
    # Reconciliation validates the restored source checkpoint chain without
    # provider activity; it must expose update 4 as the next Dynamic update.
    base.summary(run, manifest, state="recovery_imported")
    write_json(run / "recovery-admission.json", {"marker_sha256": marker["marker_sha256"], "imported_count": PREFIX_COUNT,
               "next": _load(run / PREFIX_NAME)["next"]})
    base.st(run, "recovery_imported", manifest_sha256=file_sha256(run / "manifest.json"), imported_completed_trajectories=PREFIX_COUNT)


def preflight(run: pathlib.Path) -> None:
    _source, _sha, prefix, exposure, dynamic_ids = _source_prefix()
    _configure(run, historical_exposure=exposure); _install_source_marker_validation(dynamic_ids)
    base.load(run)
    marker = _load(run / IMPORT_MARKER); prefix_record = _load(run / PREFIX_NAME)
    if marker.get("imported_count") != PREFIX_COUNT or prefix_record.get("record_sha256") != canonical_sha256({k: v for k, v in prefix_record.items() if k != "record_sha256"}):
        raise RecoveryImportError("recovery admission marker or prefix record is invalid")
    if marker.get("records") is None or [row.get("trajectory_id") for row in marker["records"]] != [row["trajectory_id"] for row in prefix]:
        raise RecoveryImportError("recovery marker does not bind the exact source prefix")
    base.st(run, "preflight_passed", manifest_sha256=file_sha256(run / "manifest.json"), imported_completed_trajectories=PREFIX_COUNT)


def run(run: pathlib.Path) -> None:
    """Run with a terminal record even for failures before ``base.run``'s try.

    The maintained runner owns its service/executor failure handling, but a
    recovery can also fail while rebuilding its prefix immediately before that
    boundary.  Persist a value-free terminal record in either case so a
    detached launcher cannot leave a misleading ``running`` status.
    """
    try:
        _source, _sha, _prefix, exposure, dynamic_ids = _source_prefix()
        _configure(run, historical_exposure=exposure); _install_source_marker_validation(dynamic_ids)
        preflight(run)
        base.run(run)
    except BaseException as exc:
        failure = {
            "version": PROTOCOL,
            "event": "recovery_runner_failed",
            "failure_class": type(exc).__name__,
            "time_ns": time.time_ns(),
        }
        write_json(run / "recovery-runner-failure.json", failure)
        try:
            manifest_sha = file_sha(run / "manifest.json") if (run / "manifest.json").is_file() else None
            base.st(run, "failed", manifest_sha256=manifest_sha,
                    failure_class=failure["failure_class"])
        except Exception:
            # The durable failure record above is still authoritative if the
            # status writer itself is unavailable.
            pass
        raise


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=["prepare", "freeze", "recover", "preflight", "run"])
    parser.add_argument("--run", required=True, type=pathlib.Path); args = parser.parse_args(); run_root = args.run.resolve()
    {"prepare": prepare, "freeze": freeze, "recover": recover, "preflight": preflight, "run": run}[args.command](run_root)


if __name__ == "__main__":
    main()
