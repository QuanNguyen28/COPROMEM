"""Content-addressed custody for ReasoningBank recovery imports.

The recovery marker references immutable predecessor evidence.  It never
copies or rewrites that evidence into the successor run.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from copromem.experiments.reme_copromem.evidence_contract import validate as validate_evidence


VERSION = "reasoningbank-recovery-import-v2"
MARKER_VERSION = "reasoningbank-recovery-import-marker-v2"


class RecoveryIntegrityError(RuntimeError):
    """Raised when immutable predecessor custody cannot be established."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecoveryIntegrityError(f"invalid JSON evidence: {path.name}") from exc
    if not isinstance(value, dict):
        raise RecoveryIntegrityError(f"JSON evidence is not an object: {path.name}")
    return value


def _manifest_runtime_identity(manifest: Mapping[str, Any], manifest_sha256: str) -> dict[str, Any]:
    """Build the strongest honest identity available for a legacy run.

    Engineering 002 predates a standalone runtime-identity file.  Its frozen
    manifest nevertheless binds the executable commit and all scientific
    runtime inputs.  The version label makes that limitation explicit rather
    than presenting the reconstruction as a contemporaneous runtime dump.
    """
    body = {
        "version": "reasoningbank-manifest-bound-legacy-runtime-identity-v1",
        "source_manifest_sha256": manifest_sha256,
        "executable_source_commit": str(manifest.get("git_commit") or ""),
        "protocol_sha256": str(manifest.get("protocol_sha256") or ""),
        "registry_sha256": str(manifest.get("registry_sha256") or ""),
        "initial_bank_sha256": str(manifest.get("initial_bank_sha256") or ""),
        "execution_sha256": digest(manifest.get("execution")),
        "embedding_sha256": digest(manifest.get("embedding")),
        "upstream_commit": str((manifest.get("protocol") or {}).get("upstream_commit") or ""),
    }
    if not all((body["executable_source_commit"], body["protocol_sha256"], body["registry_sha256"],
                body["initial_bank_sha256"], body["upstream_commit"])):
        raise RecoveryIntegrityError("legacy manifest lacks a required runtime identity component")
    return {**body, "runtime_identity_sha256": digest(body)}


def _scorer_binding(row: Mapping[str, Any], source_run: Path) -> dict[str, Any]:
    evidence = row.get("official_scorer_evidence")
    if not isinstance(evidence, Mapping):
        zero = row.get("zero_action_evidence")
        if not isinstance(zero, Mapping) or not isinstance(zero.get("scorer_evidence_sha256"), str):
            raise RecoveryIntegrityError("artifact lacks a canonical scorer evidence binding")
        return {"variant": "zero_action", "scorer_evidence_sha256": zero["scorer_evidence_sha256"],
                "binding_sha256": digest(zero)}
    path_text = evidence.get("path")
    if not isinstance(path_text, str) or not path_text:
        raise RecoveryIntegrityError("ordinary scorer evidence path is absent")
    path = Path(path_text)
    if os.name != "posix" and path_text.startswith("/mnt/"):
        parts = path_text.split("/")
        path = Path(parts[2].upper() + ":/", *parts[3:])
    if not path.is_absolute() or not path.is_file():
        raise RecoveryIntegrityError("ordinary scorer evidence file is unavailable")
    try:
        relative = path.resolve().relative_to(source_run.resolve()).as_posix()
    except ValueError as exc:
        raise RecoveryIntegrityError("scorer evidence is outside its source run") from exc
    return {"variant": "ordinary", "scorer_evidence_sha256": str(evidence.get("sha256") or ""),
            "scorer_binding_sha256": digest(evidence), "scorer_journal_relative": relative,
            "scorer_journal_file_sha256": file_sha256(path)}


