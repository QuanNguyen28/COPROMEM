"""Read-only v6.2 Evaluation-004 prefix validation and atomic import envelopes.

This boundary does not execute a task or call a provider.  It deliberately
keeps source scored artifacts byte-identical and records successor custody in
separate content-addressed envelopes.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
from collections.abc import Mapping
from typing import Any

from .recovery_import import RecoveryImportError, canonical_sha256, copy_evidence_file, file_sha256, publish_atomic_import

VERSION = "v6.2-real-prefix-import-v1"
EXPECTED_TASKS = ("024c982_2", "042a9fc_1")
NEXT = {"task_id": "09b0ee6_1", "arm": "no_memory", "trial_id": 1, "seed": 11001}


def _host_path(raw: str) -> pathlib.Path:
    """Read immutable E-backed source evidence on either Windows or WSL."""
    if raw.startswith("/mnt/e/") and pathlib.Path("E:/").exists():
        return pathlib.Path("E:/" + raw[len("/mnt/e/"):])
    if os.name != "nt" and re.match(r"^[Ee]:[\\/]", raw):
        return pathlib.Path("/mnt/e/" + raw[3:].replace("\\", "/"))
    return pathlib.Path(raw)


def project_legacy_e_backed_path(value: str) -> str:
    """Project one generated E-backed locator to the legacy Windows spelling."""
    if value.startswith("/mnt/e/"):
        return "E:\\" + value[len("/mnt/e/"):].replace("/", "\\")
    return value


def project_legacy_e_backed_paths(value: Any) -> Any:
    """Canonicalize only equivalent E-backed root locators for custody hashes.

    Earlier immutable markers were created by the Windows host and therefore
    used ``E:\\...`` for paths assembled by pathlib.  The production split
    runtime is WSL and sees those same files as ``/mnt/e/...``.  Evidence
    content paths persisted inside artifacts are intentionally untouched; this
    projection applies only to generated artifact, journal, scorer, and root
    locators in custody preimages so either host derives the same legacy
    identity.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return [project_legacy_e_backed_paths(item) for item in value]
    if isinstance(value, dict):
        return {key: (project_legacy_e_backed_path(item) if (key == "source_run" or key.endswith("_path")) and isinstance(item, str)
                      else project_legacy_e_backed_paths(item)) for key, item in value.items()}
    return value


