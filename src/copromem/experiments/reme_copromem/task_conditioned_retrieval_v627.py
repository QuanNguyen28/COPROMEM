"""v6.2.7 relevant-app terminal-slice retrieval.

The v6.2.4 admission path proved one learned Venmo schema can reach the
executor prompt, but its all-description matching made almost every public
instruction abstain. This version keeps admission, named-app, exact registry,
and evidence tie rules. It relaxes only the public expression of a known,
admitted terminal operation. Guidance contains the admitted terminal slice
only; no unproven prerequisite from the learned trajectory is injected.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from . import task_conditioned_retrieval_v624 as v624
from .public_operation_intent_registry import verify as verify_intents
from .schema_multi_admission import verify as verify_multi_admission


base = v624.base
POLICY_VERSION = "copromem-v6.2.7-multi-schema-relevant-app-terminal-slice"
_STOP = frozenset({"a", "an", "the", "to", "for", "of", "in", "on", "with", "and", "or", "from",
                   "your", "you", "my", "i", "this", "that", "all", "each", "any", "via"})
_CURRENCY = re.compile(r"[$€£]\s*\d")
_RECIPIENT = re.compile(r"\b(?:to|for)\s+(?:[A-Z][\w-]*|him|her|them|each|every)\b", re.I)
_VENMO_PRONOUN = re.compile(r"\bvenmo\s+(?:him|her|them)\b", re.I)
_PAST_CONTEXT = re.compile(r"\b(?:yesterday|previously|before|ago|last\s+\w+)\b", re.I)

# Task-independent surface variants of public OpenAPI terminology. They
# identify a documented operation but never prove a missing prerequisite.
_ACTION_SURFACES: dict[str, frozenset[str]] = {
    "create": frozenset({"create", "make", "send", "pay", "transfer", "venmo"}),
    "show": frozenset({"show", "list", "find", "search", "view", "history", "get"}),
    "update": frozenset({"update", "edit", "modify", "change"}),
    "delete": frozenset({"delete", "remove"}),
}
_CONCEPT_SURFACES: dict[str, frozenset[str]] = {
    "money": frozenset({"money", "payment", "payments", "amount", "amounts", "cash", "transfer", "transfers"}),
    "transaction": frozenset({"transaction", "transactions", "payment", "payments", "transfer", "transfers"}),
    "user": frozenset({"user", "users", "person", "people", "recipient", "recipients", "receiver", "receivers"}),
    "note": frozenset({"note", "notes", "log", "logs"}),
}


def _json_native(value: Any) -> dict[str, Any]:
    frozen = json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")))
    if not isinstance(frozen, dict):
        raise TypeError("v6.2.5 provenance must be a JSON object")
    return frozen


def _tokens(instruction: str) -> set[str]:
    values = set(base.v621._tokens(instruction))
    if _CURRENCY.search(instruction):
        values.update({"money", "amount"})
    if _RECIPIENT.search(instruction) or _VENMO_PRONOUN.search(instruction):
        values.update({"user", "recipient", "receiver"})
    return values


def _concept_match(term: str, tokens: set[str]) -> tuple[str, ...]:
    surfaces = _CONCEPT_SURFACES.get(term, frozenset({term}))
    return tuple(sorted(surfaces & tokens))


def _operation_match(item: Mapping[str, Any], *, tokens: set[str], instruction: str) -> dict[str, Any] | None:
    """Return deterministic public evidence for one operation, or no match."""
    operation = item.get("operation")
    app = item.get("app")
    if not isinstance(operation, str) or not isinstance(app, str):
        raise ValueError("public intent operation is malformed")
    op_app, verb, nouns = base.v621._operation_tokens(operation)
    if op_app != app:
        raise ValueError("public intent app disagrees with canonical operation")
    action = tuple(sorted(_ACTION_SURFACES.get(verb, frozenset({verb})) & tokens))
    # The app name acts as an imperative only in the public command form
    # ("Venmo her ...").  A past-tense mention of Venmo never licenses a
    # transfer pattern for a different requested action.
    if operation == "apis.venmo.create_transaction" and "venmo" in action and not _VENMO_PRONOUN.search(instruction):
        action = tuple(value for value in action if value != "venmo")
    if not action:
        return None
    desc = {str(value) for value in item.get("description_tokens", ()) if isinstance(value, str)}
    object_terms = sorted({term for term in {*nouns, *desc} if term not in _STOP
                           and term not in _ACTION_SURFACES.get(verb, frozenset())})
    matched: dict[str, tuple[str, ...]] = {}
    for term in object_terms:
        values = _concept_match(term, tokens)
        if values:
            matched[term] = values
    if not matched:
        return None
    # A transfer must contain direct transfer evidence. Merely saying
    # "payment request" or creating an account has no transfer authority.
    if operation == "apis.venmo.create_transaction":
        transfer_object = bool({"money", "transaction"} & set(matched))
        recipient = bool({"user"} & set(matched))
        direct_verb = bool({"send", "pay", "transfer"} & set(action))
        if not transfer_object or not (recipient or direct_verb):
            return None
        if "request" in tokens and not ("send" in action or "transfer" in action or "pay" in action):
            return None
    return {
        "operation": operation,
        "app": app,
        "verb": verb,
        "matched_action_terms": list(action),
        "matched_object_terms": [{"documented_term": term, "instruction_terms": list(values)}
                                 for term, values in sorted(matched.items())],
        "public_access_mode": "documented_safe_terminal_slice",
        "match_mode": "named_app_action_and_object_public_intent_v1",
    }


def derive_task_query(instruction: str, domain: str, public_tool_metadata: Mapping[str, Any],
                      callable_registry: Mapping[str, Any]) -> dict[str, Any]:
    """Derive reproducible public candidates without guessing prerequisites."""
    base_query = base.derive_task_query(instruction, domain, public_tool_metadata, callable_registry)
    intents = public_tool_metadata.get("public_operation_intents")
    if not isinstance(intents, Mapping):
        raise ValueError("v6.2.5 requires frozen public operation intents")
    verify_intents(intents)
    named = set(base_query["derived_public_descriptor"]["relevant_public_apps"])
    # A public app named only as completed historical context cannot activate
    # the experimental same-app relaxation. Exact v6.2.5 evidence remains
    # available independently through safe_terminal_operations.
    relaxed_apps = set() if _PAST_CONTEXT.search(instruction) else set(named)
    tokens = _tokens(instruction)
    evidence = []
    for item in intents["operations"]:
        if item.get("app") not in named:
            continue
        match = _operation_match(item, tokens=tokens, instruction=instruction)
        if match is not None:
            evidence.append(match)
    by_operation: dict[str, dict[str, Any]] = {}
    for item in evidence:
        prior = by_operation.setdefault(item["operation"], item)
        if prior != item:
            raise ValueError("conflicting public evidence for the same operation")
    exact = sorted(by_operation.values(), key=lambda row: row["operation"])
    existing = {str(row["operation"]) for row in base_query["operation_evidence"]}
    combined = sorted([*base_query["operation_evidence"],
                       *(row for row in exact if row["operation"] not in existing)],
                      key=lambda row: str(row["operation"]))
    operations = [str(row["operation"]) for row in combined]
    out = {
        **base_query,
        "policy_version": POLICY_VERSION,
        "operation_evidence": combined,
        "canonical_query_operations": operations,
        "query_operations": operations,
        "safe_terminal_operation_evidence": exact,
        "safe_terminal_operations": [row["operation"] for row in exact],
        "relaxed_relevant_public_apps": sorted(relaxed_apps),
        "intent_registry_sha256": intents["intent_registry_sha256"],
        "derived_public_descriptor": {**base_query["derived_public_descriptor"],
                                       "candidate_operations": operations},
    }
    out["query_sha256"] = base.digest({key: value for key, value in out.items() if key != "query_sha256"})
    return out


def validate_task_query(record: Mapping[str, Any], *, instruction: str,
                        public_tool_metadata: Mapping[str, Any],
                        callable_registry: Mapping[str, Any]) -> None:
    descriptor = record.get("derived_public_descriptor")
    if not isinstance(descriptor, Mapping):
        raise ValueError("v6.2.5 query lacks descriptor")
    expected = derive_task_query(instruction, str(descriptor.get("domain") or ""),
                                 public_tool_metadata, callable_registry)
    if dict(record) != expected:
        raise ValueError("v6.2.5 query does not reproduce")


def _terminal_occurrence(schema: Mapping[str, Any], operation: str) -> Mapping[str, Any]:
    rows = base._typed_occurrences(schema, tuple(str(x) for x in schema.get("required_operations", ())))
    terminal = str(schema.get("terminal_effect") or "")
    if terminal != operation:
        raise ValueError("schema terminal differs from requested operation")
    values = [row for row in rows if row["operation"] == terminal]
    if len(values) != 1:
        raise ValueError("schema terminal occurrence is ambiguous")
    return values[0]


def _candidate(schema_id: str, schema: Mapping[str, Any], query: Mapping[str, Any],
               registry: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if schema.get("registry_sha256") != registry.get("registry_sha256"):
        reasons.append("registry_hash_mismatch")
    support = schema.get("support", {})
    if not isinstance(support, Mapping) or int(support.get("successes", 0)) < 2:
        reasons.append("insufficient_positive_success_support")
    terminal = str(schema.get("terminal_effect") or "")
    index = base.v621._operation_index(registry)
    if terminal not in index:
        reasons.append("terminal_not_in_registry")
    named = set(query.get("derived_public_descriptor", {}).get("relevant_public_apps", ()))
    if terminal in index and base.v621._operation_tokens(terminal)[0] not in named:
        reasons.append("terminal_app_not_publicly_relevant")
    exact_task_support = terminal in set(query.get("safe_terminal_operations", ()))
    relevant_app_support = terminal in index and base.v621._operation_tokens(terminal)[0] in set(query.get("relaxed_relevant_public_apps", ()))
    # v6.2.7 permits a unique admitted terminal capability for a publicly
    # relevant app even if the task does not name that exact terminal effect.
    # Registry identity, positive support, same-app, unique-winner, and
    # terminal-only rendering remain mandatory.
    if not exact_task_support and not relevant_app_support:
        reasons.append("terminal_effect_not_supported_by_relevant_public_app")
    occurrence: Mapping[str, Any] | None = None
    if not reasons:
        try:
            occurrence = _terminal_occurrence(schema, terminal)
        except ValueError as exc:
            reasons.append(f"safe_terminal_slice_invalid:{exc}")
    return {
        "schema_id": schema_id,
        "compatible": not reasons,
        "rejection_reason": reasons[0] if reasons else None,
        "rejection_reasons": reasons,
        "terminal_effect": terminal,
        "terminal_support_mode": (
            "exact_task_public_intent" if exact_task_support else
            "relevant_public_app_admitted_terminal" if relevant_app_support else None
        ),
        "terminal_occurrence": dict(occurrence) if occurrence is not None else None,
        "semantic_evidence": [terminal, "exact_task_public_intent" if exact_task_support
                              else "relevant_public_app_admitted_terminal"] if not reasons else [],
    }


def _guidance(candidate: Mapping[str, Any]) -> str:
    row = candidate["terminal_occurrence"]
    inputs = ", ".join(str(value) for value in row["required_inputs"]) or "no declared public input"
    outputs = ", ".join(str(value) for value in row["outputs"]) or "no declared public output"
    mode = str(candidate["terminal_support_mode"])
    heading = ("Task-supported public effect" if mode == "exact_task_public_intent"
               else "Retrieved admitted terminal capability for a task-relevant public app")
    return "\n".join((
        "# Retrieved admitted relevant-app terminal slice",
        f"{heading}: {candidate['terminal_effect']}",
        "Use only this terminal operation with current-task public values; do not infer or repeat unproven prerequisites.",
        f"Public inputs: {inputs}; public outputs: {outputs}.",
    ))


def _terminal_slice_identity(candidate: Mapping[str, Any]) -> str:
    """Identity of the only bytes eligible for prompt injection.

    Different learned paths may have the same safe terminal slice.  They form
    one semantic equivalence class; this never selects a schema by id/order.
    """
    occurrence = candidate.get("terminal_occurrence")
    if not isinstance(occurrence, Mapping):
        raise ValueError("compatible candidate has no terminal occurrence")
    return base.digest({
        "terminal_effect": candidate.get("terminal_effect"),
        "terminal_support_mode": candidate.get("terminal_support_mode"),
        "terminal_occurrence": dict(occurrence),
    })


def retrieve(state: Mapping[str, Any], task_query: Mapping[str, Any],
             callable_registry: Mapping[str, Any], admission: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Retrieve only from independently admitted, byte-bound schema slices.

    The caller supplies a v6.2.7 multi-schema bundle.  A live Dynamic state
    may gain support counts, but each admitted terminal slice has to retain
    exactly the semantic identity externally validated for that schema.
    """
    bank = base.digest(state)
    if task_query.get("callable_registry_sha256") != callable_registry.get("registry_sha256"):
        raise ValueError("v6.2.7 task query registry mismatch")
    schemas = base._schema_rows(state)
    admitted = verify_multi_admission(admission, policy_sha256=frozen_policy()["policy_sha256"], schemas=schemas)
    candidates = [_candidate(schema_id, schema, task_query, callable_registry)
                  for schema_id, schema in sorted(admitted.items())]
    compatible = [item for item in candidates if item["compatible"]]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in compatible:
        grouped.setdefault(_terminal_slice_identity(item), []).append(item)
    # More than one distinct safe terminal slice is semantic ambiguity.  For
    # duplicate identical slices, render the common slice and record every
    # contributing schema; no ID/support/order tie breaker is used.
    winner_id = next(iter(grouped)) if len(grouped) == 1 else None
    winners = grouped.get(winner_id, []) if winner_id else []
    selected = winners[0] if winners else None
    selected_ids = [item["schema_id"] for item in winners]
    decision = (
        "admitted_exact_safe_terminal_slice" if selected and selected["terminal_support_mode"] == "exact_task_public_intent" else
        "admitted_relevant_app_terminal_slice" if selected else
        "semantic_tie_abstention" if compatible else "no_compatible_admitted_schema"
    )
    guidance = _guidance(selected) if selected else ""
    provenance = _json_native({
        "policy_version": POLICY_VERSION,
        "policy_sha256": frozen_policy()["policy_sha256"],
        "retrieval_mode": "multi_schema_admitted_relevant_app_terminal_slice",
        "pre_state_semantic_sha256": bank,
        "task_query": dict(task_query),
        "task_query_sha256": task_query["query_sha256"],
        "registry_sha256": callable_registry["registry_sha256"],
        "multi_schema_admission_bundle_sha256": admission["bundle_sha256"],
        "candidate_schema_ids": [item["schema_id"] for item in candidates],
        "candidate_scores": candidates,
        "semantic_winner_candidate_ids": selected_ids,
        "selected_schema_id": selected_ids[0] if len(selected_ids) == 1 else None,
        "selected_schema_ids": selected_ids,
        "selected_terminal_slice_sha256": winner_id,
        "selection_decision": decision,
        "guidance": guidance,
        "guidance_sha256": base.digest(guidance),
        "guidance_nonempty": bool(guidance),
    })
    provenance["retrieval_sha256"] = base.digest(provenance)
    return guidance, provenance

