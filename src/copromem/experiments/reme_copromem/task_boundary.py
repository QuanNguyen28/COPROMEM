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
from .public_path_registry import observed_public_operation_matches, public_path_audit, verify_public_registry
from .public_tool_schema_registry import (canonical_operation_signature, invocation_evidence,
                                          public_tool_path_audit, verify_public_tool_schema_registry)

POLICY_VERSION = "v5-task-boundary-transaction-v1"
OBSERVABLE_SUBGRAPH_POLICY_VERSION = "observable_supported_subgraph_v5_1"
OBSERVABLE_PATH_POLICY_VERSION = "observable_supported_path_v5_2"
TOOL_SCHEMA_PATH_POLICY_VERSION = "observable_tool_schema_path_v5_3"
# Same v5.3 public callable predicate, but the observed calls originate from
# AppWorld's shared dispatcher rather than a Python-source approximation.
EXECUTION_EVIDENCE_POLICY_VERSION = "observable_tool_schema_execution_evidence_v1"
STRICT_POLICY_VERSION = "strict_exact_v5"
HELPER_REGISTRY_VERSION = "public-helper-registry-v1"

# Identity-only categories.  The data-flow test below, rather than score or
# task content, decides whether a helper can actually be excluded.
PUBLIC_HELPER_PREFIXES = ("apis.api_docs.",)
PUBLIC_HELPER_OPERATIONS = {"apis.supervisor.complete_task", "apis.supervisor.show_account_passwords"}


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


def fully_observed(events: Sequence[ActionObservation]) -> bool:
    """Strict v5 evidence predicate: an observed response has a check.

    ``check`` is positive evidence, not a reason to reject a step. Concrete
    parameters are not admitted into signatures because ``LearningCore``
    templates them before deriving the content-addressed structure.
    """
    return bool(events) and all(event.observed for event in events)


def _same_shape(left: ActionObservation, right: ActionObservation) -> bool:
    return (left.operation == right.operation and set(left.input_slots) == set(right.input_slots)
            and set(left.output_slots) == set(right.output_slots))


def _helper_category(event: ActionObservation) -> str | None:
    if event.operation.startswith(PUBLIC_HELPER_PREFIXES): return "allowed_infrastructure_helper"
    if event.operation in PUBLIC_HELPER_OPERATIONS or event.operation.endswith(".login"):
        return "allowed_infrastructure_helper"
    return None


def project_observable_supported_subgraph(descriptor: Sequence[ActionObservation],
                                          events: Sequence[ActionObservation]) -> tuple[tuple[ActionObservation, ...], dict[str, Any]]:
    """Project only directly observed, public descriptor steps without values.

    The result is independent of score, private state, or model output.  A
    helper whose output feeds a required descriptor input is unresolved rather
    than silently accepted.
    """
    desc, raw = tuple(descriptor), tuple(events)
    included: list[ActionObservation] = []; records: list[dict[str, Any]] = []; cursor = 0
    descriptor_inputs = {slot for item in desc for slot in item.input_slots}
    for index, event in enumerate(raw):
        if cursor < len(desc) and _same_shape(event, desc[cursor]):
            category = "included_descriptor_step" if event.observed and event.check else "disqualifying_unsupported_operation"
            records.append({"index": index, "category": category, "operation": event.operation,
                            "input_slots": sorted(event.input_slots), "output_slots": sorted(event.output_slots)})
            if category == "included_descriptor_step": included.append(event); cursor += 1
            continue
        helper = _helper_category(event)
        output_feeds_required = bool(set(event.output_slots) & descriptor_inputs)
        if helper and not output_feeds_required:
            category = helper
        elif helper:
            category = "unresolved_dependency"
        elif not event.observed:
            category = "disqualifying_unsupported_operation"
        else:
            category = "excluded_unrelated_exploration"
        records.append({"index": index, "category": category, "operation": event.operation,
                        "input_slots": sorted(event.input_slots), "output_slots": sorted(event.output_slots)})
    missing = [item.operation for item in desc[cursor:]]
    included_outputs: set[str] = set(); unresolved_inputs: list[str] = []
    helper_outputs = {slot for item, row in zip(raw, records) if row["category"] == "unresolved_dependency" for slot in item.output_slots}
    for item in included:
        for slot in item.input_slots:
            if slot in helper_outputs: unresolved_inputs.append(slot)
        included_outputs.update(item.output_slots)
    audit = {"registry_version": HELPER_REGISTRY_VERSION, "required_count": len(desc),
             "included_count": len(included), "missing_operations": missing,
             "unresolved_dependency_slots": sorted(set(unresolved_inputs)), "records": records,
             "valid": bool(desc) and len(included) == len(desc) and not missing and not unresolved_inputs and
                      not any(row["category"] == "disqualifying_unsupported_operation" for row in records)}
    return tuple(included), audit


