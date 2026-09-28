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
    OBSERVABLE_SUBGRAPH_POLICY_VERSION, fully_observed, plan_task_boundary_update,
    project_observable_supported_subgraph, validate_task_boundary_plan,
)


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
