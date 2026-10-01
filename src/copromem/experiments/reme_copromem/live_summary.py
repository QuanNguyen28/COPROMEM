"""Pure, fail-closed reconciliation of evaluation ledgers and scored artifacts."""
from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .evidence_contract import EvidenceContractError, load_artifact, validate as validate_execution_evidence


ARMS = frozenset({
    "no_memory", "official_upstream_reme_fixed", "official_upstream_reme_dynamic",
    "copromem_v6_1_fixed", "copromem_v6_1_dynamic",
})
_EXECUTOR = re.compile(r"^executor:([^:]+):([^:]+):trial=(\d+):seed=(\d+)$")
_MONEY = Decimal("0.000000000001")


class LedgerReconciliationError(RuntimeError):
    """The append-only ledger or scored-artifact set is not safe to summarize."""


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _money(value: Any, label: str) -> Decimal:
    if isinstance(value, bool):
        raise LedgerReconciliationError(f"{label} is not a numeric USD value")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise LedgerReconciliationError(f"{label} is malformed") from exc
    if not number.is_finite() or number < 0:
        raise LedgerReconciliationError(f"{label} is negative or non-finite")
    return number.quantize(_MONEY)


def _number(value: Decimal) -> float:
    return float(value.quantize(_MONEY))


def _role_owner(role: str, *, allow_copromem_decomposition: bool,
                registered_arms: frozenset[str] = ARMS) -> tuple[str | None, str]:
    if role == "historical_carry_forward":
        return None, "historical"
    match = _EXECUTOR.fullmatch(role)
    if match:
        arm, _task, trial, seed = match.groups()
        if arm not in registered_arms or int(trial) < 1 or int(seed) < 0:
            raise LedgerReconciliationError("executor role has an unregistered arm or malformed identity")
        return arm, "executor"
    lifecycle = {"reme_lifecycle:reme-fixed": "official_upstream_reme_fixed",
                 "reme_lifecycle:reme-dynamic": "official_upstream_reme_dynamic"}
    embedding = {"reme_embedding:reme-fixed": "official_upstream_reme_fixed",
                 "reme_embedding:reme-dynamic": "official_upstream_reme_dynamic"}
    if role in lifecycle:
        return lifecycle[role], "lifecycle"
    if role in embedding:
        return embedding[role], "embedding"
    # The controlled ReasoningBank-AppWorld port has one online Dynamic bank
    # in its engineering profile.  Judge/extractor calls are lifecycle calls;
    # query/document embeddings use the shared Azure embedding transport.  A
    # future profile that registers a Fixed ReasoningBank arm must introduce a
    # separately owned role rather than silently attributing it here.
    reasoningbank = {"reasoningbank_judge": ("reasoningbank_dynamic", "lifecycle"),
                     "reasoningbank_extraction": ("reasoningbank_dynamic", "lifecycle"),
                     "reasoningbank_embedding": ("reasoningbank_dynamic", "embedding")}
    if role in reasoningbank:
        arm, kind = reasoningbank[role]
        if arm not in registered_arms:
            raise LedgerReconciliationError("ReasoningBank call exists without its registered Dynamic arm")
        return arm, kind
    if role in {"reme_lifecycle:reme-dynamic-verifier", "reme_embedding:reme-dynamic-verifier"}:
        raise LedgerReconciliationError("ReMe Dynamic verifier provider activity is prohibited")
    if role.startswith("copromem_decomposition"):
        if not allow_copromem_decomposition:
            raise LedgerReconciliationError("CoProMem decomposition is forbidden for the frozen v6.1 evaluation")
        raise LedgerReconciliationError("registered CoProMem decomposition ownership is not implemented")
    raise LedgerReconciliationError("ledger contains an unknown provider-call role")


@dataclass(frozen=True)
class LedgerCall:
    call_id: str
    role: str
    arm: str | None
    kind: str
    maximum_usd: Decimal
    settled_usd: Decimal | None
    model: str | None
    provider: str | None


