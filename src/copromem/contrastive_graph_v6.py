"""Deterministic, value-redacted contrastive execution-graph memory (v6).

This module has no model or benchmark dependency.  It accepts only dispatcher
evidence produced by ``public-execution-evidence-v1`` plus aggregate success.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


POLICY_VERSION = "copromem-v6-contrastive-graph-v1"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


@dataclass(frozen=True)
class Graph:
    registry_sha256: str
    nodes: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, Any], ...]
    sha256: str


def _node(row: Mapping[str, Any], registry: Mapping[str, Any]) -> dict[str, Any]:
    signature = row.get("operation_signature")
    if not isinstance(signature, Mapping) or not row.get("schema_accepted") or not row.get("response_success"):
        raise ValueError("only response-attested schema-valid dispatcher events may enter v6 graphs")
    operation = signature.get("operation")
    meta = next((item for item in registry.get("operations", []) if item.get("operation") == operation), None)
    if not isinstance(meta, Mapping):
        raise ValueError("event operation is absent from frozen callable registry")
    # Invocation and response digests are retained only as equality witnesses.
    inputs = row.get("invocation_value_hashes", {})
    outputs = row.get("response_output_value_hashes", {})
    if not isinstance(inputs, Mapping) or not isinstance(outputs, Mapping):
        raise ValueError("evidence does not contain redacted dataflow hashes")
    return {"operation": operation, "application": signature.get("application"),
            "callable_name": signature.get("callable_name"), "effect_class": meta.get("access_mode"),
            "inputs": sorted({str(key): str(value) for key, value in inputs.items()}.items()),
            "outputs": sorted({str(key): str(value) for key, value in outputs.items()}.items()),
            "public_required": list(signature.get("public_required", [])),
            "output_slots": list(signature.get("output_slots", [])),
            "index": int(row["monotonic_index"]), "response_class": str(row.get("response_error_class") or "success")}


def build_graph(records: Iterable[Mapping[str, Any]], registry: Mapping[str, Any]) -> Graph:
    """Build a replayable public graph; concrete values never leave telemetry."""
    registry_hash = str(registry.get("registry_sha256", ""))
    if not registry_hash:
        raise ValueError("frozen callable registry required")
    nodes = tuple(_node(row, registry) for row in sorted(records, key=lambda item: int(item["monotonic_index"])))
    edges: list[dict[str, Any]] = []
    for right in range(1, len(nodes)):
        edges.append({"kind": "order", "from": right - 1, "to": right})
    declared = {(row["from_operation"], row["to_operation"]) for row in registry.get("dependency_edges", [])}
    for left, producer in enumerate(nodes):
        outputs = dict(producer["outputs"])
        for right, consumer in enumerate(nodes[left + 1:], left + 1):
            for output_name, output_hash in outputs.items():
                for input_name, input_hash in dict(consumer["inputs"]).items():
                    if output_hash == input_hash:
                        edges.append({"kind": "redacted_dataflow", "from": left, "to": right,
                                      "producer_slot": output_name, "consumer_slot": input_name})
            if (producer["operation"], consumer["operation"]) in declared:
                edges.append({"kind": "declared_dependency", "from": left, "to": right})
    body = {"registry_sha256": registry_hash, "nodes": nodes, "edges": sorted(edges, key=lambda item: canonical(item))}
    return Graph(registry_hash, nodes, tuple(body["edges"]), digest(body))


def _core(graphs: list[Graph]) -> list[str]:
    """Ordered common subsequence of operation/effect identities."""
    sequences = [[(node["operation"], node["effect_class"]) for node in graph.nodes] for graph in graphs]
    first = sequences[0]
    result: list[tuple[str, str]] = []
    positions = [0] * len(sequences)
    for item in first:
        found: list[int] = []
        for sequence, position in zip(sequences, positions):
            try: found.append(sequence.index(item, position))
            except ValueError: break
        else:
            result.append(item); positions = [position + 1 for position in found]
    return [operation for operation, _ in result]


def plan_task_batch(success_graphs: Iterable[Graph], failed_graphs: Iterable[Graph], pre_state: Mapping[str, Any], *, min_successes: int = 2) -> dict[str, Any]:
    success = list(success_graphs); failed = list(failed_graphs)
    if not success:
        core: list[str] = []
        registry_hash = ""
    else:
        registry_hash = success[0].registry_sha256
        if any(graph.registry_sha256 != registry_hash for graph in success + failed):
            raise ValueError("mixed registry evidence")
        core = _core(success)
    success_counts = {operation: sum(operation in [node["operation"] for node in graph.nodes] for graph in success) for operation in core}
    failure_counts = {operation: sum(operation in [node["operation"] for node in graph.nodes] for graph in failed) for operation in core}
    # An operation equally frequent in failures is exploration, not a learned
    # constraint.  The final write is always required as terminal effect.
    required = [operation for operation in core if success_counts[operation] > failure_counts[operation]]
    terminal = next((operation for operation in reversed(required) if any(node["operation"] == operation and node["effect_class"] == "write" for node in success[-1].nodes)), None) if success else None
    optional = sorted({node["operation"] for graph in success for node in graph.nodes} - set(required))
    schema = {"policy_version": POLICY_VERSION, "registry_sha256": registry_hash, "required_operations": required,
              "optional_operations": optional, "terminal_effect": terminal,
              "typed_constraints": [{"operation": node["operation"], "required": node["public_required"], "outputs": node["output_slots"]}
                                    for node in success[0].nodes if node["operation"] in required] if success else [],
              "support": {"successes": len(success), "failures": len(failed), "success_counts": success_counts, "failure_counts": failure_counts},
              "graph_hashes": sorted(graph.sha256 for graph in success + failed)}
    candidate = {"schema": schema, "schema_id": f"schema_{digest(schema)[:16]}", "pre_state_sha256": digest(pre_state),
                 "min_successes": min_successes, "plan_version": POLICY_VERSION}
    candidate["plan_sha256"] = digest(candidate)
    return candidate


def validate_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    schema = plan.get("schema", {})
    support = schema.get("support", {}) if isinstance(schema, Mapping) else {}
    required = schema.get("required_operations", []) if isinstance(schema, Mapping) else []
    terminal = schema.get("terminal_effect") if isinstance(schema, Mapping) else None
    passed = bool(len(required) and terminal in required and int(support.get("successes", 0)) >= int(plan.get("min_successes", 2)))
    return {"passed": passed, "reason": None if passed else "insufficient_contrastive_response_attested_evidence",
            "plan_sha256": plan.get("plan_sha256"), "required_operation_count": len(required)}


def commit(pre_state: Mapping[str, Any], plan: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pure transactional commit.  Rejection is byte-identical to pre-state."""
    validation = validate_plan(plan)
    if not validation["passed"]:
        return dict(pre_state), {"state": "rejected", "winner_schema_id": None, "validation": validation,
                                 "before_state_sha256": digest(pre_state), "after_state_sha256": digest(pre_state)}
    state = json.loads(canonical(pre_state))
    schemas = state.setdefault("contrastive_v6_schemas", {})
    schema_id = str(plan["schema_id"])
    schemas.setdefault(schema_id, plan["schema"])
    marker = {"state": "committed", "winner_schema_id": schema_id, "validation": validation,
              "before_state_sha256": digest(pre_state), "after_state_sha256": digest(state), "plan_sha256": plan["plan_sha256"]}
    return state, marker


