from __future__ import annotations

import copy
import json
import os
import subprocess
import sys

import pytest

from copromem.benchmarks.appworld.adapter import CoProMemAppWorldAdapter
from copromem.experiments.reme_copromem.task_boundary import (
    POLICY_VERSION, canonical_digest, commit_task_boundary_plan,
    OBSERVABLE_PATH_POLICY_VERSION, OBSERVABLE_SUBGRAPH_POLICY_VERSION, fully_observed, plan_task_boundary_update,
    TOOL_SCHEMA_PATH_POLICY_VERSION, EXECUTION_EVIDENCE_POLICY_VERSION, project_observable_registry_path, project_observable_supported_subgraph,
    project_observable_tool_schema_path, validate_task_boundary_plan,
)
from copromem.experiments.reme_copromem.public_path_registry import canonical_digest as registry_digest
from copromem.experiments.reme_copromem.public_tool_schema_registry import canonical_digest as tool_registry_digest


def trial(seed: int, index: int, *, observed: bool = True, score: float = 1.0) -> dict:
    return {"task_id": "fixture", "seed": seed, "trajectory_index": index, "intent": "redacted",
            "score": score, "no_memory_score": 0.0, "cost_usd": 0.01 + index, "actions": 1,
            "actions_text": ["redacted"], "task_state": {"fixture": True},
            "events": [{"operation": "apis.notes.search", "input_slots": ["query"],
                        "output_slots": ["results"], "check": "observed", "observed": observed}]}


def test_rejected_plan_never_commits_or_changes_retrieval_bank():
    pre = CoProMemAppWorldAdapter(api_key="").export_state()
    plan = plan_task_boundary_update(pre, [], [trial(11, 1, observed=False), trial(12, 2, observed=True)])
    validation = validate_task_boundary_plan(plan)
    post, committed = commit_task_boundary_plan(pre, plan)
    assert not validation["passed"] and committed["winner_episode_id"] is None
    assert post == pre and canonical_digest(post) == canonical_digest(pre)
    adapter = CoProMemAppWorldAdapter(api_key=""); adapter.clone_from_state(post)
    assert adapter.module.learning.retrieve("appworld", ()).text == ""


def test_valid_plan_commits_one_deterministic_winner_and_reconstructs_exactly():
    pre = CoProMemAppWorldAdapter(api_key="").export_state()
    descriptor = [{"operation": "apis.notes.search", "input_slots": ["query"], "output_slots": ["results"]}]
    plan = plan_task_boundary_update(pre, descriptor, [trial(12, 2), trial(11, 1)])
    post, validation = commit_task_boundary_plan(pre, plan)
    assert validation["passed"] and validation["winner_episode_id"] == "fixture::seed=11::trajectory=1"
    replay, replay_validation = commit_task_boundary_plan(copy.deepcopy(pre), json.loads(json.dumps(plan)))
    assert replay_validation == validation and canonical_digest(replay) == canonical_digest(post)
    assert canonical_digest(pre) == canonical_digest(CoProMemAppWorldAdapter(api_key="").export_state())


def test_strict_descriptor_mismatch_rejects_before_promotion():
    pre = CoProMemAppWorldAdapter(api_key="").export_state()
    descriptor = [{"operation": "apis.notes.create", "input_slots": ["text"], "output_slots": ["id"]}]
    plan = plan_task_boundary_update(pre, descriptor, [trial(11, 1)])
    post, validation = commit_task_boundary_plan(pre, plan)
    assert not validation["passed"]
    assert not validation["descriptor_exact_match"]
    assert validation["winner_episode_id"] is None
    assert post == pre


