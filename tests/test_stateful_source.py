import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from copromem.checkpoints import RecordedCallError, RunStore, canonical
from copromem.stateful_source import (
    context_for_step,
    parse_code,
    parse_executor_response,
    parse_plan,
    prompt_context,
    role_prompts,
    run_episode,
    select_groups,
    transport_price_caps,
    validate_settings,
)


def settings():
    return json.loads(
        (
            Path(__file__).parents[1] / "research/configs/cycle06_appworld_source.json"
        ).read_text()
    )


def frame(history=None):
    return {
        "task_id": "1111111_1",
        "public_instruction": "Change the public app.",
        "results": history or [],
        "completion_flag": False,
        "request_id": "prefix",
        "harness_only_state": {"privileged": "DO_NOT_SEND"},
        "native_success": "DO_NOT_SEND",
    }


def test_parsing_is_public_and_fallbacks_are_explicit():
    assert parse_plan('```json\n{"intent":"read"}\n```') == ({"intent": "read"}, False)
    assert parse_plan("[]")[1]
    assert parse_code('{"code":"print(1)"}') == ("print(1)", False)
    assert parse_code("```python\nprint(1)\n```") == ("print(1)", True)


def test_context_allowlist_and_cap_include_truncation_metadata():
    value = prompt_context(frame([{"program": "print(1)", "output": "x" * 6000}]), 5000)
    assert "DO_NOT_SEND" not in canonical(value)
    assert len(canonical(value)) <= 5000
    assert value["history"][0]["truncated"]
    with pytest.raises(ValueError):
        prompt_context(frame(), 1)


def test_context_uses_latest_entries_in_original_order():
    value = prompt_context(
        frame([{"program": str(i), "output": "x" * 100} for i in range(10)]), 550
    )
    programs = [item["program"] for item in value["history"]]
    assert programs[-1] == "9"
    assert programs == sorted(programs)
    assert value["omitted_history_entries"] == 10 - len(programs)
    assert len(canonical(value)) <= 550


def test_selection_is_disjoint_deterministic_and_excludes_oracle(tmp_path):
    native = tmp_path / "data"
    (native / "datasets").mkdir(parents=True)
    ids = [f"{i:07x}_{variant}" for i in range(20) for variant in (1, 2, 3)]
    (native / "datasets/train.txt").write_text("\n".join([*ids, "07b42fd_1"]))
    first = select_groups(native, settings())
    assert first == select_groups(native, settings())
    chosen = [item for split in first.values() for item in split]
    assert len(chosen) == len(set(chosen)) == 15
    assert all(
        item.endswith("_1") and not item.startswith("07b42fd") for item in chosen
    )


@pytest.mark.parametrize(
    "change",
    [
        {"excluded_scenarios": []},
        {"max_steps": 51},
        {"max_steps": True},
        {"max_usd": 6},
        {"replicates": 0},
        {"audit_groups": -1},
    ],
)
def test_invalid_collection_settings_fail_before_paid_calls(change):
    with pytest.raises(ValueError):
        validate_settings({**settings(), **change})


def test_fixed_team_can_recover_public_error_without_private_labels():
    class Worker:
        last = frame()

        def act(self, code):
            output = (
                "Execution failed. Invalid API" if not self.last["results"] else "done"
            )
            self.last = {
                **self.last,
                "results": [*self.last["results"], {"program": code, "output": output}],
                "completion_flag": output == "done",
            }
            return self.last

    class Service:
        count = 0

        def call(self, system, user, max_tokens, seed):
            assert "DO_NOT_SEND" not in user
            self.count += 1
            return SimpleNamespace(
                text='{"intent":"read"}'
                if self.count % 2
                else '{"code":"public_api()"}',
                request_id=str(self.count),
            )

    store, service = RunStore(), Service()
    result = run_episode(
        Worker(), service, settings(), "1111111_1", 0, store, "fixture"
    )
    assert result["steps"] == 2 and result["local_action_errors"] == 1
    assert service.count == 4 and result["completion_flag"]
    assert result["provider_failure"] is None
    assert store.read("source_steps", "fixture-00")["environment_prefix_id"] == "prefix"


def test_provider_failure_is_not_a_method_outcome():
    class Service:
        def call(self, *args):
            raise RecordedCallError("recorded provider error")

    worker = SimpleNamespace(last=frame())
    result = run_episode(
        worker, Service(), settings(), "1111111_1", 0, RunStore(), "fixture"
    )
    assert result["steps"] == 0 and result["provider_failure"]


