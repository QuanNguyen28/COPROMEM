from decimal import Decimal

from copromem.real_gsm8k_experiment import (
    CallResult,
    Example,
    Usage,
    extract_prediction,
    load_cumulative_memory,
    run_experiment,
    verify_plan,
)


class FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, system: str, user: str, max_tokens: int) -> CallResult:
        self.calls += 1
        usage = Usage(20, 10, 30, usd=0.00001, latency_seconds=0.01)
        if "solving agent" in system:
            answer = "2" if "one plus one" in user else "4"
            return CallResult(f"FINAL_ANSWER: {answer}", usage, "fake/model")
        if "Repair the artifact" in user:
            return CallResult(
                '{"operations":["1+1"],"answer_unit":"items","check":"inverse check"}',
                usage,
                "fake/model",
            )
        if "two plus two" in user:
            return CallResult(
                '{"operations":["2+2"],"answer_unit":"items","check":"inverse check"}',
                usage,
                "fake/model",
            )
        return CallResult('{"operations":["1+1"],"answer_unit":"items","check":""}', usage, "fake/model")


def test_answer_extraction_and_plan_verifier() -> None:
    assert extract_prediction("work\nFINAL_ANSWER: 1,250.5") == Decimal("1250.5")
    assert verify_plan({"operations": ["2+2"], "answer_unit": "items", "check": "inverse"}) == []


def test_real_agent_pipeline_smoke_with_fake_calls() -> None:
    client = FakeClient()
    build = [
        Example("train-a", "one plus one", Decimal(2)),
        Example("train-b", "two plus two", Decimal(4)),
    ]
    evaluation = [Example("test-a", "one plus one", Decimal(2))]
    report = run_experiment(client, build, evaluation, {"id": "fake/model"})
    assert report["memory_construction"]["success_only_memory_available"] is True
    assert report["memory_construction"]["copromem_contract"]["admitted"] is False
    assert set(report["evaluation"]) == {"no_memory", "success_only_memory", "copromem"}
    assert report["experiment_totals"]["measured_agent_calls"] == client.calls
    assert report["evaluation"]["no_memory"]["metrics"]["task_success"]["pass_at_1"] == 1.0


def test_prior_failure_evidence_can_admit_reusable_contract(tmp_path) -> None:
    path = tmp_path / "prior.json"
    path.write_text(
        '{"memory_construction":{"copromem_contract":{"evidence":'
        '{"build_failures":1,"failures_with_observable_violation":1,'
        '"successful_valid_handoffs":1}}}}',
        encoding="utf-8",
    )
    memory = load_cumulative_memory([path])
    client = FakeClient()
    build = [Example("train-a", "one plus one", Decimal(2))]
    evaluation = [Example("test-a", "one plus one", Decimal(2))]
    report = run_experiment(client, build, evaluation, {"id": "fake/model"}, memory)
    contract = report["memory_construction"]["copromem_contract"]
    assert contract["admitted"] is True
    assert contract["reused_prior_contract"] is True