@dataclass(frozen=True)
class LedgerReconciliation:
    calls: tuple[LedgerCall, ...]
    ledger_sha256: str
    historical_settled_exposure: Decimal
    settled_evaluation_cost: Decimal
    reserved_maximum_exposure: Decimal
    unresolved_reservation_ids: tuple[str, ...]

    @property
    def total_ledger_exposure(self) -> Decimal:
        return self.historical_settled_exposure + self.settled_evaluation_cost


def reconcile_ledger(path: pathlib.Path, *, historical_expected_usd: float | Decimal,
                     historical_id: str = "historical-construction-carry",
                     allow_copromem_decomposition: bool = False,
                     registered_arms: Iterable[str] = ARMS) -> LedgerReconciliation:
    """Read the ledger without modifying it and validate every accounting row."""
    if not path.is_file():
        raise LedgerReconciliationError("append-only ledger is absent")
    registered = frozenset(str(arm) for arm in registered_arms)
    if not registered:
        raise LedgerReconciliationError("at least one registered arm is required")
    payload = path.read_bytes()
    reservations: dict[str, dict[str, Any]] = {}
    settlements: dict[str, dict[str, Any]] = {}
    for line_no, raw in enumerate(payload.splitlines(), 1):
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LedgerReconciliationError(f"ledger JSON is malformed at line {line_no}") from exc
        if not isinstance(row, dict) or row.get("event") not in {"reserve", "settle"}:
            raise LedgerReconciliationError(f"ledger event is unknown or malformed at line {line_no}")
        call_id = row.get("id")
        if not isinstance(call_id, str) or not call_id:
            raise LedgerReconciliationError(f"ledger call ID is malformed at line {line_no}")
        _money(row.get("usd"), f"ledger USD at line {line_no}")
        destination = reservations if row["event"] == "reserve" else settlements
        if call_id in destination:
            raise LedgerReconciliationError(f"duplicate {row['event']} record for {call_id}")
        destination[call_id] = row
    if set(settlements) - set(reservations):
        raise LedgerReconciliationError("ledger contains a settlement without its reservation")
    calls: list[LedgerCall] = []
    historical_count = 0
    for call_id, reservation in reservations.items():
        role = reservation.get("role")
        if not isinstance(role, str):
            raise LedgerReconciliationError("ledger reservation lacks a role")
        arm, kind = _role_owner(role, allow_copromem_decomposition=allow_copromem_decomposition,
                                registered_arms=registered)
        maximum = _money(reservation["usd"], "reserved USD")
        settlement = settlements.get(call_id)
        actual: Decimal | None = None
        model = reservation.get("model") if isinstance(reservation.get("model"), str) else None
        provider = reservation.get("provider") if isinstance(reservation.get("provider"), str) else None
        if settlement is not None:
            actual = _money(settlement["usd"], "settled USD")
            if actual > maximum:
                raise LedgerReconciliationError("settled USD exceeds the registered maximum")
            for field in ("role", "model", "provider"):
                left, right = reservation.get(field), settlement.get(field)
                if left is not None and right is not None and left != right:
                    raise LedgerReconciliationError(f"settlement {field} differs from its reservation")
            if isinstance(settlement.get("model"), str): model = settlement["model"]
            if isinstance(settlement.get("provider"), str): provider = settlement["provider"]
        if kind == "historical":
            historical_count += 1
            if call_id != historical_id:
                raise LedgerReconciliationError("unexpected historical carry-forward call ID")
        calls.append(LedgerCall(call_id, role, arm, kind, maximum, actual, model, provider))
    if historical_count != 1:
        raise LedgerReconciliationError("historical carry-forward must occur exactly once")
    historical = sum((call.settled_usd or Decimal(0) for call in calls if call.kind == "historical"), Decimal(0))
    expected = _money(historical_expected_usd, "manifest historical exposure")
    if historical != expected:
        raise LedgerReconciliationError("historical carry-forward differs from the manifest-pinned exposure")
    evaluation = sum((call.settled_usd or Decimal(0) for call in calls if call.kind != "historical"), Decimal(0))
    maximum = sum((call.maximum_usd for call in calls), Decimal(0))
    unresolved = tuple(sorted(call.call_id for call in calls if call.settled_usd is None))
    return LedgerReconciliation(tuple(sorted(calls, key=lambda call: call.call_id)), hashlib.sha256(payload).hexdigest(),
                                historical, evaluation, maximum, unresolved)


