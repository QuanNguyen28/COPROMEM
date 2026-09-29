"""Versioned, fail-closed scored-artifact execution-evidence contract.

This is the one vocabulary used by the producer, reconciliation, reporting,
and restart boundaries.  It deliberately validates the durable journal binding
without reading task content.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from collections.abc import Mapping
from typing import Any


VERSION = "scored-execution-evidence-v1"
PATH = "execution_evidence_path"
HASH = "execution_evidence_sha256"
ROWS = "execution_evidence_rows"
REGISTRY = "execution_evidence_registry_sha256"
RELATIVE = "execution_evidence_run_relative"
VERSION_FIELD = "execution_evidence_contract_version"
ZERO_ACTION = "zero_action_evidence"
SCORER = "official_scorer_evidence"
FIELDS = frozenset({PATH, HASH, ROWS, REGISTRY, RELATIVE, VERSION_FIELD})
ZERO_ACTION_VERSION = "canonical-zero-action-evidence-v1"
ZERO_ACTION_TERMINATIONS = frozenset({"truncation_termination"})


class EvidenceContractError(RuntimeError):
    """A scored artifact is not safely bound to its execution journal."""


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise EvidenceContractError(f"duplicate scored-artifact field: {key}")
        value[key] = item
    return value


def load_artifact(path: pathlib.Path) -> dict[str, Any]:
    """Load one artifact while rejecting duplicate JSON object keys."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicates)
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceContractError("scored artifact is unreadable") from exc
    if not isinstance(value, dict):
        raise EvidenceContractError("scored artifact has the wrong shape")
    return value


def _relative(path: pathlib.Path, run_root: pathlib.Path) -> str:
    try:
        return str(path.relative_to(run_root.resolve()))
    except ValueError as exc:
        raise EvidenceContractError("execution-evidence journal escapes the run root") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def _ledger_settlement(run_root: pathlib.Path, call_id: str) -> dict[str, Any]:
    """Return exactly one durable executor settlement without accepting ambiguity."""
    ledger = run_root / "ledger.jsonl"
    try:
        rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceContractError("zero-action ledger is unreadable") from exc
    settled = [row for row in rows if row.get("event") == "settle" and row.get("id") == call_id]
    reserved = [row for row in rows if row.get("event") == "reserve" and row.get("id") == call_id]
    if len(reserved) != 1 or len(settled) != 1:
        raise EvidenceContractError("zero-action executor settlement is missing or ambiguous")
    role = str(settled[0].get("role") or reserved[0].get("role") or "")
    if not role.startswith("executor:"):
        raise EvidenceContractError("zero-action settlement is not an executor call")
    return settled[0]


