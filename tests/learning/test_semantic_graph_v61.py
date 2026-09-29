from copromem.contrastive_graph_v6 import Graph, digest
from copromem.semantic_graph_v61 import classify_operation, project_graph, semantic_plan, validate_semantic_plan


def _registry():
    rows=[]
    for op, app, name, mode in [
        ("apis.api_docs.show_api_doc","api_docs","api_docs__show_api_doc","read"),
        ("apis.supervisor.complete_task","supervisor","supervisor__complete_task","write"),
        ("apis.demo.login","demo","demo__login","write"),
        ("apis.demo.read","demo","demo__read","read"),
        ("apis.demo.write","demo","demo__write","write")]:
        rows.append({"operation":op,"app":app,"function_name":name,"access_mode":mode,"parameters":{},"required_parameters":[],"output_slots":[]})
    return {"registry_sha256":"r","operations":rows,"dependency_edges":[]}


def _graph():
    nodes=[]
    for index,op in enumerate(["apis.api_docs.show_api_doc","apis.demo.login","apis.demo.read","apis.demo.read","apis.demo.write","apis.supervisor.complete_task"]):
        nodes.append({"operation":op,"application":"demo","callable_name":op,"effect_class":"write" if op.endswith("write") else "read","inputs":[],"outputs":[],"public_required":[],"output_slots":[],"index":index,"response_class":"success"})
    body={"registry_sha256":"r","nodes":tuple(nodes),"edges":tuple()}
    return Graph("r",tuple(nodes),tuple(),digest(body))


def test_registry_roles_and_projection_exclude_scaffolding_and_collapse_repeated_reads():
    registry=_registry(); graph,audit=project_graph(_graph(),registry)
    assert classify_operation(registry["operations"][0]) == "infrastructure_discovery"
    assert classify_operation(registry["operations"][1]) == "supervisor_control"
    assert classify_operation(registry["operations"][2]) == "authentication_runtime_context"
    assert [node["operation"] for node in graph.nodes] == ["apis.demo.read","apis.demo.write"]
    assert graph.nodes[0]["multiplicity"] == 2
    assert {row["role"] for row in audit["excluded_nodes"]} == {"infrastructure_discovery","supervisor_control","authentication_runtime_context"}


def test_semantic_plan_rejects_infrastructure_terminal_and_is_transactional():
    registry=_registry(); graph,audit=project_graph(_graph(),registry)
    plan=semantic_plan([graph,graph],[],{},[audit,audit]); validation=validate_semantic_plan(plan,registry)
    assert validation["passed"] and plan["schema"]["terminal_effect"] == "apis.demo.write"
    bad={**plan,"schema":{**plan["schema"],"terminal_effect":"apis.supervisor.complete_task"}}
    assert validate_semantic_plan(bad,registry)["reason"] == "unsupported_terminal_effect"


def test_infrastructure_only_and_failed_paths_cannot_promote_semantic_procedure():
    registry=_registry(); nodes=[dict(node) for node in _graph().nodes[:2]]
    body={"registry_sha256":"r","nodes":tuple(nodes),"edges":tuple()}; graph=Graph("r",tuple(nodes),tuple(),digest(body))
    projected,audit=project_graph(graph,registry)
    assert not projected.nodes and len(audit["excluded_nodes"]) == 2
    plan=semantic_plan([projected,projected],[],{},[audit,audit])
    assert validate_semantic_plan(plan,registry)["reason"] == "no_domain_operation"


def test_distinct_response_attested_domain_dataflow_prevents_repeat_collapse():
    registry=_registry(); nodes=[dict(node) for node in _graph().nodes[2:5]]
    nodes[0]["index"]=0; nodes[1]["index"]=1; nodes[2]["index"]=2
    edge={"kind":"redacted_dataflow","from":0,"to":2,"producer_slot":"id","consumer_slot":"id"}
    body={"registry_sha256":"r","nodes":tuple(nodes),"edges":(edge,)}; graph=Graph("r",tuple(nodes),(edge,),digest(body))
    projected,_=project_graph(graph,registry)
    assert len(projected.nodes) == 3  # protected endpoints retain distinct provenance.