def candidate_validation_retrieve(state: Mapping[str, Any], task_query: Mapping[str, Any],
                                  callable_registry: Mapping[str, Any], *, schema_id: str,
                                  validation_task_id: str, current_task_id: str) -> tuple[str, dict[str, Any]]:
    """Materialize one isolated, non-admitted safe slice for validation.

    This is deliberately a distinct provenance mode.  Its sole purpose is to
    create the custody evidence used by the later admission receipt; it can
    never be replayed as an admitted retrieval.
    """
    if current_task_id != validation_task_id:
        raise ValueError("candidate validation task identity mismatch")
    if task_query.get("callable_registry_sha256") != callable_registry.get("registry_sha256"):
        raise ValueError("v6.2.7 task query registry mismatch")
    rows = base._schema_rows(state)
    schema = rows.get(schema_id)
    if schema is None:
        raise ValueError("candidate validation schema is absent")
    candidate = _candidate(schema_id, schema, task_query, callable_registry)
    if not candidate["compatible"]:
        raise ValueError("candidate validation has no safe task-supported terminal slice")
    guidance = _guidance(candidate)
    provenance = _json_native({
        "policy_version": POLICY_VERSION,
        "policy_sha256": frozen_policy()["policy_sha256"],
        "retrieval_mode": "isolated_relevant_app_terminal_slice_candidate_validation",
        "validation_task_id": validation_task_id,
        "candidate_schema_id": schema_id,
        "pre_state_semantic_sha256": base.digest(state),
        "task_query": dict(task_query),
        "task_query_sha256": task_query["query_sha256"],
        "registry_sha256": callable_registry["registry_sha256"],
        "candidate_score": candidate,
        "guidance": guidance,
        "guidance_sha256": base.digest(guidance),
        "guidance_nonempty": True,
    })
    provenance["retrieval_sha256"] = base.digest(provenance)
    return guidance, provenance