def _ledger_binding(ledger_path: Path, *, role: str) -> dict[str, Any]:
    raw_lines = ledger_path.read_bytes().splitlines()
    ordered: list[dict[str, Any]] = []
    all_ids: list[str] = []
    for index, raw in enumerate(raw_lines):
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RecoveryIntegrityError("source ledger contains malformed JSON") from exc
        if not isinstance(record, Mapping):
            raise RecoveryIntegrityError("source ledger contains a non-object record")
        if str(record.get("role") or "") != role:
            continue
        event = str(record.get("event") or "")
        if event not in {"reserve", "settle"}:
            raise RecoveryIntegrityError("executor ledger interval contains an unexpected event")
        call_id = str(record.get("id") or "")
        if not call_id:
            raise RecoveryIntegrityError("executor ledger record lacks a call ID")
        all_ids.append(call_id)
        ordered.append({"ledger_line_index": index, "event": event, "id": call_id,
                        "record_sha256": hashlib.sha256(raw).hexdigest()})
    reserves = [item["id"] for item in ordered if item["event"] == "reserve"]
    settlements = [item["id"] for item in ordered if item["event"] == "settle"]
    if not reserves or len(reserves) != len(set(reserves)) or len(settlements) != len(set(settlements)):
        raise RecoveryIntegrityError("executor ledger IDs are absent or duplicated")
    if set(reserves) != set(settlements):
        raise RecoveryIntegrityError("executor reservations and settlements do not reconcile")
    return {"source_ledger_file_sha256": file_sha256(ledger_path),
            "executor_role": role, "ordered_executor_records": ordered,
            "ordered_reservation_ids": reserves, "ordered_settlement_ids": settlements,
            "executor_record_inventory_sha256": digest(ordered)}


def build_envelope(source_run: Path, *, task_id: str, arm: str, trial_id: int, seed: int) -> dict[str, Any]:
    source = source_run.resolve()
    manifest_path = source / "manifest.json"
    manifest_hash_path = source / "manifest.sha256"
    if not manifest_path.is_file() or not manifest_hash_path.is_file():
        raise RecoveryIntegrityError("source manifest custody is incomplete")
    manifest_sha = file_sha256(manifest_path)
    if manifest_hash_path.read_text(encoding="utf-8").strip() != manifest_sha:
        raise RecoveryIntegrityError("source manifest is hash-inconsistent")
    manifest = _read_json(manifest_path)
    if task_id not in manifest.get("evaluation", {}).get("task_ids", ()) or arm not in manifest.get("arms", ()):
        raise RecoveryIntegrityError("imported key is outside the frozen source allocation")
    seeds = list(manifest.get("evaluation", {}).get("seeds", ()))
    if trial_id < 1 or trial_id > len(seeds) or int(seeds[trial_id - 1]) != seed:
        raise RecoveryIntegrityError("imported trial/seed is outside the frozen source allocation")
    task_position = list(manifest["evaluation"]["task_ids"]).index(task_id)
    arm_position = list(manifest["arms"]).index(arm)
    successor_position = (task_position * len(manifest["arms"]) * len(seeds)
                          + arm_position * len(seeds) + trial_id - 1)
    artifact_path = source / "artifacts" / task_id / arm / f"trial-{trial_id}.json"
    row = _read_json(artifact_path)
    # The immutable artifact records the Linux worker's absolute E-backed
    # locator.  A Windows-side read-only audit uses its already-bound relative
    # locator without rewriting the source artifact.
    validation_row = json.loads(json.dumps(row))
    if os.name != "posix" and str(row.get("execution_evidence_path") or "").startswith("/mnt/"):
        validation_row["execution_evidence_path"] = str(source / str(row["execution_evidence_run_relative"]))
        validation_row["execution_evidence_run_relative"] = str(Path(str(row["execution_evidence_run_relative"])))
        scorer = validation_row.get("official_scorer_evidence")
        if isinstance(scorer, dict) and str(scorer.get("path") or "").startswith("/mnt/"):
            scorer_path = str(scorer["path"])
            parts = scorer_path.split("/")
            scorer["path"] = str(Path(parts[2].upper() + ":/", *parts[3:]))
    validate_evidence(validation_row, run_root=source, expected_registry_sha256=str(manifest["registry_sha256"]))
    expected_identity = (task_id, arm, trial_id, seed)
    observed_identity = (row.get("task_id"), row.get("arm"), row.get("trial_id"), row.get("seed"))
    if observed_identity != expected_identity:
        raise RecoveryIntegrityError("artifact identity differs from the frozen import key")
    journal_text = row.get("execution_evidence_path")
    if not isinstance(journal_text, str) or not journal_text:
        raise RecoveryIntegrityError("artifact execution-evidence path is absent")
    journal = Path(journal_text)
    if os.name != "posix" and journal_text.startswith("/mnt/"):
        parts = journal_text.split("/")
        journal = Path(parts[2].upper() + ":/", *parts[3:])
    if not journal.is_absolute() or not journal.is_file():
        raise RecoveryIntegrityError("artifact execution-evidence journal is unavailable")
    if file_sha256(journal) != row.get("execution_evidence_sha256"):
        raise RecoveryIntegrityError("artifact execution-evidence journal hash mismatch")
    role = f"executor:{arm}:{task_id}:trial={trial_id}:seed={seed}"
    body = {
        "version": VERSION,
        "source_run_identity": source.name,
        "source_manifest_sha256": manifest_sha,
        "source_executable_commit": str(manifest["git_commit"]),
        "source_runtime_identity": _manifest_runtime_identity(manifest, manifest_sha),
        "source_registry_sha256": str(manifest["registry_sha256"]),
        "source_artifact_relative": artifact_path.relative_to(source).as_posix(),
        "source_artifact_file_sha256": file_sha256(artifact_path),
        "source_history_sha256": str(row["history_sha256"]),
        "source_journal_relative": journal.resolve().relative_to(source).as_posix(),
        "source_journal_file_sha256": file_sha256(journal),
        "source_journal_rows": int(row["execution_evidence_rows"]),
        "source_scorer": _scorer_binding(row, source),
        "source_ledger": _ledger_binding(source / "ledger.jsonl", role=role),
        "key": {"task_id": task_id, "arm": arm, "trial_id": trial_id, "seed": seed,
                "trajectory_id": str(row["trajectory_id"])},
        "result": {"official_score": float(row["after_score"]), "actions": int(row["actions"]),
                   "termination": str(row["termination"])},
        "successor_allocation_position": successor_position,
    }
    return {**body, "envelope_sha256": digest(body)}


