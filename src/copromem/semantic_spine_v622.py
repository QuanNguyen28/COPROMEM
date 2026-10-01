"""Evidence-preserving semantic schema induction for CoProMem v6.2.2.

Unlike the legacy semantic projection, this module carries occurrence-level
redacted value-equality witnesses into the committed schema.  Public registry
dependencies describe callable compatibility only; they are never promoted to
observed dataflow.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from .contrastive_graph_v6 import Graph, canonical, digest
from .semantic_graph_v61 import semantic_plan, validate_semantic_plan


POLICY_VERSION = "copromem-v6.2.2-attested-semantic-spine-v1"
SCHEMA_CONTRACT_VERSION = "copromem-occurrence-dataflow-schema-v1"


def _alignment(graph: Graph, operations: Sequence[str]) -> list[int]:
    """Return the deterministic ordered-subsequence alignment."""
    result: list[int] = []
    cursor = 0
    for operation in operations:
        matches = [index for index in range(cursor, len(graph.nodes))
                   if graph.nodes[index].get("operation") == operation]
        if not matches:
            raise ValueError("required semantic occurrence is absent from supporting graph")
        result.append(matches[0])
        cursor = matches[0] + 1
    return result


def _attested_edges(graph: Graph, alignment: Sequence[int]) -> set[tuple[int, int, str, str]]:
    positions = {node_index: position for position, node_index in enumerate(alignment, 1)}
    result: set[tuple[int, int, str, str]] = set()
    for edge in graph.edges:
        if edge.get("kind") != "redacted_dataflow":
            continue
        left, right = edge.get("from"), edge.get("to")
        if left not in positions or right not in positions:
            continue
        producer = str(edge.get("producer_slot") or "")
        consumer = str(edge.get("consumer_slot") or "")
        if not producer or not consumer:
            raise ValueError("attested dataflow edge lacks typed endpoint slots")
        result.add((positions[int(left)], positions[int(right)], producer, consumer))
    return result


def _repetition_groups(occurrences: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    start = 0
    while start < len(occurrences):
        first = occurrences[start]
        end = start + 1
        signature = (first["operation"], tuple(first["required_inputs"]), tuple(first["outputs"]))
        while end < len(occurrences):
            row = occurrences[end]
            if (row["operation"], tuple(row["required_inputs"]), tuple(row["outputs"])) != signature:
                break
            end += 1
        if end - start > 1:
            groups.append({"operation": first["operation"], "start_position": start + 1,
                           "end_position": end, "count": end - start,
                           "occurrence_ids": [row["occurrence_id"] for row in occurrences[start:end]],
                           "rendering": "parameterized_consecutive_repetition"})
        start = end
    return groups


def plan(success: list[Graph], failed: list[Graph], pre_state: Mapping[str, Any],
         audits: list[dict[str, Any]]) -> dict[str, Any]:
    """Induce a schema while retaining only dataflow witnessed in every success."""
    base = semantic_plan(success, failed, pre_state, audits)
    schema = dict(base["schema"])
    required = tuple(str(item) for item in schema.get("required_operations", ()))
    if not success or not required:
        return base
    alignments = [_alignment(graph, required) for graph in success]
    first = success[0]
    occurrence_counts: dict[str, int] = {}
    occurrences: list[dict[str, Any]] = []
    for position, node_index in enumerate(alignments[0], 1):
        node = first.nodes[node_index]
        operation = str(node["operation"])
        occurrence_counts[operation] = occurrence_counts.get(operation, 0) + 1
        occurrences.append({
            "position": position,
            "occurrence_id": f"{operation}#{occurrence_counts[operation]}",
            "operation": operation,
            "effect_class": str(node.get("effect_class") or ""),
            "required_inputs": [str(item) for item in node.get("public_required", ())],
            "outputs": [str(item) for item in node.get("output_slots", ())],
        })
    common_edges = set.intersection(*[_attested_edges(graph, alignment)
                                      for graph, alignment in zip(success, alignments)])
    edges = [{"from_occurrence_id": occurrences[left - 1]["occurrence_id"],
              "to_occurrence_id": occurrences[right - 1]["occurrence_id"],
              "producer_slot": producer, "consumer_slot": consumer,
              "attestation": "redacted_value_equality_in_every_success"}
             for left, right, producer, consumer in sorted(common_edges)]
    terminal_operation = str(schema.get("terminal_effect") or "")
    terminal_candidates = [row for row in occurrences
                           if row["operation"] == terminal_operation and row["effect_class"] == "write"]
    if not terminal_candidates:
        terminal_candidates = [row for row in occurrences if row["operation"] == terminal_operation]
    groups = _repetition_groups(occurrences)
    terminal_ids = [row["occurrence_id"] for row in terminal_candidates]
    terminal_group = next((group for group in groups if group["occurrence_ids"] == terminal_ids), None)
    terminal_id = (terminal_candidates[0]["occurrence_id"] if len(terminal_candidates) == 1
                   else f"repetition-group:{terminal_group['start_position']}-{terminal_group['end_position']}"
                   if terminal_group is not None else None)
    schema.update({
        "policy_version": POLICY_VERSION,
        "schema_contract_version": SCHEMA_CONTRACT_VERSION,
        "occurrences": occurrences,
        "terminal_occurrence_id": terminal_id,
        "terminal_occurrence_ids": terminal_ids,
        "terminal_occurrence_ambiguous": len(terminal_candidates) != 1,
        "attested_dataflow_edges": edges,
        "dataflow_attestation_graph_sha256s": sorted(graph.sha256 for graph in success),
        "repetition_groups": groups,
        "typed_constraints": [{"operation": row["operation"], "occurrence_index": row["position"],
                               "required": row["required_inputs"], "outputs": row["outputs"]}
                              for row in occurrences],
    })
    result = {**base, "schema": schema, "plan_version": POLICY_VERSION}
    result["schema_id"] = f"schema_{digest(schema)[:16]}"
    result["plan_sha256"] = digest({key: value for key, value in result.items() if key != "plan_sha256"})
    return result


def validate(plan_record: Mapping[str, Any], registry: Mapping[str, Any]) -> dict[str, Any]:
    base = validate_semantic_plan(plan_record, registry)
    schema = plan_record.get("schema", {})
    reason: str | None = None
    if not base["passed"]:
        reason = str(base["reason"])
    elif schema.get("schema_contract_version") != SCHEMA_CONTRACT_VERSION:
        reason = "missing_occurrence_dataflow_contract"
    occurrences = schema.get("occurrences", ()) if isinstance(schema, Mapping) else ()
    if reason is None and (not isinstance(occurrences, Sequence) or not occurrences):
        reason = "missing_semantic_occurrences"
    ids = [row.get("occurrence_id") for row in occurrences if isinstance(row, Mapping)]
    if reason is None and (len(ids) != len(occurrences) or len(set(ids)) != len(ids)):
        reason = "invalid_occurrence_identity"
    terminal_ids = schema.get("terminal_occurrence_ids", ()) if isinstance(schema, Mapping) else ()
    if reason is None:
        if not isinstance(terminal_ids, Sequence) or not terminal_ids or any(item not in ids for item in terminal_ids):
            reason = "ambiguous_or_missing_terminal_occurrence"
        elif len(terminal_ids) == 1 and schema.get("terminal_occurrence_id") != terminal_ids[0]:
            reason = "terminal_occurrence_identity_mismatch"
        elif len(terminal_ids) > 1:
            groups = schema.get("repetition_groups", ())
            matching = [group for group in groups if isinstance(group, Mapping)
                        and list(group.get("occurrence_ids", ())) == list(terminal_ids)]
            if len(matching) != 1 or schema.get("terminal_occurrence_id") != f"repetition-group:{matching[0]['start_position']}-{matching[0]['end_position']}":
                reason = "ambiguous_terminal_repetition"
    by_id = {str(row["occurrence_id"]): row for row in occurrences if isinstance(row, Mapping) and row.get("occurrence_id")}
    if reason is None:
        for edge in schema.get("attested_dataflow_edges", ()):
            if not isinstance(edge, Mapping):
                reason = "malformed_attested_dataflow_edge"; break
            source = by_id.get(str(edge.get("from_occurrence_id")))
            target = by_id.get(str(edge.get("to_occurrence_id")))
            if (source is None or target is None or source["position"] >= target["position"]
                    or edge.get("producer_slot") not in source.get("outputs", ())
                    or edge.get("consumer_slot") not in target.get("required_inputs", ())
                    or edge.get("attestation") != "redacted_value_equality_in_every_success"):
                reason = "invalid_attested_dataflow_edge"; break
    return {**base, "passed": reason is None, "reason": reason,
            "schema_contract_version": schema.get("schema_contract_version") if isinstance(schema, Mapping) else None,
            "validation_policy_version": POLICY_VERSION}


def commit(pre_state: Mapping[str, Any], plan_record: Mapping[str, Any],
           validation: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Commit only the exact semantically validated plan, never base validation."""
    before = digest(pre_state)
    validation_sha = digest(validation)
    if validation.get("plan_sha256") != plan_record.get("plan_sha256"):
        raise ValueError("semantic validation is not bound to the plan")
    if not validation.get("passed"):
        return dict(pre_state), {"state": "rejected", "winner_schema_id": None,
                                 "before_state_sha256": before, "after_state_sha256": before,
                                 "plan_sha256": plan_record.get("plan_sha256"),
                                 "semantic_validation_sha256": validation_sha}
    state = json.loads(canonical(pre_state))
    schemas = state.setdefault("contrastive_v6_schemas", {})
    schema_id = str(plan_record["schema_id"])
    existing = schemas.get(schema_id)
    if existing is not None and existing != plan_record["schema"]:
        raise ValueError("schema identity collision")
    schemas.setdefault(schema_id, plan_record["schema"])
    return state, {"state": "committed", "winner_schema_id": schema_id,
                   "before_state_sha256": before, "after_state_sha256": digest(state),
                   "plan_sha256": plan_record["plan_sha256"],
                   "semantic_validation_sha256": validation_sha,
                   "semantic_policy_version": POLICY_VERSION}
