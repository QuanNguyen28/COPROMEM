from pathlib import Path
from unittest.mock import MagicMock

import pytest
from copromem.openrouter_experiment import (
    OpenRouterMultiAgentRunner,
    build_default_test_suite,
    load_api_key,
    parse_json_object,
)
from copromem.real_gsm8k_experiment import CallResult, Usage


def test_load_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    # 1. From CLI
    assert load_api_key(cli_key="sk-cli-123") == "sk-cli-123"

    # 2. From env file
    env_file = tmp_path / ".env"
    env_file.write_text('OPENROUTER_API_KEY="sk-env-456"\n', encoding="utf-8")
    assert load_api_key(cli_key=None, env_path=str(env_file)) == "sk-env-456"

    # 3. Missing
    missing_file = tmp_path / "non_existent.env"
    assert load_api_key(cli_key=None, env_path=str(missing_file)) == ""


def test_parse_json_object():
    # Clean JSON
    assert parse_json_object('{"key": "value"}') == {"key": "value"}

    # JSON with surrounding markdown text
    text_with_fences = 'Here is the plan:\n```json\n{"declared_cardinality": "one_to_one"}\n```\nDone.'
    parsed = parse_json_object(text_with_fences)
    assert parsed.get("declared_cardinality") == "one_to_one"

    # Malformed text
    assert parse_json_object("no json here") == {}


def test_openrouter_multi_agent_runner_with_mock_client():
    mock_client = MagicMock()
    mock_client.spent_usd = 0.001
    mock_client.calls = 3

    # Mock Planner output
    mock_plan_reply = CallResult(
        text='{"declared_cardinality": "one_to_many", "expected_rows": 25, "join_keys": ["customer_id"]}',
        usage=Usage(prompt_tokens=50, completion_tokens=25, usd=0.0005),
        model="openai/gpt-4o-mini",
    )

    # Mock Solver output
    mock_solve_reply = CallResult(
        text='{"assumed_cardinality": "one_to_many", "output_rows": 25, "preserves_row_semantics": true}',
        usage=Usage(prompt_tokens=40, completion_tokens=20, usd=0.0005),
        model="openai/gpt-4o-mini",
    )

    mock_client.chat.side_effect = [mock_plan_reply, mock_solve_reply]

    tasks, schema = build_default_test_suite()
    task_standard = tasks[0]

    runner = OpenRouterMultiAgentRunner(mock_client)
    res = runner.run_episode(task_standard, schema, arm="copromem_v2", seed=42)

    assert res.task_id == "task_standard_01"
    assert res.success
    assert res.declared_cardinality == "one_to_many"
    assert len(runner.fast_buffer.traces) == 1
    assert runner.fast_buffer.traces[0].success


def test_twin_task_pattern_separation_protection():
    mock_client = MagicMock()
    mock_client.spent_usd = 0.001
    mock_client.calls = 2

    mock_plan_reply = CallResult(
        text='{"declared_cardinality": "one_to_many", "expected_rows": 100}',
        usage=Usage(prompt_tokens=50, completion_tokens=25, usd=0.0005),
        model="openai/gpt-4o-mini",
    )
    mock_solve_reply = CallResult(
        text='{"assumed_cardinality": "one_to_many", "output_rows": 100, "preserves_row_semantics": true}',
        usage=Usage(prompt_tokens=40, completion_tokens=20, usd=0.0005),
        model="openai/gpt-4o-mini",
    )
    mock_client.chat.side_effect = [mock_plan_reply, mock_solve_reply]

    tasks, schema = build_default_test_suite()
    task_twin = tasks[1]  # Intentional expansion twin task

    runner = OpenRouterMultiAgentRunner(mock_client)
    # COPROMEM 2.0 detects pattern separation and does not erroneously force row-preservation verification
    res = runner.run_episode(task_twin, schema, arm="copromem_v2", seed=42)

    assert res.task_id == "task_expansion_twin"
    assert res.success


def test_benchmark_suites_registry():
    from copromem.openrouter_experiment import (
        BENCHMARK_REGISTRY,
        get_benchmark_suite,
    )

    for name in ("twin_task", "alfworld_slice", "appworld_slice", "webarena_slice"):
        tasks, schema = get_benchmark_suite(name)
        assert len(tasks) >= 2
        assert schema.schema_id.startswith("schema_")
        assert len(schema.contracts) >= 1

    with pytest.raises(ValueError, match="Unknown benchmark: 'invalid_bench'"):
        get_benchmark_suite("invalid_bench")


def test_estimate_benchmark_cost():
    from copromem.openrouter_experiment import estimate_benchmark_cost

    est_mini = estimate_benchmark_cost("openai/gpt-4o-mini", num_tasks=2, num_arms=3)
    assert est_mini["total_episodes"] == 6.0
    assert est_mini["est_usd"] > 0
    assert est_mini["est_usd"] < 0.05

    est_4o = estimate_benchmark_cost("openai/gpt-4o", num_tasks=2, num_arms=3)
    assert est_4o["est_usd"] > est_mini["est_usd"]


def test_main_dry_run_no_api_key(capsys, monkeypatch):
    import sys
    from copromem.openrouter_experiment import main

    monkeypatch.setattr(sys, "argv", ["openrouter_experiment.py", "--benchmark", "twin_task", "--dry-run"])
    main()
    captured = capsys.readouterr()
    assert "COPROMEM 2.0 OpenRouter Experiment Runner" in captured.out
    assert "[DRY RUN COMPLETE] No API calls were made." in captured.out


def test_scale_smoke_vs_conference():
    from copromem.openrouter_experiment import get_benchmark_suite

    # Smoke scale: exactly 2 tasks
    tasks_smoke, _ = get_benchmark_suite("webarena", scale="smoke")
    assert len(tasks_smoke) == 2

    # Conference scale: 20 stratified tasks
    tasks_conf, _ = get_benchmark_suite("webarena", scale="conference")
    assert len(tasks_conf) == 20

    # Max-tasks clipping
    tasks_clipped, _ = get_benchmark_suite("webarena", scale="conference", max_tasks=7)
    assert len(tasks_clipped) == 7