def _terminal_progress(run_root: pathlib.Path, call_id: str) -> dict[str, Any]:
    try:
        rows = [json.loads(line) for line in (run_root / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceContractError("zero-action progress is unreadable") from exc
    matches = [row for row in rows if row.get("event") == "call_settled" and row.get("id") == call_id]
    if len(matches) != 1:
        raise EvidenceContractError("zero-action terminal progress is missing or ambiguous")
    record = matches[0]
    if record.get("finish_reason") != "length" or int(record.get("completion_tokens") or 0) != 2048:
        raise EvidenceContractError("zero-action progress is not the registered token-ceiling terminal")
    if bool(record.get("tool_call_present")) or not isinstance(record.get("content_sha256"), str):
        raise EvidenceContractError("zero-action progress contains a callable or no output hash")
    return record


def _scorer_evidence(path: pathlib.Path, *, trajectory_id: str, score: Any, task_id: str | None = None,
                     require_zero_actions: bool = False) -> dict[str, Any]:
    """Verify the durable AppWorld score record without exporting its payload."""
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceContractError("zero-action scorer evidence is unreadable") from exc
    submitted = [row for row in rows if row.get("event") == "action_submitted"]
    scores = [row for row in rows if row.get("event") == "official_score"]
    if (require_zero_actions and submitted) or len(scores) != 1 or scores[0].get("trajectory_id") != trajectory_id:
        raise EvidenceContractError("zero-action scorer evidence is inconsistent")
    if task_id is not None and scores[0].get("task_id") != task_id:
        raise EvidenceContractError("scorer task identity differs from artifact")
    observed = int(scores[0].get("pass_count", 0)) / max(1, int(scores[0].get("pass_count", 0)) + int(scores[0].get("fail_count", 0)))
    if float(score) != observed:
        raise EvidenceContractError("zero-action scorer result differs from artifact")
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "pass_count": int(scores[0].get("pass_count", 0)), "fail_count": int(scores[0].get("fail_count", 0)),
            "official_score": observed, "trajectory_id": trajectory_id, "task_id": scores[0].get("task_id")}


def bind(*, journal: pathlib.Path, run_root: pathlib.Path, registry_sha256: str,
         scorer_journal: pathlib.Path | None = None, trajectory_id: str | None = None,
         task_id: str | None = None, after_score: float | None = None,
         history_sha256: str | None = None) -> dict[str, Any]:
    """Return the canonical evidence fields after a durable journal write."""
    run_root = run_root.resolve()
    journal = journal.resolve()
    if not journal.is_absolute() or not journal.is_file():
        raise EvidenceContractError("execution-evidence journal is not an absolute durable file")
    payload = journal.read_bytes()
    if not payload:
        raise EvidenceContractError("execution-evidence journal is empty")
    if not isinstance(registry_sha256, str) or not registry_sha256:
        raise EvidenceContractError("execution-evidence registry identity is absent")
    result = {
        PATH: str(journal),
        HASH: hashlib.sha256(payload).hexdigest(),
        ROWS: len(payload.splitlines()),
        REGISTRY: registry_sha256,
        RELATIVE: _relative(journal, run_root),
        VERSION_FIELD: VERSION,
    }
    if scorer_journal is not None:
        if trajectory_id is None or task_id is None or after_score is None or history_sha256 is None:
            raise EvidenceContractError("ordinary scorer binding lacks artifact identity")
        scorer = _scorer_evidence(scorer_journal, trajectory_id=trajectory_id, task_id=task_id, score=after_score)
        result[SCORER] = {"path": scorer["path"], "sha256": scorer["sha256"],
                          "trajectory_id": trajectory_id, "task_id": task_id,
                          "pass_count": scorer["pass_count"], "fail_count": scorer["fail_count"],
                          "official_score": scorer["official_score"], "history_sha256": history_sha256}
    return result


def bind_zero_action(*, journal: pathlib.Path, scorer_journal: pathlib.Path, run_root: pathlib.Path,
                     registry_sha256: str, trajectory_id: str, after_score: float,
                     termination: str, executor_record: Mapping[str, Any],
                     manifest_sha256: str, source_commit: str) -> dict[str, Any]:
    """Bind the sole permitted empty telemetry journal outcome.

    This is deliberately restricted to a settled, length-truncated executor
    response with no tool call or submitted AppWorld program.  It does not turn
    arbitrary empty journals into evidence.
    """
    run_root, journal, scorer_journal = run_root.resolve(), journal.resolve(), scorer_journal.resolve()
    payload = journal.read_bytes() if journal.is_file() else None
    if payload != b"":
        raise EvidenceContractError("zero-action journal must exist and be empty")
    if termination not in ZERO_ACTION_TERMINATIONS:
        raise EvidenceContractError("zero-action termination is not registered")
    call_id = executor_record.get("id")
    if not isinstance(call_id, str) or not call_id or executor_record.get("finish_reason") != "length":
        raise EvidenceContractError("zero-action executor terminal record is invalid")
    if int(executor_record.get("completion_tokens") or 0) != 2048 or bool(executor_record.get("tool_call_present")):
        raise EvidenceContractError("zero-action executor record has tools or no completion")
    output_hash = executor_record.get("content_sha256")
    if not isinstance(output_hash, str) or len(output_hash) != 64:
        raise EvidenceContractError("zero-action output hash is invalid")
    settlement = _ledger_settlement(run_root, call_id)
    terminal = _terminal_progress(run_root, call_id)
    if terminal.get("content_sha256") != output_hash:
        raise EvidenceContractError("zero-action terminal output hash differs from progress")
    scorer = _scorer_evidence(scorer_journal, trajectory_id=trajectory_id, score=after_score, require_zero_actions=True)
    evidence = {
        "version": ZERO_ACTION_VERSION, "trajectory_id": trajectory_id,
        "executor_settlement_id": call_id, "executor_settlement_sha256": _digest(settlement),
        "executor_terminal_progress_sha256": _digest(terminal),
        "model_output_sha256": output_hash, "termination": termination,
        "submitted_action_count": 0, "tool_call_present": False,
        "callable_event_count": 0, "scorer_evidence_path": scorer["path"],
        "scorer_evidence_sha256": scorer["sha256"], "official_score": float(after_score),
        "manifest_sha256": manifest_sha256, "source_commit": source_commit,
    }
    evidence["binding_sha256"] = _digest(evidence)
    return {PATH: str(journal), HASH: hashlib.sha256(payload).hexdigest(), ROWS: 0,
            REGISTRY: registry_sha256, RELATIVE: _relative(journal, run_root),
            VERSION_FIELD: VERSION, ZERO_ACTION: evidence}


def _validate_zero_action(row: Mapping[str, Any], *, run_root: pathlib.Path) -> None:
    evidence = row.get(ZERO_ACTION)
    if not isinstance(evidence, Mapping) or evidence.get("version") != ZERO_ACTION_VERSION:
        raise EvidenceContractError("empty journal lacks canonical zero-action evidence")
    copy = dict(evidence); binding = copy.pop("binding_sha256", None)
    if not isinstance(binding, str) or binding != _digest(copy):
        raise EvidenceContractError("zero-action evidence binding hash mismatch")
    if evidence.get("trajectory_id") != row.get("trajectory_id") or evidence.get("termination") not in ZERO_ACTION_TERMINATIONS:
        raise EvidenceContractError("zero-action trajectory or termination mismatch")
    if evidence.get("submitted_action_count") != 0 or evidence.get("tool_call_present") is not False or evidence.get("callable_event_count") != 0:
        raise EvidenceContractError("zero-action evidence contains action or callable telemetry")
    if evidence.get("official_score") != float(row.get("after_score")):
        raise EvidenceContractError("zero-action score mismatch")
    manifest = run_root / "manifest.json"
    if not manifest.is_file() or evidence.get("manifest_sha256") != hashlib.sha256(manifest.read_bytes()).hexdigest():
        raise EvidenceContractError("zero-action manifest binding mismatch")
    try:
        manifest_commit = str(json.loads(manifest.read_text(encoding="utf-8")).get("git_commit") or "")
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceContractError("zero-action manifest is unreadable") from exc
    if not manifest_commit or evidence.get("source_commit") != manifest_commit:
        raise EvidenceContractError("zero-action source-commit binding mismatch")
    settlement = _ledger_settlement(run_root, str(evidence.get("executor_settlement_id") or ""))
    if evidence.get("executor_settlement_sha256") != _digest(settlement):
        raise EvidenceContractError("zero-action settlement hash mismatch")
    terminal = _terminal_progress(run_root, str(evidence.get("executor_settlement_id") or ""))
    if (evidence.get("executor_terminal_progress_sha256") != _digest(terminal) or
            evidence.get("model_output_sha256") != terminal.get("content_sha256")):
        raise EvidenceContractError("zero-action terminal progress hash mismatch")
    scorer = _scorer_evidence(pathlib.Path(str(evidence.get("scorer_evidence_path") or "")),
                              trajectory_id=str(row.get("trajectory_id") or ""), score=row.get("after_score"))
    if scorer["sha256"] != evidence.get("scorer_evidence_sha256"):
        raise EvidenceContractError("zero-action scorer hash mismatch")


def _validate_scorer_binding(row: Mapping[str, Any]) -> None:
    binding = row.get(SCORER)
    if not isinstance(binding, Mapping):
        raise EvidenceContractError("ordinary scored artifact lacks official scorer binding")
    path = pathlib.Path(str(binding.get("path") or ""))
    scorer = _scorer_evidence(path, trajectory_id=str(row.get("trajectory_id") or ""),
                              task_id=str(row.get("task_id") or ""), score=row.get("after_score"))
    for field in ("sha256", "pass_count", "fail_count", "official_score", "trajectory_id", "task_id"):
        if binding.get(field) != scorer.get(field):
            raise EvidenceContractError("ordinary scorer binding mismatch")
    if binding.get("history_sha256") != row.get("history_sha256"):
        raise EvidenceContractError("ordinary scorer binding history mismatch")


def validate(row: Mapping[str, Any], *, run_root: pathlib.Path,
             expected_registry_sha256: str | None = None) -> pathlib.Path:
    """Validate and return the canonical journal path without modifying state."""
    if row.get(VERSION_FIELD) != VERSION:
        raise EvidenceContractError("scored artifact execution-evidence contract version mismatch")
    if any(field not in row for field in FIELDS):
        raise EvidenceContractError("scored artifact has missing execution-evidence binding fields")
    raw_path = row.get(PATH)
    if not isinstance(raw_path, str) or not raw_path:
        raise EvidenceContractError("scored artifact has no absolute execution-evidence path")
    journal = pathlib.Path(raw_path)
    if not journal.is_absolute() or not journal.is_file():
        raise EvidenceContractError("scored artifact execution-evidence journal is absent")
    payload = journal.read_bytes()
    empty = not payload
    if empty:
        _validate_zero_action(row, run_root=run_root)
    elif ZERO_ACTION in row:
        raise EvidenceContractError("ordinary execution evidence must not carry zero-action proof")
    elif SCORER in row:
        _validate_scorer_binding(row)
    if row.get(HASH) != hashlib.sha256(payload).hexdigest():
        raise EvidenceContractError("scored artifact execution-evidence hash mismatch")
    if not isinstance(row.get(ROWS), int) or row[ROWS] != len(payload.splitlines()) or (row[ROWS] <= 0 and not empty):
        raise EvidenceContractError("scored artifact execution-evidence row count mismatch")
    registry = row.get(REGISTRY)
    if not isinstance(registry, str) or not registry:
        raise EvidenceContractError("scored artifact lacks execution-evidence registry identity")
    if expected_registry_sha256 is not None and registry != expected_registry_sha256:
        raise EvidenceContractError("scored artifact execution-evidence registry differs from the frozen registry")
    if not isinstance(row.get(RELATIVE), str) or row[RELATIVE] != _relative(journal, run_root):
        raise EvidenceContractError("scored artifact execution-evidence locator mismatch")
    return journal