def _validate_artifact(path: pathlib.Path, *, expected_tasks: set[str], expected_seeds: set[int],
                       require_evidence: bool, registered_arms: frozenset[str] = ARMS) -> dict[str, Any]:
    try:
        row = load_artifact(path)
    except EvidenceContractError as exc:
        raise LedgerReconciliationError("scored artifact is unreadable") from exc
    if not isinstance(row, dict):
        raise LedgerReconciliationError("scored artifact has the wrong shape")
    arm, task = row.get("arm"), row.get("task_id")
    if arm not in registered_arms or task not in expected_tasks:
        raise LedgerReconciliationError("scored artifact has an unregistered arm or task")
    try:
        trial, seed = int(row["trial_id"]), int(row["seed"])
        score, actions = float(row["after_score"]), int(row["actions"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LedgerReconciliationError("scored artifact has invalid identity, score, or action count") from exc
    if trial < 1 or seed not in expected_seeds or not math.isfinite(score) or actions < 0:
        raise LedgerReconciliationError("scored artifact violates frozen identity or score constraints")
    history = row.get("history")
    if not isinstance(history, list) or not history or row.get("history_sha256") != _digest(history):
        raise LedgerReconciliationError("scored artifact history is absent or hash-inconsistent")
    if actions != sum(isinstance(message, dict) and message.get("role") == "assistant" for message in history):
        raise LedgerReconciliationError("scored artifact action count disagrees with canonical history")
    if require_evidence:
        try:
            # Artifact layout is <run>/artifacts/<task>/<arm>/trial-N.json.
            validate_execution_evidence(row, run_root=path.parents[3])
        except EvidenceContractError as exc:
            raise LedgerReconciliationError(str(exc)) from exc
    return row


def reconcile_artifacts(artifact_root: pathlib.Path, *, expected_tasks: Iterable[str], expected_seeds: Iterable[int],
                        require_evidence: bool = True,
                        registered_arms: Iterable[str] = ARMS) -> tuple[dict[str, Any], ...]:
    tasks, seeds = set(expected_tasks), set(expected_seeds)
    if not tasks or not seeds:
        raise ValueError("frozen task and seed sets are required")
    registered = frozenset(str(arm) for arm in registered_arms)
    rows: list[dict[str, Any]] = []
    identities: set[tuple[str, str, int, int]] = set()
    for path in sorted(artifact_root.glob("**/*.json")) if artifact_root.is_dir() else []:
        row = _validate_artifact(path, expected_tasks=tasks, expected_seeds=seeds,
                                 require_evidence=require_evidence, registered_arms=registered)
        identity = (str(row["arm"]), str(row["task_id"]), int(row["trial_id"]), int(row["seed"]))
        if identity in identities:
            raise LedgerReconciliationError("duplicate completed trajectory artifact")
        identities.add(identity); rows.append(row)
    return tuple(rows)


def build_live_summary(*, ledger_path: pathlib.Path, artifact_root: pathlib.Path, expected_tasks: Iterable[str],
                       expected_seeds: Iterable[int], historical_expected_usd: float | Decimal,
                       state: str, final: bool = False, require_evidence: bool = True,
                       expected_trajectories: int | None = None,
                       registered_arms: Iterable[str] = ARMS) -> Mapping[str, Any]:
    """Return a deterministic summary; callers may atomically persist it."""
    task_list, seed_list = tuple(expected_tasks), tuple(expected_seeds)
    registered = frozenset(str(arm) for arm in registered_arms)
    ledger = reconcile_ledger(ledger_path, historical_expected_usd=historical_expected_usd,
                              registered_arms=registered)
    rows = reconcile_artifacts(artifact_root, expected_tasks=task_list, expected_seeds=seed_list,
                               require_evidence=require_evidence, registered_arms=registered)
    expected = len(task_list) * len(seed_list) * len(registered)
    if expected_trajectories is not None and expected != expected_trajectories:
        raise LedgerReconciliationError("manifest trajectory denominator disagrees with its task/seed/arm allocation")
    arm_rows = {arm: [row for row in rows if row["arm"] == arm] for arm in sorted(registered)}
    summary: dict[str, Any] = {"state": state, "completed": len(rows), "expected": expected, "arms": {}}
    for arm, items in arm_rows.items():
        settled = [call for call in ledger.calls if call.arm == arm and call.settled_usd is not None]
        by_kind = {kind: sum((call.settled_usd or Decimal(0) for call in settled if call.kind == kind), Decimal(0))
                   for kind in ("executor", "lifecycle", "embedding")}
        calls = {kind: sum(call.kind == kind for call in settled) for kind in by_kind}
        successes = sum(float(item["after_score"]) == 1.0 for item in items)
        summary["arms"][arm] = {"Completed": len(items), "Successes": successes,
            "AvgScore": sum(float(item["after_score"]) for item in items) / len(items) if items else 0.0,
            "SuccessRate": successes / len(items) if items else 0.0,
            "AvgActions": sum(int(item["actions"]) for item in items) / len(items) if items else 0.0,
            "ExecutorCalls": calls["executor"], "LifecycleCalls": calls["lifecycle"], "EmbeddingCalls": calls["embedding"],
            "ExecutorCost": _number(by_kind["executor"]), "LifecycleCost": _number(by_kind["lifecycle"]),
            "EmbeddingCost": _number(by_kind["embedding"]), "TotalCost": _number(sum(by_kind.values(), Decimal(0)))}
        if len(items) > len(task_list) * len(seed_list):
            raise LedgerReconciliationError("an arm exceeds its frozen trajectory count")
    per_arm = sum((Decimal(str(value["TotalCost"])) for value in summary["arms"].values()), Decimal(0))
    if per_arm != ledger.settled_evaluation_cost:
        raise LedgerReconciliationError("per-arm settled costs do not reconcile with the ledger")
    summary.update({"settled_evaluation_cost": _number(ledger.settled_evaluation_cost),
        "historical_settled_exposure": _number(ledger.historical_settled_exposure),
        "total_ledger_exposure": _number(ledger.total_ledger_exposure),
        "reserved_maximum_exposure": _number(ledger.reserved_maximum_exposure),
        "unresolved_reservation_count": len(ledger.unresolved_reservation_ids),
        "unresolved_reservation_ids": list(ledger.unresolved_reservation_ids),
        "unattributed_settlement_count": 0,
        "last_completed_trajectory": max((str(row["trajectory_id"]) for row in rows), default=None),
        "ledger_sha256": ledger.ledger_sha256})
    if final:
        if ledger.unresolved_reservation_ids or len(rows) != expected:
            raise LedgerReconciliationError("final completion requires every frozen trajectory and no unresolved reservation")
        required = {(arm, task, index + 1, seed) for arm in registered for task in task_list
                    for index, seed in enumerate(seed_list)}
        observed = {(str(row["arm"]), str(row["task_id"]), int(row["trial_id"]), int(row["seed"])) for row in rows}
        if observed != required:
            raise LedgerReconciliationError("final trajectory allocation is incomplete or inconsistent")
    return MappingProxyType(summary)


def write_live_summary(path: pathlib.Path, summary: Mapping[str, Any], *, updated_ns: int | None = None) -> None:
    """Atomically persist a deterministic summary without touching the ledger."""
    value = dict(summary); value["updated_ns"] = int(time.time_ns() if updated_ns is None else updated_ns)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":")); handle.write("\n")
        handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, path)
    try:
        directory = os.open(str(path.parent), os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    except OSError:
        pass