def test_v51_projects_observed_descriptor_steps_and_ignores_repeated_public_docs():
    descriptor = [{"operation": "apis.notes.search", "input_slots": ["query"], "output_slots": ["results"]}]
    raw = [
        {"operation": "apis.api_docs.show_api_doc", "input_slots": ["api_name"], "output_slots": ["observation"], "check": "public", "observed": True},
        {"operation": "apis.notes.search", "input_slots": ["query"], "output_slots": ["results"], "check": "direct", "observed": True},
        {"operation": "apis.api_docs.show_api_doc", "input_slots": ["api_name"], "output_slots": ["observation"], "check": "public", "observed": True},
    ]
    projected, audit = project_observable_supported_subgraph(
        tuple(__import__("copromem.learning", fromlist=["ActionObservation"]).ActionObservation(**x) for x in descriptor),
        tuple(__import__("copromem.learning", fromlist=["ActionObservation"]).ActionObservation(**x) for x in raw))
    assert audit["valid"] and len(projected) == 1 and projected[0].operation == "apis.notes.search"
    row = trial(11, 1); row["events"] = raw
    pre = CoProMemAppWorldAdapter(api_key="").export_state()
    plan = plan_task_boundary_update(pre, descriptor, [row], OBSERVABLE_SUBGRAPH_POLICY_VERSION)
    post, validation = commit_task_boundary_plan(pre, plan)
    assert validation["passed"] and validation["descriptor_exact_match"] and post != pre


def test_v51_quarantines_helper_dataflow_and_policy_mismatch_fails():
    descriptor = [{"operation": "apis.notes.search", "input_slots": ["token"], "output_slots": ["results"]}]
    row = trial(11, 1); row["events"] = [
        {"operation": "apis.supervisor.show_account_passwords", "input_slots": [], "output_slots": ["token"], "check": "public", "observed": True},
        {"operation": "apis.notes.search", "input_slots": ["token"], "output_slots": ["results"], "check": "direct", "observed": True},
    ]
    pre = CoProMemAppWorldAdapter(api_key="").export_state()
    plan = plan_task_boundary_update(pre, descriptor, [row], OBSERVABLE_SUBGRAPH_POLICY_VERSION)
    post, validation = commit_task_boundary_plan(pre, plan)
    assert not validation["passed"] and not validation["projection_valid"] and post == pre
    plan["policy_version"] = "unknown"
    with pytest.raises(ValueError): validate_task_boundary_plan(plan)


def test_trial_and_mapping_order_do_not_change_content_addressed_plan():
    pre = CoProMemAppWorldAdapter(api_key="").export_state(); rows = [trial(12, 2), trial(11, 1)]
    left = plan_task_boundary_update(pre, [], rows)
    right = plan_task_boundary_update(dict(reversed(list(pre.items()))), [], list(reversed(rows)))
    assert left["plan_sha256"] == right["plan_sha256"]


@pytest.mark.parametrize("field", ["pre_state", "descriptor", "trials", "policy_version"])
def test_tampering_fails_closed(field):
    pre = CoProMemAppWorldAdapter(api_key="").export_state(); plan = plan_task_boundary_update(pre, [], [trial(11, 1)])
    broken = copy.deepcopy(plan)
    if field == "pre_state": broken[field]["version"] = 999
    elif field == "descriptor": broken[field].append({"operation": "x"})
    elif field == "trials": broken[field][0]["score"] = 0.5
    else: broken[field] = "wrong"
    with pytest.raises(ValueError): validate_task_boundary_plan(broken)


def test_sanitized_005_and_006_nested_shapes_reject_without_payloads():
    pre = CoProMemAppWorldAdapter(api_key="").export_state()
    for label in ("v5-005", "v5-006"):
        item = trial(11, 1, observed=True)
        item["events"].append({"operation": f"helper.{label}", "input_slots": ["results"], "output_slots": [], "observed": False})
        plan = plan_task_boundary_update(pre, [], [item])
        assert not validate_task_boundary_plan(plan)["passed"]


def test_observed_response_check_is_positive_evidence_not_a_rejection():
    from copromem.learning import ActionObservation
    assert fully_observed((ActionObservation("apis.x", ("input",), ("output",), check="API response observed"),))


