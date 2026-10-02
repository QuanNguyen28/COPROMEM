"""Versioned semantic-spine retrieval for the CoProMem v6.2.2 ablation.

This deliberately does *not* change the frozen v6.2 common-core method or
the published v6.2.1 policy.  It is a separately identifiable retrieval
ablation that corrects three executor-facing defects: unrelated prerequisites
are excluded by public dataflow, semantic ties abstain, and repeated semantic
occurrences stay distinct through rendering and provenance.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from . import task_conditioned_retrieval_v621 as v621
from ...semantic_spine_v622 import POLICY_VERSION as LEARNING_POLICY_VERSION


POLICY_VERSION = "copromem-v6.2.2-semantic-spine-retrieval"
_GENERIC_SLOT_TOKENS = frozenset({"id", "name", "value", "data", "input", "output", "result", "item", "object"})

canonical = v621.canonical
digest = v621.digest
derive_task_query = v621.derive_task_query
validate_task_query = v621.validate_task_query


def frozen_policy() -> dict[str, Any]:
    value = {
        "policy_version": POLICY_VERSION,
        "base_common_core_policy": "copromem-v6.1-semantic-graph-v1",
        "selection": "unique_semantic_evidence_winner_or_empty_guidance",
        "tie_evidence": "distinct_nonterminal_operations_supported_by_public_task_query_not_success_count_or_schema_id",
        "semantic_projection": "terminal_closure_over_committed_occurrence_level_value_equality_witnesses_only",
        "external_input_guard": "queried_operation_and_all_non_generic_slot_concepts_supported_or_prior_attested_output",
        "cross_app_guard": "no_slot_name_or_registry_dependency_may_substitute_for_attested_value_equality",
        "occurrences": "all_positioned_occurrences_preserved_in_provenance_consecutive_identical_runs_parameterized_in_guidance",
        "deduplication": "no_semantic_occurrence_loss",
        "query_evidence": ["visible_instruction", "public_app_descriptions", "frozen_callable_registry"],
        "exclusions": ["hidden_state", "scorer", "current_or_future_actions", "task_specific_rules"],
        "fixed": "read_only",
        "dynamic": "exact_durable_pre_task_prefix_only",
        "reproduction": "canonical_JSON_UTF8_SHA256_and_full_provenance_equality",
    }
    return {**value, "policy_sha256": digest(value)}


def _typed_occurrences(schema: Mapping[str, Any], required: tuple[str, ...]) -> list[dict[str, Any]]:
    """Attach a public constraint to every required *occurrence*.

    Legacy schemas remain readable only where their constraints are
    unambiguous. A constraint may cover repeated occurrences solely when it
    explicitly declares ``reusable_for_occurrences=true``.
    """
    raw = schema.get("typed_constraints", ())
    if not isinstance(raw, Sequence):
        raise ValueError("schema typed constraints are malformed")
    by_operation: dict[str, list[Mapping[str, Any]]] = {}
    by_position: dict[int, Mapping[str, Any]] = {}
    for item in raw:
        if not isinstance(item, Mapping) or not isinstance(item.get("operation"), str):
            raise ValueError("schema typed constraint is malformed")
        by_operation.setdefault(str(item["operation"]), []).append(item)
        position = item.get("occurrence_index")
        if type(position) is int:
            if position in by_position:
                raise ValueError("schema has duplicate typed occurrence index")
            by_position[position] = item
        elif position is not None:
            raise ValueError("schema typed occurrence index is malformed")
    if by_position and set(by_position) != set(range(1, len(required) + 1)):
        raise ValueError("schema positional constraints do not cover every required occurrence")
    required_counts = {operation: required.count(operation) for operation in set(required)}
    if set(by_operation) - set(required_counts):
        raise ValueError("schema has typed constraints for a non-required operation")
    if not by_position:
        for operation, count in required_counts.items():
            choices = by_operation.get(operation, [])
            if len(choices) != count and not (len(choices) == 1 and choices[0].get("reusable_for_occurrences") is True):
                raise ValueError("typed constraints must cover occurrences exactly")
    seen: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for index, operation in enumerate(required, 1):
        seen[operation] = seen.get(operation, 0) + 1
        constraint = by_position.get(index)
        if constraint is not None and constraint["operation"] != operation:
            raise ValueError("typed occurrence operation differs from required order")
        if constraint is None:
            choices = by_operation.get(operation, [])
            if not choices:
                raise ValueError("schema required operation lacks typed public constraint")
            occurrence = seen[operation] - 1
            if occurrence < len(choices):
                constraint = choices[occurrence]
            elif len(choices) == 1 and choices[0].get("reusable_for_occurrences") is True:
                constraint = choices[0]
            else:
                raise ValueError("typed constraints do not cover every required occurrence")
        required_slots = tuple(str(item) for item in constraint.get("required", ()) if isinstance(item, str))
        outputs = tuple(str(item) for item in constraint.get("outputs", ()) if isinstance(item, str))
        rows.append({"position": index, "occurrence_id": f"{operation}#{seen[operation]}",
                     "operation": operation, "required_inputs": required_slots,
                     "outputs": outputs})
    return rows


def semantic_projection(schema: Mapping[str, Any], registry: Mapping[str, Any]) -> dict[str, Any]:
    """Return the response-attested public path around the terminal effect.

    A prior operation is retained only when it directly supplies a public
    input to a retained occurrence or is a declared public predecessor.  The
    backwards closure preserves genuine transitive prerequisites. A forward
    closure preserves dependent verification after the terminal effect.
    Unrelated setup, applications and entities stay out of guidance.
    """
    index = v621._operation_index(registry)
    required = tuple(str(item) for item in schema.get("required_operations", ()))
    terminal = str(schema.get("terminal_effect") or "")
    if not required or terminal not in required or any(item not in index for item in required):
        raise ValueError("schema lacks a declared terminal required operation")
    occurrences = _typed_occurrences(schema, required)
    by_id = {row["occurrence_id"]: row for row in occurrences}
    terminal_id = schema.get("terminal_occurrence_id")
    terminal_ids = schema.get("terminal_occurrence_ids")
    if isinstance(terminal_ids, Sequence) and not isinstance(terminal_ids, (str, bytes)) and terminal_ids:
        if any(item not in by_id or by_id[str(item)]["operation"] != terminal for item in terminal_ids):
            raise ValueError("terminal occurrence group is invalid")
        terminal_positions = {int(by_id[str(item)]["position"]) for item in terminal_ids}
    else:
        terminal_positions = set()
    if terminal_id is None:
        legacy = [row for row in occurrences if row["operation"] == terminal]
        if len(legacy) != 1:
            raise ValueError("terminal occurrence is ambiguous")
        terminal_id = legacy[0]["occurrence_id"]
    if not terminal_positions and (terminal_id not in by_id or by_id[str(terminal_id)]["operation"] != terminal):
        raise ValueError("terminal occurrence identity is invalid")
    if not terminal_positions:
        terminal_positions = {int(by_id[str(terminal_id)]["position"])}
    attested: list[tuple[int, int, str, str]] = []
    for edge in schema.get("attested_dataflow_edges", ()):
        if not isinstance(edge, Mapping):
            raise ValueError("attested dataflow edge is malformed")
        source = by_id.get(str(edge.get("from_occurrence_id")))
        target = by_id.get(str(edge.get("to_occurrence_id")))
        producer_slot = str(edge.get("producer_slot") or "")
        consumer_slot = str(edge.get("consumer_slot") or "")
        if (source is None or target is None or source["position"] >= target["position"]
                or producer_slot not in source["outputs"] or consumer_slot not in target["required_inputs"]
                or edge.get("attestation") != "redacted_value_equality_in_every_success"):
            raise ValueError("attested dataflow edge fails occurrence contract")
        attested.append((int(source["position"]), int(target["position"]), producer_slot, consumer_slot))
    retained = set(terminal_positions)
    retained_edges: set[tuple[int, int, str, str]] = set()
    # Iterate until a fixed point: newly kept predecessors can themselves
    # require a response-attested producer.
    changed = True
    while changed:
        changed = False
        for target in sorted(tuple(retained), reverse=True):
            for source_position, target_position, producer_slot, consumer_slot in attested:
                if target_position != target:
                    continue
                retained_edges.add((source_position, target, producer_slot, consumer_slot))
                if source_position not in retained:
                    retained.add(source_position); changed = True
    # A response-attested verification step can follow the terminal write.
    # Preserve only steps reachable *from* that terminal through public
    # dataflow or a declared dependency; plain chronology is insufficient.
    forward = set(terminal_positions)
    changed = True
    while changed:
        changed = False
        for source_position in sorted(tuple(forward)):
            for left, target_position, producer_slot, consumer_slot in attested:
                if left != source_position:
                    continue
                retained_edges.add((source_position, target_position, producer_slot, consumer_slot))
                if target_position not in forward:
                    forward.add(target_position); retained.add(target_position); changed = True
    rows = [row for row in occurrences if row["position"] in retained]
    # Edges are dependencies, not duplicate semantic operations.  Deduplicate
    # only exact occurrence-edge triples and serialize by source/target order.
    edges = [{"from_occurrence_id": occurrences[left - 1]["occurrence_id"],
              "to_occurrence_id": occurrences[right - 1]["occurrence_id"],
              "producer_slot": producer_slot, "consumer_slot": consumer_slot,
              "kind": "attested_redacted_value_equality"}
             for left, right, producer_slot, consumer_slot in sorted(retained_edges)]
    excluded = [row for row in occurrences if row["position"] not in retained]
    projection = {"terminal_effect": terminal, "terminal_occurrence_id": terminal_id,
                  "terminal_occurrence_ids": [occurrences[position - 1]["occurrence_id"] for position in sorted(terminal_positions)],
                  "occurrences": rows, "dataflow_edges": edges,
                  "excluded_occurrences": [{"occurrence_id": row["occurrence_id"], "operation": row["operation"],
                                             "reason": "not_on_terminal_public_dependency_closure"} for row in excluded]}
    projection["semantic_projection_sha256"] = digest(projection)
    return projection


def _slot_concepts(slot: str) -> set[str]:
    return {v621._stem(token) for token in v621._SPLIT.split(slot.lower())
            if token and v621._stem(token) not in _GENERIC_SLOT_TOKENS}


def _query_concepts(query_ops: Sequence[str]) -> set[str]:
    concepts: set[str] = set()
    for operation in query_ops:
        _app, verb, nouns = v621._operation_tokens(operation)
        concepts.update((verb, *nouns))
    return concepts


def _features(schema_id: str, schema: Mapping[str, Any], query: Mapping[str, Any],
              registry: Mapping[str, Any]) -> dict[str, Any]:
    query_ops = tuple(str(item) for item in query.get("canonical_query_operations", ()))
    descriptor = query.get("derived_public_descriptor", {})
    named_apps = set(descriptor.get("relevant_public_apps", ())) if isinstance(descriptor, Mapping) else set()
    support = schema.get("support", {})
    reasons: list[str] = []
    if schema.get("registry_sha256") != registry.get("registry_sha256"):
        reasons.append("registry_hash_mismatch")
    if not isinstance(support, Mapping) or int(support.get("successes", 0)) < 2:
        reasons.append("insufficient_positive_success_support")
    try:
        projection = semantic_projection(schema, registry)
    except ValueError as exc:
        projection = {"occurrences": [], "dataflow_edges": [], "semantic_projection_sha256": ""}
        reasons.append(f"semantic_projection_invalid:{exc}")
    terminal = str(schema.get("terminal_effect") or "")
    index = v621._operation_index(registry)
    terminal_app = v621._operation_tokens(terminal)[0] if terminal in index else None
    if terminal not in query_ops:
        reasons.append("terminal_effect_not_supported_by_public_query")
    if named_apps and terminal_app not in named_apps:
        reasons.append("terminal_app_not_publicly_relevant")
    query_concepts = _query_concepts(query_ops)
    incoming = {(str(edge["to_occurrence_id"]), str(edge["consumer_slot"]))
                for edge in projection.get("dataflow_edges", ())}
    unsupported_inputs: list[dict[str, str]] = []
    unsupported_apps: list[str] = []
    for row in projection.get("occurrences", []):
        operation = str(row["operation"])
        app = v621._operation_tokens(operation)[0]
        if app != terminal_app and app not in named_apps:
            unsupported_apps.append(operation)
        for slot in row["required_inputs"]:
            concepts = _slot_concepts(slot)
            # A matching noun in a callable name alone cannot establish that
            # an unobserved prerequisite has usable task input.  External
            # slots require this very operation to be supported by the public
            # task query; otherwise only an earlier attested output suffices.
            supported_by_edge = (str(row["occurrence_id"]), slot) in incoming
            if not supported_by_edge and (operation not in query_ops or not concepts or
                                          not concepts <= query_concepts):
                unsupported_inputs.append({"operation": operation, "input": slot})
    if unsupported_apps:
        reasons.append("prerequisite_app_not_publicly_relevant")
    if unsupported_inputs:
        reasons.append("prerequisite_input_not_supported_by_public_query_or_dataflow")
    nonsemantic = []
    for row in projection.get("occurrences", []):
        operation = str(row["operation"])
        app, verb, nouns = v621._operation_tokens(operation)
        if app in v621._NON_SEMANTIC_APPS or verb in v621._AUTH_RUNTIME_TERMS or any(noun in v621._AUTH_RUNTIME_TERMS for noun in nouns):
            nonsemantic.append(operation)
    if nonsemantic:
        reasons.append("semantic_projection_contains_nonsemantic_operation")
    compatible = not reasons
    # Success frequency is evidence that a schema was learned, but cannot
    # distinguish which of two procedures fits this *new* public task.
    # Only operation matches supplied by the task query may break a tie.
    matched_nonterminal = {row["operation"] for row in projection.get("occurrences", [])
                           if row["operation"] != terminal and row["operation"] in query_ops}
    semantic_evidence = (len(matched_nonterminal),)
    return {"schema_id": schema_id, "compatible": compatible,
            "rejection_reason": reasons[0] if reasons else None, "rejection_reasons": reasons,
            "terminal_effect": terminal, "terminal_effect_supported": terminal in query_ops,
            "semantic_projection": projection, "semantic_projection_sha256": projection.get("semantic_projection_sha256"),
            "schema_operation_apps": sorted({v621._operation_tokens(str(row["operation"]))[0] for row in projection.get("occurrences", [])}),
            "nonsemantic_operations": sorted(nonsemantic), "unsupported_public_inputs": unsupported_inputs,
            "unsupported_prerequisite_apps": unsupported_apps,
            "semantic_evidence": list(semantic_evidence),
            "score": list(semantic_evidence) if compatible else [0]}


def _guidance(features: Mapping[str, Any]) -> str:
    projection = features["semantic_projection"]
    lines = ["# Retrieved dispatcher-attested semantic schema", f"Terminal public effect: {features['terminal_effect']}"]
    incoming = {(str(edge["to_occurrence_id"]), str(edge["consumer_slot"]))
                for edge in projection.get("dataflow_edges", ())}
    rows = list(projection["occurrences"])
    cursor = 0
    while cursor < len(rows):
        row = rows[cursor]
        end = cursor + 1
        signature = (row["operation"], tuple(row["required_inputs"]), tuple(row["outputs"]))
        while end < len(rows):
            other = rows[end]
            if (other["operation"], tuple(other["required_inputs"]), tuple(other["outputs"])) != signature:
                break
            end += 1
        required = ", ".join(row["required_inputs"]) or "no declared public input"
        outputs = ", ".join(row["outputs"]) or "no declared public output"
        external = [slot for slot in row["required_inputs"]
                    if (str(row["occurrence_id"]), slot) not in incoming]
        caution = ("; verify current-task values for external inputs before use: " + ", ".join(external)
                   if external else "")
        group = rows[cursor:end]
        if len(group) == 1:
            lines.append(f"{row['position']}. [{row['occurrence_id']}] {row['operation']}; public inputs: {required}; public outputs: {outputs}{caution}.")
        else:
            occurrence_inventory = digest([item["occurrence_id"] for item in group])
            lines.append(f"{row['position']}-{group[-1]['position']}. Repeat {row['operation']} for each current-task item ({len(group)} attested occurrences; occurrence inventory {occurrence_inventory}); public inputs per item: {required}; public outputs per item: {outputs}{caution}.")
        cursor = end
    return "\n".join(lines)


def _schema_rows(state: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    raw = state.get("contrastive_v6_schemas", {})
    if not isinstance(raw, Mapping):
        raise ValueError("semantic bank schema container is malformed")
    accepted = {"copromem-v6.1-semantic-graph-v1", LEARNING_POLICY_VERSION}
    return {str(schema_id): schema for schema_id, schema in raw.items()
            if isinstance(schema_id, str) and isinstance(schema, Mapping)
            and schema.get("policy_version") in accepted}


def retrieve(state: Mapping[str, Any], task_query: Mapping[str, Any], callable_registry: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    if task_query.get("callable_registry_sha256") != callable_registry.get("registry_sha256"):
        raise ValueError("task query registry identity mismatch")
    rows = _schema_rows(state)
    # Sorting is serialization only; selection below never uses ID/order.
    candidates = [_features(schema_id, schema, task_query, callable_registry)
                  for schema_id, schema in sorted(rows.items())]
    compatible = [item for item in candidates if item["compatible"]]
    best_evidence = max((tuple(item["semantic_evidence"]) for item in compatible), default=None)
    top = [item for item in compatible if tuple(item["semantic_evidence"]) == best_evidence] if best_evidence else []
    selected = top[0] if len(top) == 1 else None
    decision = "unique_semantic_winner" if selected else ("semantic_tie_abstention" if top else "no_compatible_schema")
    guidance = _guidance(selected) if selected else ""
    provenance = {"policy_version": POLICY_VERSION, "policy_sha256": frozen_policy()["policy_sha256"],
                  "pre_state_semantic_sha256": digest(state), "task_query": dict(task_query),
                  "task_query_sha256": str(task_query.get("query_sha256") or ""),
                  "registry_sha256": str(callable_registry["registry_sha256"]),
                  "candidate_schema_ids": [item["schema_id"] for item in candidates], "candidate_scores": candidates,
                  "semantic_winner_candidate_ids": [item["schema_id"] for item in top],
                  "selection_decision": decision, "selected_schema_id": selected["schema_id"] if selected else None,
                  "selected_schema_ids": [selected["schema_id"]] if selected else [],
                  "fallback_category": "learned_schema" if selected else "empty_ambiguous_or_incompatible",
                  "fallback_reason": None if selected else decision,
                  "guidance_sha256": digest(guidance), "guidance_nonempty": bool(guidance),
                  "prompt_injection_sha256": digest(guidance), "reproduction_version": POLICY_VERSION}
    provenance["retrieval_sha256"] = digest(provenance)
    return guidance, provenance


def reproduce_retrieval(state: Mapping[str, Any], task_query: Mapping[str, Any], callable_registry: Mapping[str, Any],
                         provenance: Mapping[str, Any]) -> str:
    if digest(state) != provenance.get("pre_state_semantic_sha256"):
        raise ValueError("retrieval pre-state mismatch")
    if dict(task_query) != provenance.get("task_query"):
        raise ValueError("retrieval task-query mismatch")
    guidance, expected = retrieve(state, task_query, callable_registry)
    observed_json = json.loads(json.dumps(provenance, ensure_ascii=False, sort_keys=True))
    expected_json = json.loads(json.dumps(expected, ensure_ascii=False, sort_keys=True))
    if observed_json != expected_json:
        raise ValueError("retrieval provenance mismatch")
    return guidance