def project_observable_registry_path(registry: dict[str, Any], descriptor: Sequence[ActionObservation],
                                     events: Sequence[ActionObservation]) -> tuple[tuple[ActionObservation, ...], dict[str, Any]]:
    """Project one frozen public path without retaining values or raw checks.

    A descriptor is a pre-execution path selected from the frozen registry.
    The raw trace is consulted only for direct operation/slot evidence.  The
    stored projection takes its names and slots from the descriptor and has no
    parameters, concrete values, or task text.
    """
    verify_public_registry(registry)
    desc, raw = tuple(descriptor), tuple(events)
    cursor = 0; selected: list[ActionObservation] = []; records: list[dict[str, Any]] = []
    for index, event in enumerate(raw):
        matched, match_audit = (observed_public_operation_matches(registry, asdict(event), asdict(desc[cursor]))
                                if cursor < len(desc) else (False, {"reason": "path_already_complete"}))
        if cursor < len(desc) and matched and event.observed and bool(event.check):
            expected = desc[cursor]
            selected.append(ActionObservation(operation=expected.operation, input_slots=tuple(expected.input_slots),
                                               output_slots=tuple(expected.output_slots), check="direct_public_observation",
                                               observed=True))
            records.append({"index": index, "category": "included_descriptor_path_step", "operation": event.operation,
                            "input_slots": sorted(event.input_slots), "output_slots": sorted(event.output_slots),
                            "normalization": match_audit})
            cursor += 1
        elif event.operation == (desc[cursor].operation if cursor < len(desc) else ""):
            records.append({"index": index, "category": "descriptor_signature_not_directly_observed", "operation": event.operation,
                            "input_slots": sorted(event.input_slots), "output_slots": sorted(event.output_slots),
                            "normalization": match_audit})
        else:
            helper = _helper_category(event)
            records.append({"index": index, "category": helper or "excluded_non_path_operation", "operation": event.operation,
                            "input_slots": sorted(event.input_slots), "output_slots": sorted(event.output_slots)})
    missing = [item.operation for item in desc[cursor:]]
    path = public_path_audit(registry, [asdict(item) for item in selected]) if selected else {
        "registry_sha256": registry["registry_sha256"], "selected_path": [],
        "selected_path_sha256": canonical_digest([]), "passed": False,
        "first_rejection": {"reason": "empty_or_incomplete_path"}, "rejections": [{"reason": "empty_or_incomplete_path"}],
    }
    valid = bool(desc) and not missing and len(selected) == len(desc) and bool(path["passed"])
    audit = {"registry_version": registry["registry_version"], "registry_sha256": registry["registry_sha256"],
             "required_count": len(desc), "included_count": len(selected), "missing_operations": missing,
             "records": records, "path_audit": path, "path_audit_sha256": canonical_digest(path), "valid": valid}
    return tuple(selected), audit