def test_deterministic_ids_match_in_fresh_python_process(tmp_path):
    pre = CoProMemAppWorldAdapter(api_key="").export_state(); plan = plan_task_boundary_update(pre, [], [trial(11, 1)])
    fixture = tmp_path / "fixture.json"; fixture.write_text(json.dumps({"pre": pre, "trials": [trial(11, 1)]}), encoding="utf-8")
    code = ("import json,sys; from copromem.experiments.reme_copromem.task_boundary import plan_task_boundary_update; "
            "x=json.load(open(sys.argv[1])); print(plan_task_boundary_update(x['pre'],[],x['trials'])['plan_sha256'])")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    output = subprocess.check_output([sys.executable, "-c", code, str(fixture)], text=True, env=env).strip()
    assert output == plan["plan_sha256"]


def _v52_registry():
    registry = {"registry_version": "appworld-public-alternative-path-registry-v5_2", "source_metadata": [],
                "operations": [
                    {"operation": "apis.notes.search", "app": "notes", "http_method": "GET", "access_mode": "read",
                     "path_template": "/search", "operation_id": "notes__search", "input_slots": [], "optional_input_slots": [], "output_slots": ["result_id"]},
                    {"operation": "apis.notes.archive", "app": "notes", "http_method": "POST", "access_mode": "write",
                     "path_template": "/{result_id}/archive", "operation_id": "notes__archive", "input_slots": ["result_id"], "optional_input_slots": [], "output_slots": ["message"]},
                ], "alternative_groups": [{"group_id": "input:apis.notes.archive:result_id", "consumer_operation": "apis.notes.archive",
                                              "input_slot": "result_id", "producer_operations": ["apis.notes.search"],
                                              "semantic_status": "schema_compatible_not_semantically_equivalent"}],
                "dependency_edges": [{"from_operation": "apis.notes.search", "to_operation": "apis.notes.archive", "via_slot": "result_id", "kind": "public_schema_flow"}],
                "normalization": {"aliases": []}, "path_rule": {"ordered": True}}
    registry["registry_sha256"] = registry_digest(registry)
    return registry


def test_v52_registry_path_is_value_free_transactional_and_reproducible():
    registry = _v52_registry()
    descriptor = [{"operation": "apis.notes.search", "input_slots": [], "output_slots": ["result_id"]},
                  {"operation": "apis.notes.archive", "input_slots": ["result_id"], "output_slots": ["message"]}]
    raw = [
        {"operation": "apis.api_docs.show_api_doc", "input_slots": [], "output_slots": ["observation"], "check": "public", "observed": True},
        {"operation": "apis.notes.search", "input_slots": [], "output_slots": ["result_id"], "parameters": {"must_not": "persist"}, "check": "direct", "observed": True},
        {"operation": "apis.notes.archive", "input_slots": ["result_id"], "output_slots": ["message"], "parameters": {"must_not": "persist"}, "check": "direct", "observed": True},
    ]
    projected, audit = project_observable_registry_path(registry,
        tuple(__import__("copromem.learning", fromlist=["ActionObservation"]).ActionObservation(**x) for x in descriptor),
        tuple(__import__("copromem.learning", fromlist=["ActionObservation"]).ActionObservation(**x) for x in raw))
    assert audit["valid"] and len(projected) == 2 and all(not item.parameters for item in projected)
    item = trial(11, 1); item["events"] = raw
    pre = CoProMemAppWorldAdapter(api_key="").export_state()
    plan = plan_task_boundary_update(pre, descriptor, [item], OBSERVABLE_PATH_POLICY_VERSION, registry)
    post, validation = commit_task_boundary_plan(pre, plan)
    assert validation["passed"] and post != pre
    replay, second = commit_task_boundary_plan(pre, json.loads(json.dumps(plan)))
    assert second == validation and canonical_digest(replay) == canonical_digest(post)