def retrieve(state: Mapping[str, Any], query_operations: Iterable[str], registry_sha256: str) -> tuple[str, dict[str, Any]]:
    query = tuple(query_operations); candidates = []
    for schema_id, schema in sorted(state.get("contrastive_v6_schemas", {}).items()):
        compatible = schema.get("registry_sha256") == registry_sha256 and schema.get("terminal_effect") in query and set(schema.get("required_operations", [])) <= set(query)
        candidates.append({"schema_id": schema_id, "compatible": compatible, "score": len(schema.get("required_operations", [])) if compatible else 0})
    selected = next((item for item in candidates if item["compatible"]), None)
    if selected is None:
        guidance = ""
    else:
        schema = state["contrastive_v6_schemas"][selected["schema_id"]]
        guidance = "\n".join(f"- Use public operation constraint: {operation}" for operation in schema["required_operations"])
    provenance = {"policy_version": POLICY_VERSION, "pre_state_sha256": digest(state), "query_sha256": digest(query),
                  "registry_sha256": registry_sha256, "candidate_ids": [item["schema_id"] for item in candidates],
                  "candidate_scores": candidates, "selected_schema_id": None if selected is None else selected["schema_id"],
                  "guidance_sha256": digest(guidance), "fallback_category": "empty" if not guidance else "learned"}
    return guidance, provenance


def reproduce_retrieval(state: Mapping[str, Any], query_operations: Iterable[str], provenance: Mapping[str, Any]) -> str:
    if digest(state) != provenance.get("pre_state_sha256") or digest(tuple(query_operations)) != provenance.get("query_sha256"):
        raise ValueError("retrieval provenance input mismatch")
    guidance, reproduced = retrieve(state, query_operations, str(provenance.get("registry_sha256")))
    if digest(guidance) != provenance.get("guidance_sha256") or reproduced.get("selected_schema_id") != provenance.get("selected_schema_id"):
        raise ValueError("retrieval provenance mismatch")
    return guidance