def frozen_policy() -> dict[str, Any]:
    value = {
        "policy_version": POLICY_VERSION,
        "base_policy": v624.POLICY_VERSION,
        "terminal_evidence": "exact_task_public_intent_or_relevant_public_app",
        "admission": "one-or-more independently externally attested byte-bound schemas",
        "selection": "one_compatible_terminal_slice_or_semantic_tie_abstention",
        "guidance": "terminal_slice_only_without_learned_prerequisites",
        "cross_app_guard": "retained",
        "unproven_prerequisite_guard": "retained_by_exclusion_from_guidance",
        "occurrence_order": "terminal occurrence identity is preserved",
        "tie_breaking": "no_schema_id_or_support_tie_breaking",
    }
    return {**value, "policy_sha256": base.digest(value)}


def reproduce_retrieval(state: Mapping[str, Any], task_query: Mapping[str, Any],
                        callable_registry: Mapping[str, Any],
                        provenance: Mapping[str, Any],
                        admission: Mapping[str, Any] | None = None) -> str:
    if base.digest(state) != provenance.get("pre_state_semantic_sha256"):
        raise ValueError("v6.2.7 retrieval pre-state mismatch")
    if dict(task_query) != provenance.get("task_query"):
        raise ValueError("v6.2.7 retrieval task query mismatch")
    mode = provenance.get("retrieval_mode")
    if mode == "isolated_relevant_app_terminal_slice_candidate_validation":
        guidance, expected = candidate_validation_retrieve(
            state, task_query, callable_registry,
            schema_id=str(provenance.get("candidate_schema_id") or ""),
            validation_task_id=str(provenance.get("validation_task_id") or ""),
            current_task_id=str(provenance.get("validation_task_id") or ""),
        )
    elif mode == "multi_schema_admitted_relevant_app_terminal_slice":
        if admission is None:
            raise ValueError("admitted v6.2.7 retrieval lacks multi-schema admission")
        guidance, expected = retrieve(state, task_query, callable_registry, admission)
    else:
        raise ValueError("unknown v6.2.7 retrieval provenance mode")
    if dict(provenance) != expected:
        raise ValueError("v6.2.7 retrieval provenance does not reproduce exactly")
    return guidance