def project_observable_tool_schema_path(registry: dict[str, Any], descriptor: Sequence[ActionObservation],
                                        events: Sequence[ActionObservation], *, raw_evidence_digest: str) -> tuple[tuple[ActionObservation, ...], dict[str, Any]]:
    """Project direct calls through the frozen v5.3 callable interface.

    Invocation values are not retained.  The only raw execution reference is
    an aggregate digest separated from the procedure-bearing projection.
    """
    verify_public_tool_schema_registry(registry)
    desc, raw = tuple(descriptor), tuple(events)
    cursor = 0; selected: list[ActionObservation] = []; evidence: list[dict[str, Any]] = []; records: list[dict[str, Any]] = []
    for index, event in enumerate(raw):
        if cursor >= len(desc):
            records.append({"index": index, "category": _helper_category(event) or "excluded_non_path_operation", "operation": event.operation})
            continue
        expected = desc[cursor]
        try:
            signature = canonical_operation_signature(registry, event.operation, event.input_slots)
        except ValueError as exc:
            records.append({"index": index, "category": "nonmatching_or_undeclared_call", "operation": event.operation,
                            "reason": str(exc)})
            continue
        if signature["operation"] != expected.operation or not event.observed or not event.check:
            records.append({"index": index, "category": "nonmatching_or_unobserved_path_step", "operation": event.operation})
            continue
        # The descriptor itself is derived from the frozen registry.  This
        # guard prevents a hand-written signature from silently widening it.
        if (list(expected.input_slots) != signature["public_required"] or
                list(expected.output_slots) != signature["output_slots"]):
            records.append({"index": index, "category": "descriptor_callable_schema_mismatch", "operation": event.operation})
            continue
        selected.append(ActionObservation(operation=expected.operation, input_slots=tuple(expected.input_slots),
                                           output_slots=tuple(expected.output_slots), check="direct_public_observation",
                                           observed=True))
        evidence.append(invocation_evidence(signature, raw_event_digest=canonical_digest(
            {"trajectory": raw_evidence_digest, "index": index, "operation": event.operation,
             "input_slots": sorted(event.input_slots), "output_slots": sorted(event.output_slots)}),
            concrete_value_digest=raw_evidence_digest))
        records.append({"index": index, "category": "included_tool_schema_path_step", "operation": event.operation,
                        "invocation_evidence_sha256": evidence[-1]["invocation_evidence_sha256"]})
        cursor += 1
    signatures = [item["operation_signature"] for item in evidence]
    path = public_tool_path_audit(registry, signatures) if signatures else {
        "registry_sha256": registry["registry_sha256"], "path": [], "path_sha256": canonical_digest([]),
        "passed": False, "rejections": [{"reason": "empty_or_incomplete_path"}],
        "first_rejection": {"reason": "empty_or_incomplete_path"}}
    missing = [item.operation for item in desc[cursor:]]
    audit = {"registry_version": registry["registry_version"], "registry_sha256": registry["registry_sha256"],
             "required_count": len(desc), "included_count": len(selected), "missing_operations": missing,
             "records": records, "invocation_evidence": evidence,
             "invocation_evidence_sha256": canonical_digest(evidence), "path_audit": path,
             "path_audit_sha256": canonical_digest(path),
             "valid": bool(desc) and len(selected) == len(desc) and not missing and bool(path["passed"])}
    return tuple(selected), audit


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
        "all_executor_operations_observed": fully_observed(events),
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
                              frozen_scored_trials: Sequence[dict[str, Any]], policy_version: str = POLICY_VERSION,
                              public_registry: dict[str, Any] | None = None) -> dict[str, Any]:
    """Plan on an isolated clone; this never mutates ``frozen_pre_state``."""
    pre = _clone(frozen_pre_state)
    descriptor = _clone(list(frozen_descriptor))
    trials = sorted((_clone(item) for item in frozen_scored_trials), key=_trial_order)
    if not trials or len({item["task_id"] for item in trials}) != 1 or len({_trial_order(item) for item in trials}) != len(trials):
        raise ValueError("task-boundary plan requires one task and unique trials")
    if policy_version == OBSERVABLE_SUBGRAPH_POLICY_VERSION:
        descriptor_events = _events(descriptor)
        projections = []
        for item in trials:
            projected, audit = project_observable_supported_subgraph(descriptor_events, _events(item["events"]))
            item["events"] = [asdict(event) for event in projected]
            projections.append({"trajectory_index": item["trajectory_index"], "audit": audit})
    elif policy_version == OBSERVABLE_PATH_POLICY_VERSION:
        if public_registry is None:
            raise ValueError("v5.2 task-boundary plan requires frozen public registry")
        verify_public_registry(public_registry)
        descriptor_events = _events(descriptor)
        projections = []
        for item in trials:
            projected, audit = project_observable_registry_path(public_registry, descriptor_events, _events(item["events"]))
            item["events"] = [asdict(event) for event in projected]
            projections.append({"trajectory_index": item["trajectory_index"], "audit": audit})
    elif policy_version in {TOOL_SCHEMA_PATH_POLICY_VERSION, EXECUTION_EVIDENCE_POLICY_VERSION}:
        if public_registry is None: raise ValueError("v5.3 task-boundary plan requires frozen tool schema registry")
        verify_public_tool_schema_registry(public_registry)
        descriptor_events = _events(descriptor); projections = []
        for item in trials:
            evidence_audit = item.get("task_state", {}).get("execution_evidence_audit")
            if policy_version == EXECUTION_EVIDENCE_POLICY_VERSION:
                if not isinstance(evidence_audit, dict) or not evidence_audit.get("valid"):
                    projected, audit = (), {"valid": False, "path_audit": {"passed": False},
                                            "first_rejection": {"reason": "execution_evidence_invalid"},
                                            "execution_evidence_audit": evidence_audit}
                else:
                    projected, audit = project_observable_tool_schema_path(
                        public_registry, descriptor_events, _events(item["events"]),
                        raw_evidence_digest=str(evidence_audit["records_sha256"]))
                    audit["execution_evidence_audit_sha256"] = canonical_digest(evidence_audit)
            else:
                raw_digest = canonical_digest({"intent": item.get("intent", ""), "actions": item.get("actions_text", ())})
                projected, audit = project_observable_tool_schema_path(public_registry, descriptor_events, _events(item["events"]), raw_evidence_digest=raw_digest)
            # A learned procedure sees only registry signatures, never task
            # instruction text, action code, or concrete invocation values.
            item["events"] = [asdict(event) for event in projected]
            item["intent"] = f"public_tool_path:{canonical_digest(descriptor)}"
            item["actions_text"] = [event.operation for event in projected]
            projections.append({"trajectory_index": item["trajectory_index"], "audit": audit})
    elif policy_version in {POLICY_VERSION, STRICT_POLICY_VERSION}:
        projections = []
    else:
        raise ValueError("unknown task-boundary policy")
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
    descriptor_signature = LearningCore.signature(descriptor_events)
    plan = {"version": POLICY_VERSION, "policy_version": str(policy_version),
        "task_id": str(trials[0]["task_id"]), "pre_state": pre, "pre_state_sha256": canonical_digest(pre),
        "descriptor": descriptor, "descriptor_sha256": canonical_digest(descriptor),
        "trials": trials, "trials_sha256": canonical_digest(trials),
        "projection_audit": projections, "projection_audit_sha256": canonical_digest(projections),
        "descriptor_signature_sha256": canonical_digest(descriptor_signature) if descriptor_signature else None,
        "candidate_traces": traces, "candidate_audit_state": adapter.export_state(),
        "candidate_audit_state_sha256": canonical_digest(adapter.export_state())}
    if policy_version in {OBSERVABLE_PATH_POLICY_VERSION, TOOL_SCHEMA_PATH_POLICY_VERSION, EXECUTION_EVIDENCE_POLICY_VERSION}:
        plan["public_registry"] = _clone(public_registry)
        plan["public_registry_sha256"] = str(public_registry["registry_sha256"])
    plan["plan_sha256"] = canonical_digest({key: value for key, value in plan.items() if key != "plan_sha256"})
    return plan