def _load(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecoveryImportError(f"invalid immutable recovery evidence: {path.name}") from exc
    if not isinstance(value, dict):
        raise RecoveryImportError("recovery evidence has wrong object shape")
    return value


def _history_hash(history: Any) -> str:
    return canonical_sha256(history)


def _scorer_identity(row: Mapping[str, Any]) -> tuple[str, str]:
    ordinary, zero = row.get("official_scorer_evidence"), row.get("zero_action_evidence")
    if isinstance(ordinary, Mapping) and isinstance(zero, Mapping):
        raise RecoveryImportError("artifact has conflicting ordinary and zero-action scorer evidence")
    if isinstance(ordinary, Mapping):
        value = ordinary.get("sha256")
        if int(row.get("actions", -1)) == 0:
            raise RecoveryImportError("zero-action artifact must use canonical zero-action scorer evidence")
        if not isinstance(value, str) or len(value) != 64:
            raise RecoveryImportError("ordinary scorer identity is absent")
        path = _host_path(str(ordinary.get("path") or ""))
    elif isinstance(zero, Mapping):
        value = zero.get("scorer_evidence_sha256")
        if int(row.get("actions", -1)) != 0 or zero.get("version") != "canonical-zero-action-evidence-v1":
            raise RecoveryImportError("canonical zero-action scorer evidence is invalid")
        if not isinstance(value, str) or len(value) != 64:
            raise RecoveryImportError("zero-action scorer identity is absent")
        path = _host_path(str(zero.get("scorer_evidence_path") or ""))
    else:
        raise RecoveryImportError("artifact has no canonical scorer identity")
    if not path.is_file() or file_sha256(path) != value:
        raise RecoveryImportError("scorer evidence hash mismatch")
    return str(value), str(path)


def validate_real_prefix(*, source_run: pathlib.Path, expected_manifest_sha256: str,
                         expected_runtime_sha256: str | None = None) -> list[dict[str, Any]]:
    """Return the ordered 20-item envelope inventory after read-only validation."""
    source_run = source_run.resolve(); manifest = source_run / "manifest.json"
    if file_sha256(manifest) != expected_manifest_sha256:
        raise RecoveryImportError("source manifest identity mismatch")
    runtime = source_run / "runtime-identity.json"
    runtime_sha = file_sha256(runtime)
    if expected_runtime_sha256 is not None and runtime_sha != expected_runtime_sha256:
        raise RecoveryImportError("source runtime identity mismatch")
    ledger_rows = [_load_line(line) for line in (source_run / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    reserve = {str(x.get("id")): x for x in ledger_rows if x.get("event") == "reserve"}
    settle = {str(x.get("id")): x for x in ledger_rows if x.get("event") == "settle"}
    if len(reserve) != 268 or len(settle) != 268 or set(reserve) != set(settle):
        raise RecoveryImportError("source ledger is not exactly settled 268/268")
    source_manifest = _load(manifest)
    frozen_tasks = list(source_manifest.get("evaluation", {}).get("task_ids", []))
    frozen_arms = list(source_manifest.get("arms", []))
    frozen_seeds = list(source_manifest.get("evaluation", {}).get("seeds", []))
    raw_artifacts = list((source_run / "artifacts").glob("**/trial-*.json"))
    def order(path: pathlib.Path) -> tuple[int, int, int]:
        row = _load(path)
        try:
            return (frozen_tasks.index(str(row["task_id"])), frozen_seeds.index(int(row["seed"])), frozen_arms.index(str(row["arm"])))
        except (KeyError, ValueError) as exc:
            raise RecoveryImportError("artifact lies outside frozen task/arm/seed ordering") from exc
    artifacts = sorted(raw_artifacts, key=order)
    if len(artifacts) != 20:
        raise RecoveryImportError("source prefix must contain exactly twenty artifacts")
    out: list[dict[str, Any]] = []; seen: set[str] = set()
    for position, path in enumerate(artifacts, 1):
        row = _load(path); identity = str(row.get("trajectory_id") or "")
        if not identity or identity in seen or str(row.get("task_id")) not in EXPECTED_TASKS:
            raise RecoveryImportError("source artifact identity is duplicate or outside the frozen prefix")
        seen.add(identity); history = row.get("history")
        if not isinstance(history, list) or row.get("history_sha256") != _history_hash(history):
            raise RecoveryImportError("source artifact history hash mismatch")
        if int(row.get("actions", -1)) != sum(isinstance(x, dict) and x.get("role") == "assistant" for x in history):
            raise RecoveryImportError("source artifact action count mismatch")
        journal = _host_path(str(row.get("execution_evidence_path") or ""))
        if not journal.is_file() or file_sha256(journal) != row.get("execution_evidence_sha256"):
            raise RecoveryImportError("source execution journal hash mismatch")
        if int(row.get("execution_evidence_rows", -1)) != len(journal.read_bytes().splitlines()):
            raise RecoveryImportError("source execution journal row count mismatch")
        scorer_sha, scorer_path = _scorer_identity(row)
        role = f"executor:{row.get('arm')}:{row.get('task_id')}:trial={row.get('trial_id')}:seed={row.get('seed')}"
        source_for_artifact = source_run
        source_manifest_for_artifact = expected_manifest_sha256
        source_settle = settle
        # Evaluation 004 imported the already scored first task from immutable
        # Evaluation 002 without recharging calls.  Validate that provenance
        # at its original ledger rather than pretending 004 settled it.
        carried = row.get("carried_completed_from")
        if not any(str(x.get("role")) == role for x in source_settle.values()):
            if not isinstance(carried, Mapping):
                raise RecoveryImportError("source executor settlement is absent")
            original = source_run.parent / "v6_2_task_conditioned_evaluation_002"
            original_artifact = original / "artifacts" / str(row["task_id"]) / str(row["arm"]) / f"trial-{row['trial_id']}.json"
            if (not original_artifact.is_file() or file_sha256(original_artifact) != carried.get("source_artifact_sha256")):
                raise RecoveryImportError("carried artifact does not bind its immutable original")
            original_ledger = [_load_line(line) for line in (original / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
            source_settle = {str(x.get("id")): x for x in original_ledger if x.get("event") == "settle"}
            if not any(str(x.get("role")) == role for x in source_settle.values()):
                raise RecoveryImportError("carried source executor settlement is absent")
            source_for_artifact = original
            source_manifest_for_artifact = str(carried.get("source_manifest_sha256") or "")
        out.append({"position": position, "trajectory_id": identity, "artifact_path": str(path),
                    "artifact_sha256": file_sha256(path), "source_manifest_sha256": source_manifest_for_artifact,
                    "source_run": str(source_for_artifact), "source_runtime_sha256": runtime_sha, "source_commit": source_manifest.get("git_commit"),
                    "journal_path": str(journal), "journal_sha256": file_sha256(journal),
                    "scorer_path": scorer_path, "normalized_scorer_sha256": scorer_sha,
                    "registry_sha256": row.get("execution_evidence_registry_sha256"),
                    "identity": {k: row.get(k) for k in ("arm", "task_id", "trial_id", "seed")}})
    return out


def _load_line(line: str) -> dict[str, Any]:
    value = json.loads(line)
    if not isinstance(value, dict): raise RecoveryImportError("ledger row has wrong shape")
    return value


def import_real_prefix(*, target_run: pathlib.Path, source_run: pathlib.Path, expected_manifest_sha256: str,
                       successor_identity: Mapping[str, Any], recovery_bindings: Mapping[str, Any]) -> dict[str, Any]:
    """Materialize source bytes and successor envelopes through one atomic marker."""
    inventory = validate_real_prefix(source_run=source_run, expected_manifest_sha256=expected_manifest_sha256)
    spec = {"version": VERSION, "source_run": project_legacy_e_backed_path(str(source_run.resolve())), "source_manifest_sha256": expected_manifest_sha256,
            "expected_trajectory_ids": [x["trajectory_id"] for x in inventory], "successor_identity": dict(successor_identity),
            "recovery_bindings": dict(recovery_bindings), "inventory_sha256": canonical_sha256(inventory), "next": dict(NEXT)}
    def materialize(staging: pathlib.Path):
        (staging / "recovery-import-spec.json").write_text(
            json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        rows=[]
        for item in inventory:
            artifact_target=staging/"source-artifacts"/f"{item['position']:04d}.json"; journal_target=staging/"source-evidence"/f"{item['position']:04d}.journal.jsonl"; scorer_target=staging/"source-evidence"/f"{item['position']:04d}.scorer.jsonl"
            copy_evidence_file(pathlib.Path(item["artifact_path"]),artifact_target); copy_evidence_file(pathlib.Path(item["journal_path"]),journal_target); copy_evidence_file(pathlib.Path(item["scorer_path"]),scorer_target)
            envelope={"version":VERSION,"source":project_legacy_e_backed_paths(item),"successor_identity":dict(successor_identity),"copied_artifact_sha256":file_sha256(artifact_target),"copied_journal_sha256":file_sha256(journal_target),"copied_scorer_sha256":file_sha256(scorer_target)}; envelope["envelope_sha256"]=canonical_sha256(envelope)
            envelope_path=staging/"import-envelopes"/f"{item['position']:04d}.json"; envelope_path.parent.mkdir(parents=True,exist_ok=True); envelope_path.write_text(json.dumps(envelope,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
            rows.append({"trajectory_id":item["trajectory_id"],"position":item["position"],"envelope_sha256":envelope["envelope_sha256"]})
        return rows
    return publish_atomic_import(target_run=target_run,specification=spec,materialize=materialize)
