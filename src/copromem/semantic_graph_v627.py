"""Scalable, byte-equivalent semantic projection for CoProMem v6.2.7.

The v6.1 implementation deliberately retains every response-attested
occurrence.  A real AppWorld journal can therefore have a large number of
distinct dataflow edges.  Its list-membership duplicate check is quadratic in
that edge count.  This module preserves the v6.1 projection byte for byte for
the same input while using a canonical membership index for that check.

It is versioned rather than changing the frozen v6.1/v6.2.2 common core.
"""
from __future__ import annotations

from typing import Any, Mapping

from .contrastive_graph_v6 import Graph, canonical, digest
from .semantic_graph_v61 import POLICY_VERSION, ROLE_VERSION, _index, classify_operation


def project_graph(graph: Graph, registry: Mapping[str, Any]) -> tuple[Graph, dict[str, Any]]:
    """Project semantic occurrences with the v6.1 output contract.

    ``canonical`` is an exact deterministic representation of these
    JSON-shaped edge dictionaries.  It is used only as an index; the emitted
    dictionaries and their ordering are unchanged.
    """
    index = _index(registry)
    roles: dict[int, str] = {}
    excluded: list[dict[str, Any]] = []
    for position, node in enumerate(graph.nodes):
        operation = str(node["operation"])
        meta = index.get(operation)
        if meta is None:
            raise ValueError("graph operation absent from frozen registry")
        role = classify_operation(meta)
        roles[position] = role
        if role != "domain_operation":
            excluded.append({"node_index": position, "operation": operation, "role": role,
                             "reason": "non_domain_provenance_only"})
    domain = {position for position, role in roles.items() if role == "domain_operation"}
    mapping: dict[int, int] = {}
    retained: list[dict[str, Any]] = []
    for new_index, position in enumerate(sorted(domain)):
        node = dict(graph.nodes[position])
        node["index"] = new_index
        node["multiplicity"] = 1
        node["evidence_node_indices"] = [position]
        node["evidence_node_sha256"] = [digest(graph.nodes[position])]
        retained.append(node)
        mapping[position] = new_index
    edges: list[dict[str, Any]] = []
    edge_index: set[str] = set()

    def append_once(edge: dict[str, Any]) -> None:
        key = canonical(edge)
        if key not in edge_index:
            edge_index.add(key)
            edges.append(edge)

    positions = sorted(domain)
    for left, right in zip(positions, positions[1:]):
        append_once({"kind": "order", "from": mapping[left], "to": mapping[right],
                     "induced_over_excluded": right - left > 1})
    for edge in graph.edges:
        if (edge["kind"] not in {"redacted_dataflow", "declared_dependency"}
                or edge["from"] not in domain or edge["to"] not in domain):
            continue
        projected = {key: value for key, value in edge.items() if key not in {"from", "to"}}
        projected.update({"from": mapping[int(edge["from"])], "to": mapping[int(edge["to"]) ]})
        append_once(projected)
    edges = sorted(edges, key=lambda item: (int(item["from"]), int(item["to"]), str(item["kind"]), digest(item)))
    body = {"registry_sha256": graph.registry_sha256, "nodes": tuple(retained), "edges": tuple(edges)}
    semantic = Graph(graph.registry_sha256, body["nodes"], body["edges"], digest(body))
    audit = {
        "policy_version": POLICY_VERSION,
        "role_version": ROLE_VERSION,
        "original_graph_sha256": graph.sha256,
        "semantic_projection_sha256": semantic.sha256,
        "excluded_nodes": excluded,
        "collapsed_repeats": [],
        "retained_domain_nodes": [
            {"operation": row["operation"], "multiplicity": row["multiplicity"],
             "evidence_node_sha256": row["evidence_node_sha256"]}
            for row in retained
        ],
        "retained_domain_dataflow_edges": edges,
        "provenance_sha256": digest({"original": graph.sha256, "semantic": semantic.sha256,
                                      "excluded": excluded, "collapsed": [], "edges": edges}),
    }
    return semantic, audit


def build_semantic_graph(records: list[Mapping[str, Any]], registry: Mapping[str, Any]) -> tuple[Graph, dict[str, Any]]:
    from .contrastive_graph_v6 import build_graph
    return project_graph(build_graph(records, registry), registry)
