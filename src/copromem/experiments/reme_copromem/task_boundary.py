"""Deterministic, transactional CoProMem task-boundary learning.

The planner may simulate candidate ingestion on a private clone only.  The
retrieval bank is changed solely by :func:`commit_task_boundary_plan` after the
complete structural policy validates.  Plans are content-addressed records so a
restart and a forensic replay share exactly the same reconstruction path.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict
from typing import Any, Sequence

from ...benchmarks.appworld.adapter import AcquisitionIdentity, CoProMemAppWorldAdapter, RawAcquisitionTrajectory
from ...learning import ActionObservation, LearningCore
from ...online import ScoredCandidate, apply_task_batch

POLICY_VERSION = "v5-task-boundary-transaction-v1"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _clone(value: Any) -> Any:
    return json.loads(canonical_bytes(value))


def _events(value: Sequence[dict[str, Any]]) -> tuple[ActionObservation, ...]:
    return tuple(ActionObservation(
        operation=str(item["operation"]), input_slots=tuple(item.get("input_slots", ())),
        output_slots=tuple(item.get("output_slots", ())), precondition=str(item.get("precondition", "")),
        check=str(item.get("check", "")), parameters=dict(item.get("parameters", {})),
        observed=bool(item.get("observed", True))) for item in value)


def _trial_candidate(item: dict[str, Any]) -> ScoredCandidate:
    required = {"task_id", "seed", "trajectory_index", "intent", "score", "no_memory_score", "actions", "cost_usd", "events"}
    if not required <= set(item):
        raise ValueError("task-boundary trial lacks canonical fields")
    score = float(item["score"])
    identity = AcquisitionIdentity(str(item["task_id"]), int(item["seed"]), int(item["trajectory_index"]))
    trajectory = RawAcquisitionTrajectory(identity=identity, intent=str(item["intent"]), domain="appworld",
        success=score == 1.0, actions=tuple(str(x) for x in item.get("actions_text", ())),
        task_state=_clone(item.get("task_state", {})), events=_events(item["events"]))
    return ScoredCandidate(trajectory, score, float(item["cost_usd"]), int(item["actions"]),
                           item.get("selected_schema_id"), float(item["no_memory_score"]))


def _trial_order(item: dict[str, Any]) -> tuple[str, int, int]:
    return str(item["task_id"]), int(item["seed"]), int(item["trajectory_index"])


def _candidate_trace(candidate: ScoredCandidate, adapter: CoProMemAppWorldAdapter) -> dict[str, Any]:
    identity = candidate.trajectory.identity.value
    events = candidate.trajectory.events
    schema_id = adapter.module.learning.episode_schemas.get(identity)
    procedures = adapter.module.learning.episode_procedures.get(identity, [])
    signature = LearningCore.signature(events)
    predicates = {
        "official_full_success": candidate.trajectory.success,
        "has_events": bool(events),
        "all_executor_operations_observed": bool(events) and all(event.observed for event in events),
        "structural_signature": signature is not None,
        "observable_procedure": any(event.check and event.output_slots for event in events),
        "has_extracted_procedure": bool(procedures),
        "schema_is_grounded": bool(schema_id and schema_id.startswith("schema_")),
    }
    return {"episode_id": identity, "task_id": candidate.trajectory.identity.task_id,
            "score": candidate.score, "cost_usd": candidate.cost_usd, "actions": candidate.actions,
            "schema_id": schema_id, "procedure_ids": sorted(procedures),
            "event_count": len(events), "signature_sha256": canonical_digest(signature) if signature else None,
            "predicates": predicates,
            "tie_break": [-candidate.score, candidate.cost_usd, candidate.actions,
                           candidate.trajectory.identity.trajectory_index]}


def plan_task_boundary_update(frozen_pre_state: dict[str, Any], frozen_descriptor: Sequence[dict[str, Any]],
                              frozen_scored_trials: Sequence[dict[str, Any]], policy_version: str = POLICY_VERSION) -> dict[str, Any]:
    """Plan on an isolated clone; this never mutates ``frozen_pre_state``."""
    pre = _clone(frozen_pre_state)
    descriptor = _clone(list(frozen_descriptor))
    trials = sorted((_clone(item) for item in frozen_scored_trials), key=_trial_order)
    if not trials or len({item["task_id"] for item in trials}) != 1 or len({_trial_order(item) for item in trials}) != len(trials):
        raise ValueError("task-boundary plan requires one task and unique trials")
    # Candidate extraction is deliberately non-promoting.  Even the private
    # planning clone contains candidates only; validation decides whether a
    # second, canonical reconstruction may promote one.
    adapter = CoProMemAppWorldAdapter(api_key="")
    adapter.clone_from_state(pre)
    candidates = [_trial_candidate(item) for item in trials]
    for candidate in candidates:
        adapter.ingest(candidate.trajectory)
        adapter.module.record_feedback(candidate.selected_schema_id, candidate.trajectory.identity.task_id,
                                       candidate.trajectory.identity.seed, candidate.score, candidate.no_memory_score)
    traces = [_candidate_trace(candidate, adapter) for candidate in candidates]
    descriptor_events = _events(descriptor)
    plan = {"version": POLICY_VERSION, "policy_version": str(policy_version),
        "task_id": str(trials[0]["task_id"]), "pre_state": pre, "pre_state_sha256": canonical_digest(pre),
        "descriptor": descriptor, "descriptor_sha256": canonical_digest(descriptor),
        "trials": trials, "trials_sha256": canonical_digest(trials),
        "descriptor_signature_sha256": canonical_digest(LearningCore.signature(descriptor_events)) if LearningCore.signature(descriptor_events) else None,
        "candidate_traces": traces, "candidate_audit_state": adapter.export_state(),
        "candidate_audit_state_sha256": canonical_digest(adapter.export_state())}
    plan["plan_sha256"] = canonical_digest({key: value for key, value in plan.items() if key != "plan_sha256"})
    return plan


def validate_task_boundary_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Validate the frozen, strict-v5 predicate without changing state."""
    expected = canonical_digest({key: value for key, value in plan.items() if key != "plan_sha256"})
    if plan.get("plan_sha256") != expected:
        raise ValueError("task-boundary plan digest mismatch")
    if plan.get("version") != POLICY_VERSION or plan.get("policy_version") != POLICY_VERSION:
        raise ValueError("task-boundary policy mismatch")
    if canonical_digest(plan.get("pre_state")) != plan.get("pre_state_sha256") or canonical_digest(plan.get("trials")) != plan.get("trials_sha256"):
        raise ValueError("task-boundary frozen input mismatch")
    traces = plan.get("candidate_traces", [])
    full_success = any(item["predicates"]["official_full_success"] for item in traces)
    fully_observed = bool(traces) and all(item["predicates"]["all_executor_operations_observed"] for item in traces)
    structural = bool(traces) and all(item["predicates"]["structural_signature"] for item in traces)
    procedure = any(item["predicates"]["has_extracted_procedure"] for item in traces)
    eligible = [item for item in traces if all(item["predicates"][key] for key in
                ("official_full_success", "all_executor_operations_observed", "structural_signature", "observable_procedure", "has_extracted_procedure", "schema_is_grounded"))]
    winner = min(eligible, key=lambda item: tuple(item["tie_break"]))["episode_id"] if eligible else None
    valid = bool(full_success and fully_observed and structural and procedure and winner)
    return {"plan_sha256": plan["plan_sha256"], "task_id": plan["task_id"], "full_success": full_success,
            "fully_observed": fully_observed, "structural_evidence": structural,
            "procedure_eligible": procedure, "eligible_episode_ids": [item["episode_id"] for item in eligible],
            "winner_episode_id": winner if valid else None, "passed": valid,
            "rejection_reason": None if valid else "strict_v5_structural_grounding_failed"}


