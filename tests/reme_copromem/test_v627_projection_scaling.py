from copromem.contrastive_graph_v6 import Graph, digest
from copromem.semantic_graph_v61 import project_graph as v61_project
from copromem.semantic_graph_v627 import project_graph as v627_project


def _registry():
    return {"registry_sha256": "registry", "dependency_edges": [], "operations": [
        {"operation": "apis.demo.read", "app": "demo", "function_name": "demo__read",
         "access_mode": "read", "parameters": {}, "required_parameters": [], "output_slots": []},
    ]}


def _graph(count: int) -> Graph:
    nodes = tuple({"operation": "apis.demo.read", "application": "demo", "callable_name": "demo__read",
                   "effect_class": "read", "inputs": [], "outputs": [], "public_required": [],
                   "output_slots": [], "index": index, "response_class": "success"}
                  for index in range(count))
    edges = tuple({"kind": "redacted_dataflow", "from": left, "to": right,
                   "producer_slot": "id", "consumer_slot": "id"}
                  for left in range(count) for right in range(left + 1, count))
    return Graph("registry", nodes, edges, digest({"registry_sha256": "registry", "nodes": nodes, "edges": edges}))


def test_v627_projection_is_exactly_v61_equivalent_on_normal_graph():
    graph = _graph(12)
    legacy, legacy_audit = v61_project(graph, _registry())
    scalable, scalable_audit = v627_project(graph, _registry())
    assert scalable == legacy
    assert scalable_audit == legacy_audit


def test_v627_projection_handles_dense_distinct_dataflow_without_occurrence_loss():
    graph = _graph(250)  # 31,125 response-attested dataflow edges.
    projected, audit = v627_project(graph, _registry())
    assert len(projected.nodes) == 250
    assert len(projected.edges) == 31_374  # 31,125 dataflow + 249 ordered edges.
    assert len(audit["retained_domain_dataflow_edges"]) == len(projected.edges)