def test_v52_registry_hash_and_incomplete_path_fail_closed():
    registry = _v52_registry()
    descriptor = [{"operation": "apis.notes.search", "input_slots": [], "output_slots": ["result_id"]},
                  {"operation": "apis.notes.archive", "input_slots": ["result_id"], "output_slots": ["message"]}]
    item = trial(11, 1); item["events"] = descriptor[:1]
    pre = CoProMemAppWorldAdapter(api_key="").export_state()
    plan = plan_task_boundary_update(pre, descriptor, [item], OBSERVABLE_PATH_POLICY_VERSION, registry)
    post, result = commit_task_boundary_plan(pre, plan)
    assert not result["passed"] and result["rejection_reason"] == "v5_2_public_path_incomplete" and post == pre
    plan["public_registry"]["operations"][0]["operation"] = "apis.tampered"
    with pytest.raises(ValueError, match="digest"):
        validate_task_boundary_plan(plan)


def _v53_registry():
    """Minimal public callable metadata; values are deliberately absent."""
    registry = {
        "registry_version": "appworld-public-tool-schema-registry-v5_3",
        "source_metadata": {"openapi": [], "function_calling": []},
        "operations": [
            {"operation": "apis.notes.show_items", "function_name": "notes__show_items", "app": "notes",
             "http_method": "GET", "access_mode": "read", "path_template": "/items",
             "parameters": {"access_token": {"type": "string", "kind": "runtime_context"},
                            "user_email": {"type": "string", "kind": "public_optional"}},
             "required_parameters": [], "optional_parameters": ["user_email"],
             "context_parameters": ["access_token"], "output_slots": ["item_id"],
             "interface_differences": {"callable_only": ["user_email"], "openapi_only": []}},
            {"operation": "apis.notes.archive_item", "function_name": "notes__archive_item", "app": "notes",
             "http_method": "POST", "access_mode": "write", "path_template": "/items/{item_id}",
             "parameters": {"access_token": {"type": "string", "kind": "runtime_context"},
                            "item_id": {"type": "string", "kind": "public_required"}},
             "required_parameters": ["item_id"], "optional_parameters": [],
             "context_parameters": ["access_token"], "output_slots": ["message"],
             "interface_differences": {"callable_only": [], "openapi_only": []}},
        ],
        "alternative_groups": [{"group_id": "input:apis.notes.archive_item:item_id",
                                 "consumer_operation": "apis.notes.archive_item", "input_slot": "item_id",
                                 "producer_operations": ["apis.notes.show_items"],
                                 "semantic_status": "schema_compatible_not_semantically_equivalent"}],
        "dependency_edges": [{"from_operation": "apis.notes.show_items", "to_operation": "apis.notes.archive_item",
                              "via_slot": "item_id", "kind": "public_callable_schema_flow"}],
        "normalization": {"operation_aliases": {"notes__show_items": "apis.notes.show_items",
                                                   "notes__archive_item": "apis.notes.archive_item"},
                          "runtime_context_fields": ["access_token"], "local_binding_pattern": "^var_[0-9]+$",
                          "values": "never retained in operation_signature or learned procedure"},
        "path_rule": {"ordered": True, "direct_observation_required": True,
                      "required_fields": "all callable public_required fields",
                      "additional_fields": "only callable public_optional or runtime_context fields",
                      "unknown_fields": "fail_closed", "concrete_values": "hash-only invocation_evidence"},
    }
    registry["registry_sha256"] = tool_registry_digest(registry)
    return registry


def test_v53_tool_schema_path_accepts_public_optional_and_context_without_values():
    registry = _v53_registry()
    descriptor = [
        {"operation": "apis.notes.show_items", "input_slots": [], "output_slots": ["item_id"]},
        {"operation": "apis.notes.archive_item", "input_slots": ["item_id"], "output_slots": ["message"]},
    ]
    raw = [
        {"operation": "notes__show_items", "input_slots": ["access_token", "user_email", "var_1"],
         "output_slots": ["observation"], "parameters": {"user_email": "must-not-enter-memory"},
         "check": "direct", "observed": True},
        {"operation": "notes__archive_item", "input_slots": ["access_token", "item_id", "var_1"],
         "output_slots": ["observation"], "parameters": {"item_id": "must-not-enter-memory"},
         "check": "direct", "observed": True},
    ]
    projected, audit = project_observable_tool_schema_path(
        registry, tuple(__import__("copromem.learning", fromlist=["ActionObservation"]).ActionObservation(**x) for x in descriptor),
        tuple(__import__("copromem.learning", fromlist=["ActionObservation"]).ActionObservation(**x) for x in raw),
        raw_evidence_digest="a" * 64)
    assert audit["valid"] and len(projected) == 2
    assert "must-not-enter-memory" not in json.dumps(audit) and all(not item.parameters for item in projected)
    item = trial(11, 1); item["events"] = raw; item["intent"] = "must-not-enter-memory"
    pre = CoProMemAppWorldAdapter(api_key="").export_state()
    plan = plan_task_boundary_update(pre, descriptor, [item], TOOL_SCHEMA_PATH_POLICY_VERSION, registry)
    assert "must-not-enter-memory" not in json.dumps(plan)
    post, validation = commit_task_boundary_plan(pre, plan)
    assert validation["passed"] and post != pre
    replay, again = commit_task_boundary_plan(pre, json.loads(json.dumps(plan)))
    assert again == validation and canonical_digest(replay) == canonical_digest(post)