def _verify_plan(plan: dict[str, Any]) -> None:
    expected = canonical_digest({key: value for key, value in plan.items() if key != "plan_sha256"})
    if plan.get("plan_sha256") != expected:
        raise ValueError("task-boundary plan digest mismatch")
    if plan.get("version") != POLICY_VERSION or plan.get("policy_version") not in {POLICY_VERSION, STRICT_POLICY_VERSION, OBSERVABLE_SUBGRAPH_POLICY_VERSION, OBSERVABLE_PATH_POLICY_VERSION, TOOL_SCHEMA_PATH_POLICY_VERSION, EXECUTION_EVIDENCE_POLICY_VERSION}:
        raise ValueError("task-boundary policy mismatch")
    if canonical_digest(plan.get("pre_state")) != plan.get("pre_state_sha256") or canonical_digest(plan.get("trials")) != plan.get("trials_sha256"):
        raise ValueError("task-boundary frozen input mismatch")
    if canonical_digest(plan.get("projection_audit", [])) != plan.get("projection_audit_sha256"):
        raise ValueError("task-boundary projection audit mismatch")
    if plan.get("policy_version") in {OBSERVABLE_PATH_POLICY_VERSION, TOOL_SCHEMA_PATH_POLICY_VERSION, EXECUTION_EVIDENCE_POLICY_VERSION}:
        registry = plan.get("public_registry")
        (verify_public_registry if plan.get("policy_version") == OBSERVABLE_PATH_POLICY_VERSION else verify_public_tool_schema_registry)(registry)
        if plan.get("public_registry_sha256") != registry.get("registry_sha256"):
            raise ValueError("task-boundary public registry digest mismatch")


