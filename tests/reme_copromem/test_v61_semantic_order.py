from __future__ import annotations

import copy

import pytest

from copromem.contrastive_graph_v6 import Graph, digest
from copromem.semantic_graph_v61 import project_graph


REGISTRY = {"registry_sha256":"r", "operations":[
    {"operation":"apis.demo.read","app":"demo","function_name":"read","access_mode":"read"},
    {"operation":"apis.demo.write","app":"demo","function_name":"write","access_mode":"write"},
    {"operation":"apis.api_docs.show","app":"api_docs","function_name":"show","access_mode":"read"},
]}


def _node(operation: str, index: int) -> dict:
    return {"operation":operation,"application":"demo","callable_name":operation,"effect_class":"write" if operation.endswith("write") else "read",
            "inputs":[],"outputs":[],"public_required":[],"output_slots":[],"index":index,"response_class":"success"}


def _graph(operations: list[str]) -> Graph:
    nodes=tuple(_node(op, i) for i,op in enumerate(operations)); edges=tuple({"kind":"order","from":i,"to":i+1} for i in range(len(nodes)-1))
    return Graph("r",nodes,edges,digest({"registry_sha256":"r","nodes":nodes,"edges":edges}))


def test_read_write_read_retains_three_ordered_occurrences():
    semantic,audit=project_graph(_graph(["apis.demo.read","apis.demo.write","apis.demo.read"]), REGISTRY)
    assert [node["operation"] for node in semantic.nodes] == ["apis.demo.read","apis.demo.write","apis.demo.read"]
    assert [node["evidence_node_indices"] for node in semantic.nodes] == [[0],[1],[2]]
    assert [(edge["from"],edge["to"]) for edge in semantic.edges if edge["kind"]=="order"] == [(0,1),(1,2)]
    assert audit["collapsed_repeats"] == []


def test_excluded_node_induces_domain_order_and_projection_is_deterministic():
    graph=_graph(["apis.demo.read","apis.api_docs.show","apis.demo.write"])
    first,audit=project_graph(graph,REGISTRY); second,_=project_graph(copy.deepcopy(graph),REGISTRY)
    assert first.sha256 == second.sha256
    assert [(edge["from"],edge["to"],edge.get("induced_over_excluded")) for edge in first.edges if edge["kind"]=="order"] == [(0,1,True)]
    assert audit["excluded_nodes"][0]["operation"] == "apis.api_docs.show"


def test_tampered_occurrence_order_changes_projection_identity():
    original,_=project_graph(_graph(["apis.demo.read","apis.demo.write","apis.demo.read"]),REGISTRY)
    tampered,_=project_graph(_graph(["apis.demo.read","apis.demo.read","apis.demo.write"]),REGISTRY)
    assert original.sha256 != tampered.sha256