def test_v53_tool_schema_unknown_field_rejects_without_mutating_state():
    registry = _v53_registry()
    descriptor = [{"operation": "apis.notes.show_items", "input_slots": [], "output_slots": ["item_id"]}]
    item = trial(11, 1); item["events"] = [{"operation": "notes__show_items", "input_slots": ["undeclared"],
        "output_slots": ["observation"], "check": "direct", "observed": True}]
    pre = CoProMemAppWorldAdapter(api_key="").export_state()
    plan = plan_task_boundary_update(pre, descriptor, [item], TOOL_SCHEMA_PATH_POLICY_VERSION, registry)
    post, validation = commit_task_boundary_plan(pre, plan)
    assert not validation["passed"] and post == pre
    assert plan["projection_audit"][0]["audit"]["records"][0]["category"] == "nonmatching_or_undeclared_call"


def test_execution_evidence_policy_reuses_v53_predicate_without_source_parsing():
    registry = _v53_registry()
    descriptor = [
        {"operation": "apis.notes.show_items", "input_slots": [], "output_slots": ["item_id"]},
        {"operation": "apis.notes.archive_item", "input_slots": ["item_id"], "output_slots": ["message"]},
    ]
    # These are dispatcher-derived public events.  No action/program text is
    # supplied to the policy, so nested execution cannot be inferred from AST.
    item = trial(11, 1)
    item["intent"] = "not retained"
    item["actions_text"] = []
    item["task_state"] = {"execution_evidence_audit": {"valid": True, "records_sha256": "a" * 64}}
    item["events"] = [
        {"operation": "apis.notes.show_items", "input_slots": [], "output_slots": ["item_id"],
         "check": "native_public_response_attested", "observed": True},
        {"operation": "apis.notes.archive_item", "input_slots": ["item_id"], "output_slots": ["message"],
         "check": "native_public_response_attested", "observed": True},
    ]
    pre = CoProMemAppWorldAdapter(api_key="").export_state()
    plan = plan_task_boundary_update(pre, descriptor, [item], EXECUTION_EVIDENCE_POLICY_VERSION, registry)
    post, validation = commit_task_boundary_plan(pre, plan)
    assert validation["passed"] and post != pre
    assert "not retained" not in json.dumps(plan)


def test_execution_evidence_policy_rejects_invalid_dispatch_audit_without_mutation():
    registry = _v53_registry()
    descriptor = [{"operation": "apis.notes.show_items", "input_slots": [], "output_slots": ["item_id"]}]
    item = trial(11, 1)
    item["task_state"] = {"execution_evidence_audit": {"valid": False, "records_sha256": "b" * 64}}
    pre = CoProMemAppWorldAdapter(api_key="").export_state()
    plan = plan_task_boundary_update(pre, descriptor, [item], EXECUTION_EVIDENCE_POLICY_VERSION, registry)
    post, validation = commit_task_boundary_plan(pre, plan)
    assert not validation["passed"] and post == pre
    assert plan["projection_audit"][0]["audit"]["first_rejection"]["reason"] == "execution_evidence_invalid"
