import runpy
from pathlib import Path

import pytest

from copromem.checkpoints import IntegrityError, RunStore, canonical, digest
from copromem.stateful_source import context_for_step

AUDIT = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/audit_stateful_source.py")
)


def test_expression_only_json_is_not_a_successful_action():
    result = AUDIT["syntax_diagnostic"]('{"code": "apis.example.change()"}')
    assert result["syntax_valid"]
    assert result["call_expressions"] == 0
    assert result["api_paths"] == []


def test_code_syntax_diagnostic_does_not_claim_calls_executed():
    result = AUDIT["syntax_diagnostic"]("if False:\n    apis.example.change()")
    assert result["api_paths"] == ["apis.example.change"]
    assert "success" not in result


def test_syntax_error_is_distinct_from_no_call_expression():
    result = AUDIT["syntax_diagnostic"]('x = "unterminated')
    assert result["syntax_valid"] is False
    assert result["call_expressions"] is None


def corpus(tmp_path, *, expanded=False):
    store = RunStore(tmp_path)
    protocol = {
        "cycle_id": "fixture",
        "context_chars": 1000,
        "excluded_scenarios": ["07b42fd"],
        "replicates": 1,
    }
    if expanded:
        protocol.update(
            {
                "context_version": "public-history-budget-v2",
                "max_steps": 50,
                "history_output_chars": 500,
                "history_program_chars": 300,
            }
        )
    store.write(
        "protocol",
        "preregistration",
        protocol,
    )
    store.write("dataset", "selection", {"build": ["1111111_1"]})
    before = {
        "task_id": "1111111_1",
        "public_instruction": "public fixture",
        "results": [],
        "completion_flag": False,
        "request_id": "prefix0",
        "harness_only_state": {"secret": "PRIVATE"},
    }
    after = {
        **before,
        "request_id": "prefix1",
        "results": [{"program": "print(1)", "output": "1"}],
    }
    context = context_for_step(before, protocol, 0)
    checkpoint = {"task_id": "1111111_1", "public_context": context}
    checkpoint_id = digest(checkpoint)
    store.write("public_handoffs", checkpoint_id, checkpoint)
    plan = {"intent": "print one"}
    calls = []
    for index, (user, text) in enumerate(
        [
            (canonical(context), canonical(plan)),
            (
                canonical({"public_context": context, "planner_handoff": plan}),
                '{"code":"print(1)"}',
            ),
        ]
    ):
        request = {"user": user}
        response = {
            "text": text,
            "usage": {"usd": 0.01},
            "metadata": {"finish_reason": "stop"},
        }
        call_id = digest(request)
        store.write(
            "calls",
            call_id,
            {
                "request": request,
                "response": response,
                "response_sha256": digest(response),
            },
        )
        store.write("reservations", str(index), {"reserved_usd": 0.02})
        store.write("settlements", str(index), {"actual_usd": 0.01})
        calls.append(call_id)
    store.write("stream_frames", "fixture-000", before)
    store.write("stream_frames", "fixture-001", after)
    step = {
        "episode_id": "fixture",
        "step": 0,
        "planner_generation_id": calls[0],
        "executor_generation_id": calls[1],
        "public_checkpoint_id": checkpoint_id,
        "environment_prefix_id": "prefix0",
        "plan": plan,
        "code": "print(1)",
        "plan_parse_fallback": False,
        "code_parse_fallback": False,
        "public_output": "1",
        "local_action_error": False,
    }
    store.write("source_steps", "fixture-00", step)
    store.write(
        "source_episodes",
        "fixture",
        {
            "task_id": "1111111_1",
            "scenario_id": "1111111",
            "steps": 1,
            "native_evaluation": {"native_success": False},
            "replay_validation": {"verified": True},
            "eligible_for_induction": True,
        },
    )
    return store


def test_offline_audit_reconciles_public_frames_and_costs(tmp_path):
    corpus(tmp_path)
    result = AUDIT["audit"](tmp_path)
    assert result["complete_registered_sample"]
    assert result["completed_calls"] == 2
    assert result["charged_or_reserved_usd"] == 0.02
    assert result["primary_metric"] == 0
    assert result["model_calls_for_audit"] == 0


def test_expanded_context_audit_binds_budget_to_both_role_requests(tmp_path):
    store = corpus(tmp_path, expanded=True)
    assert AUDIT["audit"](tmp_path)["completed_calls"] == 2
    protocol = store.read("protocol", "preregistration")
    protocol["max_steps"] = 49
    # Deliberate corruption of an authored temporary fixture, never a run archive.
    (tmp_path / "protocol/preregistration.json").write_text(canonical(protocol))
    with pytest.raises(IntegrityError, match="environment prefix"):
        AUDIT["audit"](tmp_path)


@pytest.mark.parametrize(
    "kind,key,field,replacement",
    [
        ("source_steps", "fixture-00", "environment_prefix_id", "wrong-prefix"),
        ("stream_frames", "fixture-000", "public_instruction", "changed instruction"),
        ("source_steps", "fixture-00", "code", "print(2)"),
        ("settlements", "0", "actual_usd", 0.02),
    ],
)
def test_offline_audit_rejects_changed_evidence(
    tmp_path, kind, key, field, replacement
):
    store = corpus(tmp_path)
    value = store.read(kind, key)
    value[field] = replacement
    # Intentionally simulate corruption of an authored temporary test fixture.
    (tmp_path / kind / f"{key}.json").write_text(canonical(value), encoding="utf-8")
    with pytest.raises(IntegrityError):
        AUDIT["audit"](tmp_path)
