from __future__ import annotations

import copy

import pytest

from copromem.contrastive_graph_v6 import build_graph, commit, digest, plan_task_batch, reproduce_retrieval, retrieve


def _registry():
    rows = []
    for op, mode in (("apis.demo.discover", "read"), ("apis.demo.lookup", "read"), ("apis.demo.apply", "write"), ("apis.demo.noise", "read")):
        rows.append({"operation": op, "app": "demo", "function_name": op.split(".")[-1], "access_mode": mode,
                     "required_parameters": ["item"], "output_slots": ["item"], "parameters": {"item": {"type": "string"}}})
    return {"registry_sha256": "registry", "operations": rows, "dependency_edges": [{"from_operation": "apis.demo.discover", "to_operation": "apis.demo.apply"}]}


def _record(op, index, *, value="x", success=True):
    return {"monotonic_index": index, "schema_accepted": True, "response_success": success,
            "operation_signature": {"operation": op, "application": "demo", "callable_name": op.split(".")[-1], "public_required": ["item"], "output_slots": ["item"]},
            "invocation_value_hashes": {"item": digest(value)}, "response_output_value_hashes": {"item": digest(value)}}


def _promoted_state():
    registry = _registry()
    first = build_graph([_record("apis.demo.discover", 0), _record("apis.demo.apply", 1)], registry)
    second = build_graph([_record("apis.demo.lookup", 0), _record("apis.demo.apply", 1)], registry)
    failed = build_graph([_record("apis.demo.noise", 0), _record("apis.demo.apply", 1)], registry)
    plan = plan_task_batch([first, second], [failed], {}, min_successes=2)
    state, marker = commit({}, plan)
    return registry, plan, state, marker


def test_optional_discovery_paths_promote_common_response_attested_terminal_effect():
    _, plan, state, marker = _promoted_state()
    assert marker["state"] == "committed"
    schema = state["contrastive_v6_schemas"][marker["winner_schema_id"]]
    assert schema["required_operations"] == ["apis.demo.apply"]
    assert "apis.demo.discover" in schema["optional_operations"] and "apis.demo.lookup" in schema["optional_operations"]


def test_single_success_quarantines_and_rejection_is_byte_identical():
    registry = _registry(); graph = build_graph([_record("apis.demo.discover", 0), _record("apis.demo.apply", 1)], registry)
    before = {"existing": 1}; state, marker = commit(before, plan_task_batch([graph], [], before))
    assert marker["state"] == "rejected" and state == before and digest(state) == digest(before)


def test_failed_negative_evidence_excludes_equal_support_exploration():
    registry = _registry()
    good = build_graph([_record("apis.demo.noise", 0), _record("apis.demo.apply", 1)], registry)
    plan = plan_task_batch([good, good], [good, good], {})
    assert "apis.demo.noise" not in plan["schema"]["required_operations"]


def test_retrieval_is_reproducible_and_tamper_fails_closed():
    registry, _, state, marker = _promoted_state()
    guidance, provenance = retrieve(state, ["apis.demo.apply"], registry["registry_sha256"])
    assert guidance and reproduce_retrieval(state, ["apis.demo.apply"], provenance) == guidance
    bad = copy.deepcopy(provenance); bad["guidance_sha256"] = "0" * 64
    with pytest.raises(ValueError): reproduce_retrieval(state, ["apis.demo.apply"], bad)


def test_invalid_evidence_and_value_leakage_are_rejected():
    registry = _registry(); row = _record("apis.demo.apply", 0); row["schema_accepted"] = False
    with pytest.raises(ValueError): build_graph([row], registry)
    _, _, state, marker = _promoted_state()
    assert "x" not in repr(state) and marker["state"] == "committed"


def test_duplicate_commit_and_cross_process_canonical_hash_are_deterministic():
    _, plan, state, marker = _promoted_state()
    again, marker_again = commit(state, plan)
    assert again == state and marker_again["winner_schema_id"] == marker["winner_schema_id"]


def test_v6_runner_does_not_route_to_the_v53_exact_path_lifecycle():
    import inspect
    from copromem.experiments.reme_copromem import contrastive_v6_runner
    source = inspect.getsource(contrastive_v6_runner)
    assert "complete_copro_task" not in source and "validate_tool_schema_path_v5_3" not in source