def validate_strict_v5(plan: dict[str, Any]) -> dict[str, Any]:
    """Original strict predicate: every raw normalized event is required."""
    _verify_plan(plan)
    traces = plan.get("candidate_traces", [])
    full_success = any(item["predicates"]["official_full_success"] for item in traces)
    fully_observed = bool(traces) and all(item["predicates"]["all_executor_operations_observed"] for item in traces)
    structural = bool(traces) and all(item["predicates"]["structural_signature"] for item in traces)
    # A strict-v5 task boundary is only transferable when the public descriptor
    # used at retrieval is the exact signature learned from every scored trace.
    # Empty descriptors are retained solely for pre-v5 compatibility callers;
    # the strict task-boundary runner always supplies one.
    descriptor_signature = plan.get("descriptor_signature_sha256")
    descriptor_exact = (True if descriptor_signature is None else bool(traces) and all(
        item.get("signature_sha256") == descriptor_signature for item in traces))
    procedure = any(item["predicates"]["has_extracted_procedure"] for item in traces)
    eligible = [item for item in traces if all(item["predicates"][key] for key in
                ("official_full_success", "all_executor_operations_observed", "structural_signature", "observable_procedure", "has_extracted_procedure", "schema_is_grounded"))]
    winner = min(eligible, key=lambda item: tuple(item["tie_break"]))["episode_id"] if eligible else None
    valid = bool(full_success and fully_observed and structural and descriptor_exact and procedure and winner)
    return {"plan_sha256": plan["plan_sha256"], "task_id": plan["task_id"], "full_success": full_success,
            "fully_observed": fully_observed, "structural_evidence": structural,
            "descriptor_exact_match": descriptor_exact,
            "procedure_eligible": procedure, "eligible_episode_ids": [item["episode_id"] for item in eligible],
            "winner_episode_id": winner if valid else None, "passed": valid,
            "rejection_reason": None if valid else "strict_v5_structural_grounding_failed"}


def validate_observable_subgraph_v5_1(plan: dict[str, Any]) -> dict[str, Any]:
    """Validate only frozen projected evidence; raw trace is audit-only."""
    _verify_plan(plan)
    traces, projections = plan.get("candidate_traces", []), plan.get("projection_audit", [])
    audits = {int(item["trajectory_index"]): item["audit"] for item in projections}
    eligible = []
    for trace in traces:
        audit = audits.get(int(trace["tie_break"][-1]), {})
        predicates = trace["predicates"]
        direct = bool(predicates["structural_signature"] and predicates["observable_procedure"] and
                      predicates["has_extracted_procedure"] and predicates["schema_is_grounded"])
        if predicates["official_full_success"] and audit.get("valid") and direct and trace["signature_sha256"] == plan.get("descriptor_signature_sha256"):
            eligible.append(trace)
    winner = min(eligible, key=lambda item: tuple(item["tie_break"]))["episode_id"] if eligible else None
    successful = any(item["predicates"]["official_full_success"] for item in traces)
    audits_valid = bool(projections) and all(item["audit"].get("valid") for item in projections)
    coverage = bool(projections) and all(not item["audit"].get("missing_operations") for item in projections)
    unresolved = any(item["audit"].get("unresolved_dependency_slots") for item in projections)
    procedures = any(item["predicates"]["has_extracted_procedure"] for item in traces)
    exact = bool(traces) and all(item["signature_sha256"] == plan.get("descriptor_signature_sha256") for item in traces)
    if not successful: reason = "v5_1_no_successful_projected_episode"
    elif unresolved: reason = "v5_1_unresolved_dependency"
    elif not coverage: reason = "v5_1_descriptor_coverage_incomplete"
    elif not procedures: reason = "v5_1_no_eligible_procedure"
    elif not audits_valid or not exact or not winner: reason = "v5_1_projection_invalid"
    else: reason = None
    return {"plan_sha256": plan["plan_sha256"], "task_id": plan["task_id"], "full_success": successful,
            "projection_valid": audits_valid, "descriptor_exact_match": exact, "descriptor_coverage": coverage,
            "unresolved_dependency": unresolved, "procedure_eligible": procedures,
            "eligible_episode_ids": [item["episode_id"] for item in eligible], "winner_episode_id": winner if reason is None else None,
            "passed": reason is None, "rejection_reason": reason}


