"""Bounded structural invariant mining from matched public handoff evidence.

No decisive field names or task answers occur in the learner. The restricted
language cannot express semantic arithmetic correctness; rediscovering an output
schema is explicitly not evidence of a novel reasoning capability.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, replace
from typing import Any

from .checkpoints import canonical, digest

MISSING = object()
JSON_TYPES = {
    "string": str,
    "list": list,
    "object": dict,
    "number": (int, float),
    "boolean": bool,
}


@dataclass(frozen=True, order=True)
class Predicate:
    path: tuple[str, ...]
    operator: str
    argument: str = ""

    def __post_init__(self) -> None:
        if not self.path or any(
            not isinstance(part, str) or not part for part in self.path
        ):
            raise ValueError("predicate paths must be nonempty strings")
        if self.operator not in {"present", "nonempty", "type", "list_of"}:
            raise ValueError("operator not in the executable language")
        if self.operator in {"type", "list_of"} and self.argument not in JSON_TYPES:
            raise ValueError("unknown JSON type")
        if self.operator in {"present", "nonempty"} and self.argument:
            raise ValueError("unexpected operator argument")

    def holds(self, artifact: dict[str, Any]) -> bool:
        value: Any = artifact
        for part in self.path:
            value = value.get(part, MISSING) if isinstance(value, dict) else MISSING
        if value is MISSING or value is None:
            return False
        if self.operator == "present":
            return True
        if self.operator == "nonempty":
            if isinstance(value, str):
                return bool(value.strip())
            return bool(value) if isinstance(value, (list, dict)) else True

        def is_kind(item: Any) -> bool:
            if self.argument == "number" and isinstance(item, bool):
                return False
            return isinstance(item, JSON_TYPES[self.argument])

        if self.operator == "type":
            return is_kind(value)
        return isinstance(value, list) and all(is_kind(item) for item in value)


@dataclass(frozen=True)
class HandoffEvidence:
    task_id: str
    checkpoint_id: str
    interface: str
    public_context_json: str
    artifact_json: str
    success: bool
    partition: str
    execution_context: str

    @property
    def evidence_id(self) -> str:
        return digest(asdict(self))


@dataclass(frozen=True)
class InducedContract:
    interface: str
    predicates: tuple[Predicate, ...]
    scope: tuple[tuple[str, str], ...]
    source_evidence: tuple[str, ...]
    source_tasks: tuple[str, ...]
    owner: str = "planner"
    recovery_route: str = "return_to_planner"
    status: str = "candidate"
    admission_evidence: str = ""

    def __post_init__(self) -> None:
        if not self.predicates or len(set(self.predicates)) != len(self.predicates):
            raise ValueError("nonempty, unique predicates required")
        if self.status not in {"candidate", "admitted"}:
            raise ValueError("unknown contract status")
        if self.status == "admitted" and not self.admission_evidence:
            raise ValueError("admitted contracts require replay evidence digest")

    @property
    def contract_id(self) -> str:
        return digest(
            {
                "interface": self.interface,
                "predicates": [asdict(x) for x in self.predicates],
                "scope": self.scope,
                "owner": self.owner,
                "recovery_route": self.recovery_route,
            }
        )

    def eligible(self, interface: str, context: dict[str, Any]) -> bool:
        return interface == self.interface and all(
            key in context and canonical(context[key]) == value
            for key, value in self.scope
        )

    def violations(self, artifact: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            asdict(clause) for clause in self.predicates if not clause.holds(artifact)
        ]

    def serialize(self) -> dict[str, Any]:
        return json.loads(canonical(asdict(self)))

    @classmethod
    def load(cls, value: dict[str, Any]) -> InducedContract:
        payload = dict(value)
        payload["predicates"] = tuple(
            Predicate(tuple(x["path"]), x["operator"], x["argument"])
            for x in value["predicates"]
        )
        payload["scope"] = tuple(tuple(item) for item in value["scope"])
        payload["source_evidence"] = tuple(value["source_evidence"])
        payload["source_tasks"] = tuple(value["source_tasks"])
        return cls(**payload)


def _candidate_predicates(
    artifact: dict[str, Any], prefix: tuple[str, ...] = ()
) -> set[Predicate]:
    candidates: set[Predicate] = set()
    for key, value in artifact.items():
        path = (*prefix, key)
        candidates.update((Predicate(path, "present"), Predicate(path, "nonempty")))
        for kind in JSON_TYPES:
            predicate = Predicate(path, "type", kind)
            if predicate.holds(artifact if not prefix else _wrap(prefix, artifact)):
                candidates.add(predicate)
            if isinstance(value, list) and value:
                candidates.add(Predicate(path, "list_of", kind))
        if isinstance(value, dict) and len(path) < 2:
            candidates.update(_candidate_predicates(value, path))
    return candidates


def _wrap(prefix: tuple[str, ...], value: dict[str, Any]) -> dict[str, Any]:
    for key in reversed(prefix):
        value = {key: value}
    return value


def mine_candidates(
    evidence: Iterable[HandoffEvidence], min_source_tasks: int = 2
) -> dict[str, Any]:
    records = list(evidence)
    if any(item.partition != "build" for item in records):
        raise ValueError("only build evidence may enter candidate proposal")
    if min_source_tasks < 1:
        raise ValueError("positive source-task threshold required")
    unique = {item.evidence_id: item for item in records}
    groups: dict[tuple[str, str, str, str], list[HandoffEvidence]] = defaultdict(list)
    for item in unique.values():
        groups[
            (
                item.task_id,
                item.interface,
                item.public_context_json,
                item.execution_context,
            )
        ].append(item)
    pairs: list[tuple[HandoffEvidence, HandoffEvidence]] = []
    for items in groups.values():
        pairs.extend(
            (success, failure)
            for success in items
            if success.success
            for failure in items
            if not failure.success
        )
    scopes: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
    for success, _ in pairs:
        scopes.add((success.interface, ()))
        for key, value in json.loads(success.public_context_json).items():
            if isinstance(value, (str, int, float, bool)):
                scopes.add((success.interface, ((key, canonical(value)),)))
    candidates: list[InducedContract] = []
    rejected: list[dict[str, Any]] = []
    for interface, scope in sorted(scopes):
        matches = [
            (positive, negative)
            for positive, negative in pairs
            if positive.interface == interface
            and all(
                json.loads(positive.public_context_json).get(key, MISSING) != MISSING
                and canonical(json.loads(positive.public_context_json)[key]) == value
                for key, value in scope
            )
        ]
        tasks = sorted({item.task_id for pair in matches for item in pair})
        if len(tasks) < min_source_tasks:
            rejected.append(
                {
                    "interface": interface,
                    "scope": scope,
                    "reason": "insufficient independent matched source tasks",
                    "tasks": tasks,
                }
            )
            continue
        clauses = set().union(
            *(
                _candidate_predicates(json.loads(positive.artifact_json))
                for positive, _ in matches
            )
        )
        good = []
        # A successful source without a paired failure still supplies a valid
        # counterexample. Restricting this veto to matched groups would discard
        # evidence against the proposed invariant.
        scoped_successes = [
            item
            for item in unique.values()
            if item.success
            and item.interface == interface
            and all(
                key in json.loads(item.public_context_json)
                and canonical(json.loads(item.public_context_json)[key]) == value
                for key, value in scope
            )
        ]
        for clause in sorted(clauses):
            all_successes_pass = all(
                clause.holds(json.loads(positive.artifact_json))
                for positive in scoped_successes
            )
            failed_tasks = {
                negative.task_id
                for _, negative in matches
                if not clause.holds(json.loads(negative.artifact_json))
            }
            if all_successes_pass and len(failed_tasks) >= min_source_tasks:
                good.append(clause)
            else:
                rejected.append(
                    {
                        "interface": interface,
                        "scope": scope,
                        "predicate": asdict(clause),
                        "reason": "not consistently discriminative across independent matched tasks",
                    }
                )
        if good:
            candidates.append(
                InducedContract(
                    interface,
                    tuple(good),
                    scope,
                    tuple(
                        sorted(
                            {x.evidence_id for pair in matches for x in pair}
                            | {x.evidence_id for x in scoped_successes}
                        )
                    ),
                    tuple(sorted(set(tasks) | {x.task_id for x in scoped_successes})),
                )
            )
    return {
        "algorithm": "matched-structural-invariant-mining-v2-all-success-veto",
        "records": len(records),
        "unique_records": len(unique),
        "matched_pairs": len(pairs),
        "matched_source_tasks": len({positive.task_id for positive, _ in pairs}),
        "candidates": [item.serialize() for item in candidates],
        "rejected": rejected,
        "limitations": "restricted structural predicate vocabulary and public categorical scope; no semantic synthesis",
    }


@dataclass(frozen=True)
class ReplayOutcome:
    task_id: str
    checkpoint_id: str
    contract_id: str
    partition: str
    baseline_success: bool
    treatment_success: bool
    triggered: bool
    violation: bool
    provider_failure: bool = False
    recovery_success: bool = False
    extra_usd: float = 0.0


@dataclass(frozen=True)
class AdmissionPolicy:
    min_source_tasks: int = 2
    min_dev_tasks: int = 4
    min_boundary_tasks: int = 2
    min_beneficial_flips: int = 1
    max_harmful_flips: int = 0


DEFAULT_ADMISSION_POLICY = AdmissionPolicy()


def replay_metrics(outcomes: Iterable[ReplayOutcome]) -> dict[str, Any]:
    rows = list(outcomes)
    if len({(x.task_id, x.checkpoint_id) for x in rows}) != len(rows):
        raise ValueError("duplicate replay checkpoint")
    beneficial = sum(not x.baseline_success and x.treatment_success for x in rows)
    harmful = sum(x.baseline_success and not x.treatment_success for x in rows)
    positives = [x for x in rows if x.violation]
    failing = [x for x in rows if not x.baseline_success]
    successes = [x for x in rows if x.baseline_success]
    return {
        "unique_tasks": len({x.task_id for x in rows}),
        "checkpoints": len(rows),
        "beneficial_flips": beneficial,
        "harmful_flips": harmful,
        "net_gain": beneficial - harmful,
        "provider_failures": sum(x.provider_failure for x in rows),
        "failure_prediction_precision": sum(not x.baseline_success for x in positives)
        / len(positives)
        if positives
        else None,
        "failure_prediction_recall": sum(x.violation for x in failing) / len(failing)
        if failing
        else None,
        "false_positive_rate": sum(x.violation for x in successes) / len(successes)
        if successes
        else None,
        "recovery_successes": sum(x.recovery_success for x in rows),
        "extra_usd": sum(x.extra_usd for x in rows),
        "diagnostic_label": "verifier classification targets baseline task failure, not a gold causal error annotation",
    }


def admission_decision(
    contract: InducedContract,
    dev: list[ReplayOutcome],
    boundary: list[ReplayOutcome],
    policy: AdmissionPolicy = DEFAULT_ADMISSION_POLICY,
) -> dict[str, Any]:
    if any(x.partition != "dev" for x in dev) or any(
        x.partition != "audit" for x in boundary
    ):
        raise ValueError("development and independent audit roles must be explicit")
    if any(x.contract_id != contract.contract_id for x in (*dev, *boundary)):
        raise ValueError("replay evidence belongs to a different contract")
    source_ids, dev_ids, audit_ids = (
        set(contract.source_tasks),
        {x.task_id for x in dev},
        {x.task_id for x in boundary},
    )
    if source_ids & (dev_ids | audit_ids) or dev_ids & audit_ids:
        raise ValueError("source/development/audit task leakage")
    dev_metrics, audit_metrics = replay_metrics(dev), replay_metrics(boundary)
    reasons = []
    if len(source_ids) < policy.min_source_tasks:
        reasons.append("insufficient independent source tasks")
    if (
        len(dev_ids) < policy.min_dev_tasks
        or len(audit_ids) < policy.min_boundary_tasks
    ):
        reasons.append("insufficient held-out development or boundary tasks")
    if (
        dev_metrics["beneficial_flips"] < policy.min_beneficial_flips
        or dev_metrics["net_gain"] <= 0
    ):
        reasons.append("no positive held-out development benefit")
    if (
        max(dev_metrics["harmful_flips"], audit_metrics["harmful_flips"])
        > policy.max_harmful_flips
    ):
        reasons.append("harmful-flip cap exceeded")
    if dev_metrics["provider_failures"] or audit_metrics["provider_failures"]:
        reasons.append("provider failures invalidate admission evidence")
    evidence = {
        "contract_id": contract.contract_id,
        "policy": asdict(policy),
        "dev": [asdict(x) for x in dev],
        "audit": [asdict(x) for x in boundary],
    }
    return {
        "admitted": not reasons,
        "reasons": reasons,
        "evidence_digest": digest(evidence),
        "evidence": evidence,
        "dev_metrics": dev_metrics,
        "audit_metrics": audit_metrics,
    }


def minimize_on_development(
    contract: InducedContract,
    evaluate: Callable[[InducedContract], list[ReplayOutcome]],
    policy: AdmissionPolicy = DEFAULT_ADMISSION_POLICY,
) -> tuple[InducedContract, list[dict[str, Any]]]:
    """Greedy empirical clause deletion. Never reads boundary or final outcomes."""
    current = contract
    history = []
    for clause in reversed(contract.predicates):
        predicates = tuple(x for x in current.predicates if x != clause)
        if not predicates:
            continue
        proposed = replace(current, predicates=predicates)
        outcomes = evaluate(proposed)
        if any(
            x.partition != "dev" or x.contract_id != proposed.contract_id
            for x in outcomes
        ):
            raise ValueError("minimization requires matched development replay")
        if set(proposed.source_tasks) & {x.task_id for x in outcomes}:
            raise ValueError("minimization source/development leakage")
        metrics = replay_metrics(outcomes)
        keep = (
            metrics["unique_tasks"] >= policy.min_dev_tasks
            and metrics["beneficial_flips"] >= policy.min_beneficial_flips
            and metrics["net_gain"] > 0
            and metrics["harmful_flips"] <= policy.max_harmful_flips
            and not metrics["provider_failures"]
        )
        history.append(
            {
                "deleted": asdict(clause),
                "candidate_id": proposed.contract_id,
                "accepted_deletion": keep,
                "metrics": metrics,
            }
        )
        if keep:
            current = proposed
    return current, history