def test_registered_horizon_must_fit_actual_worker_before_any_call():
    class Service:
        def call(self, *args):
            pytest.fail("no paid call may precede worker-capacity validation")

    revised = {**settings(), "max_steps": 50}
    validate_settings(revised)
    with pytest.raises(ValueError, match="running worker"):
        run_episode(
            SimpleNamespace(last=frame()),
            Service(),
            revised,
            "1111111_1",
            0,
            RunStore(),
            "fixture",
        )


def test_versioned_public_onboarding_and_raw_code_do_not_change_legacy_parser():
    revised = {
        **settings(),
        "prompt_version": "public-onboarding-v2",
        "executor_format": "python",
    }
    validate_settings(revised)
    planner, executor = role_prompts(revised)
    assert "show_api_doc" in planner and "show_api_doc" in executor
    assert "complete_task(answer=answer)" in planner
    assert "no JSON wrapper" in executor
    assert parse_executor_response("print(1)", revised) == ("print(1)", False)
    assert parse_executor_response("```python\nprint(1)", revised) == ("print(1)", True)
    assert parse_executor_response("```python\nprint(1)\n```", revised) == (
        "print(1)",
        True,
    )
    assert parse_executor_response('{"code":"print(1)"}', revised) == ("print(1)", True)
    assert parse_executor_response("print(1)", settings()) == ("print(1)", True)
    with pytest.raises(ValueError):
        validate_settings({**revised, "executor_format": "json"})


def test_declared_transport_prices_preserve_defaults_and_reach_client():
    from copromem.providers import BudgetedOpenRouterClient, BudgetLedger

    assert transport_price_caps(settings()) == {
        "prompt_price_per_million": 0.25,
        "completion_price_per_million": 0.5,
    }
    revised = {
        **settings(),
        "prompt_price_per_million": 0.5,
        "completion_price_per_million": 2.0,
        "max_usd": 1,
    }
    validate_settings(revised)
    client = BudgetedOpenRouterClient(
        "fixture-not-a-key",
        "mock/model",
        "mock/provider",
        BudgetLedger(RunStore(), revised["max_usd"], 2),
        **transport_price_caps(revised),
    )
    assert client.request_configuration["max_prompt_price_per_million"] == 0.5
    assert client.request_configuration["max_completion_price_per_million"] == 2.0


@pytest.mark.parametrize(
    "field", ["prompt_price_per_million", "completion_price_per_million"]
)
@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True, "0.5"])
def test_invalid_route_price_caps_fail_before_paid_calls(field, value):
    with pytest.raises(ValueError):
        validate_settings({**settings(), field: value})


def expanded_settings():
    return {
        **settings(),
        "context_version": "public-history-budget-v2",
        "context_chars": 64000,
        "history_output_chars": 16000,
        "history_program_chars": 6000,
        "max_steps": 50,
    }


def test_expanded_context_preserves_public_output_and_declared_budget():
    revised = expanded_settings()
    validate_settings(revised)
    observed = frame([{"program": "print('public')", "output": "x" * 8000 + "TAIL"}])
    old = context_for_step(observed, settings(), 0)
    assert old == prompt_context(observed, settings()["context_chars"])
    assert "TAIL" not in canonical(old)
    new = context_for_step(observed, revised, 7)
    assert new["history"][0]["output"].endswith("TAIL")
    assert not new["history"][0]["truncated"]
    assert new["step_budget"] == {
        "total_action_steps": 50,
        "remaining_including_current": 43,
    }
    assert "DO_NOT_SEND" not in canonical(new)
    assert len(canonical(new)) <= revised["context_chars"]
    assert (
        context_for_step(frame(), revised, 49)["step_budget"][
            "remaining_including_current"
        ]
        == 1
    )
    with pytest.raises(ValueError):
        context_for_step(frame(), revised, 50)


@pytest.mark.parametrize(
    "change",
    [
        {"history_output_chars": 0},
        {"history_program_chars": True},
        {"history_output_chars": 64000},
        {"context_version": "unknown"},
        {"context_version": "v1"},
    ],
)
def test_invalid_expanded_context_settings_fail_before_paid_calls(change):
    with pytest.raises(ValueError):
        validate_settings({**expanded_settings(), **change})


def test_expanded_context_budget_metadata_is_inside_total_cap():
    revised = {**expanded_settings(), "context_chars": 200}
    value = context_for_step(frame(), revised, 0)
    assert len(canonical(value)) <= 200
    with pytest.raises(ValueError):
        context_for_step(frame(), {**revised, "context_chars": 1}, 0)