def validate_observable_path_v5_2(plan: dict[str, Any]) -> dict[str, Any]:
    """Validate one complete, directly observed frozen public registry path."""
    _verify_plan(plan)
    traces, projections = plan.get("candidate_traces", []), plan.get("projection_audit", [])
    audits = {int(item["trajectory_index"]): item["audit"] for item in projections}
    eligible = []
    for trace in traces:
        audit = audits.get(int(trace["tie_break"][-1]), {})
        predicates = trace["predicates"]
        path = audit.get("path_audit", {})
        direct = bool(predicates["structural_signature"] and predicates["observable_procedure"] and
                      predicates["has_extracted_procedure"] and predicates["schema_is_grounded"])
        exact = trace["signature_sha256"] == plan.get("descriptor_signature_sha256")
        if predicates["official_full_success"] and audit.get("valid") and path.get("passed") and direct and exact:
            eligible.append(trace)
    winner = min(eligible, key=lambda item: tuple(item["tie_break"]))["episode_id"] if eligible else None
    successful = any(item["predicates"]["official_full_success"] for item in traces)
    complete = bool(projections) and all(item["audit"].get("valid") for item in projections)
    reproduced_paths = bool(projections) and all(item["audit"].get("path_audit", {}).get("passed") for item in projections)
    procedures = any(item["predicates"]["has_extracted_procedure"] for item in traces)
    exact = bool(traces) and all(item["signature_sha256"] == plan.get("descriptor_signature_sha256") for item in traces)
    if not successful: reason = "v5_2_no_successful_observed_path"
    elif not complete: reason = "v5_2_public_path_incomplete"
    elif not reproduced_paths: reason = "v5_2_public_path_validation_failed"
    elif not procedures: reason = "v5_2_no_eligible_procedure"
    elif not exact or not winner: reason = "v5_2_path_projection_invalid"
    else: reason = None
    return {"plan_sha256": plan["plan_sha256"], "task_id": plan["task_id"], "registry_sha256": plan["public_registry_sha256"],
            "full_success": successful, "path_complete": complete, "path_reproduced": reproduced_paths,
            "descriptor_exact_match": exact, "procedure_eligible": procedures,
            "eligible_episode_ids": [item["episode_id"] for item in eligible],
            "winner_episode_id": winner if reason is None else None, "passed": reason is None, "rejection_reason": reason}


def validate_tool_schema_path_v5_3(plan: dict[str, Any]) -> dict[str, Any]:
    """v5.3 validator: one complete, value-free callable-schema path."""
    _verify_plan(plan)
    traces, projections = plan.get("candidate_traces", []), plan.get("projection_audit", [])
    audits = {int(item["trajectory_index"]): item["audit"] for item in projections}; eligible = []
    for trace in traces:
        audit = audits.get(int(trace["tie_break"][-1]), {}); predicates = trace["predicates"]
        direct = all((predicates["structural_signature"], predicates["observable_procedure"],
                      predicates["has_extracted_procedure"], predicates["schema_is_grounded"]))
        exact = trace["signature_sha256"] == plan.get("descriptor_signature_sha256")
        if predicates["official_full_success"] and audit.get("valid") and direct and exact:
            eligible.append(trace)
    winner = min(eligible, key=lambda item: tuple(item["tie_break"]))["episode_id"] if eligible else None
    successful = any(item["predicates"]["official_full_success"] for item in traces)
    complete = bool(projections) and all(item["audit"].get("valid") for item in projections)
    procedures = any(item["predicates"]["has_extracted_procedure"] for item in traces)
    exact = bool(traces) and all(item["signature_sha256"] == plan.get("descriptor_signature_sha256") for item in traces)
    reproduced_paths = bool(projections) and all(item["audit"].get("path_audit", {}).get("passed") for item in projections)
    reason = (None if successful and complete and procedures and exact and winner else
              "v5_3_tool_schema_path_incomplete" if successful else "v5_3_no_successful_observed_path")
    return {"plan_sha256": plan["plan_sha256"], "task_id": plan["task_id"], "registry_sha256": plan["public_registry_sha256"],
            "full_success": successful, "path_complete": complete, "path_reproduced": reproduced_paths, "descriptor_exact_match": exact,
            "procedure_eligible": procedures, "eligible_episode_ids": [item["episode_id"] for item in eligible],
            "winner_episode_id": winner if reason is None else None, "passed": reason is None, "rejection_reason": reason}


def validate_task_boundary_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Dispatch to an explicitly versioned, fail-closed policy validator."""
    policy = plan.get("policy_version")
    if policy == OBSERVABLE_SUBGRAPH_POLICY_VERSION:
        return validate_observable_subgraph_v5_1(plan)
    if policy == OBSERVABLE_PATH_POLICY_VERSION:
        return validate_observable_path_v5_2(plan)
    if policy in {TOOL_SCHEMA_PATH_POLICY_VERSION, EXECUTION_EVIDENCE_POLICY_VERSION}:
        return validate_tool_schema_path_v5_3(plan)
    if policy in {POLICY_VERSION, STRICT_POLICY_VERSION}:
        return validate_strict_v5(plan)
    raise ValueError("unknown task-boundary policy")


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