def validate_envelope(expected: Mapping[str, Any], source_run: Path) -> dict[str, Any]:
    key = expected.get("key")
    if not isinstance(key, Mapping):
        raise RecoveryIntegrityError("frozen recovery envelope has no key")
    actual = build_envelope(source_run, task_id=str(key.get("task_id")), arm=str(key.get("arm")),
                            trial_id=int(key.get("trial_id")), seed=int(key.get("seed")))
    if dict(expected) != actual:
        raise RecoveryIntegrityError("source evidence differs from the frozen recovery envelope")
    return actual


def _validate_marker_value(value: Mapping[str, Any], expected: Mapping[str, Any]) -> dict[str, Any]:
    copy = dict(value)
    marker_hash = copy.pop("record_sha256", None)
    if marker_hash != digest(copy):
        raise RecoveryIntegrityError("recovery import marker content hash is invalid")
    if value.get("version") != MARKER_VERSION or value.get("transition") != "recovery_import_completed":
        raise RecoveryIntegrityError("recovery import marker type is invalid")
    if value.get("envelope") != dict(expected) or value.get("envelope_sha256") != expected.get("envelope_sha256"):
        raise RecoveryIntegrityError("recovery import marker does not equal its frozen envelope")
    return dict(value)


def publish_marker(path: Path, *, envelope: Mapping[str, Any]) -> dict[str, Any]:
    temporary = path.with_suffix(path.suffix + ".tmp")
    if path.exists():
        return _validate_marker_value(_read_json(path), envelope)
    if temporary.exists():
        raise RecoveryIntegrityError("partial recovery import marker exists")
    payload: dict[str, Any] = {"version": MARKER_VERSION, "transition": "recovery_import_completed",
                              "envelope_sha256": envelope.get("envelope_sha256"),
                              "envelope": dict(envelope)}
    payload["record_sha256"] = digest(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, path)
    return _validate_marker_value(_read_json(path), envelope)


def load_marker(path: Path, *, envelope: Mapping[str, Any]) -> dict[str, Any]:
    if not path.is_file():
        raise RecoveryIntegrityError("recovery import marker is absent")
    return _validate_marker_value(_read_json(path), envelope)