def commit_task_boundary_plan(frozen_pre_state: dict[str, Any], plan: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Canonical live/offline reconstruction function.

    A rejected plan returns a deep-copied pre-state.  A valid plan rebuilds the
    one committed state from the same canonical trial inputs used by planning.
    """
    validation = validate_task_boundary_plan(plan)
    pre = _clone(frozen_pre_state)
    if canonical_digest(pre) != plan["pre_state_sha256"]:
        raise ValueError("task-boundary current pre-state mismatch")
    if not validation["passed"]:
        return pre, validation
    adapter = CoProMemAppWorldAdapter(api_key="")
    adapter.clone_from_state(pre)
    candidates = [_trial_candidate(item) for item in sorted(plan["trials"], key=_trial_order)]
    committed_winner = apply_task_batch(adapter, candidates)
    if committed_winner != validation["winner_episode_id"]:
        raise ValueError("task-boundary winner reconstruction mismatch")
    post = adapter.export_state()
    # Ensure the planned winner is actually provisional in the reconstructed state.
    winner = validation["winner_episode_id"]
    learning = post.get("learning", {})
    schema_id = learning.get("episode_schemas", {}).get(winner)
    schemas = {item.get("schema_id"): item for item in learning.get("schemas", [])}
    if not schema_id or schemas.get(schema_id, {}).get("status") not in {"provisional", "admitted"}:
        raise ValueError("task-boundary winner is not committed in post-state")
    return post, validation
