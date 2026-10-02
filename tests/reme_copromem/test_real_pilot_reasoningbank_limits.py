"""Zero-provider admission checks for the real-pilot ReasoningBank arm."""
from __future__ import annotations

import pytest

from scripts import run_v622_parallel_real_pilot as pilot
from copromem.experiments.reme_copromem.runner import v5_budget_bound


def test_reasoningbank_retrieval_only_limit_matches_registered_schedule() -> None:
    pilot._validate_reasoningbank_call_limit_contract(pilot.CALL_LIMITS)
    assert pilot.CALL_LIMITS["reasoningbank_embedding"] == (
        pilot.TASK_COUNT * len(pilot.SEEDS)
    )


@pytest.mark.parametrize(
    "limits",
    [
        {**pilot.CALL_LIMITS, "reasoningbank_embedding": 0},
        {key: value for key, value in pilot.CALL_LIMITS.items() if key != "reasoningbank_embedding"},
        {**pilot.CALL_LIMITS, "reasoningbank_extraction": 1},
        {**pilot.CALL_LIMITS, "reasoningbank_judge": 1},
    ],
)
def test_reasoningbank_limit_contract_fails_closed(limits: dict[str, int]) -> None:
    with pytest.raises(RuntimeError):
        pilot._validate_reasoningbank_call_limit_contract(limits)


def test_reasoningbank_embedding_is_accounted_once_in_budget_bound() -> None:
    budget = v5_budget_bound(call_limits=pilot.CALL_LIMITS)
    assert budget["reasoningbank_embedding_calls"] == pilot.TASK_COUNT * len(pilot.SEEDS)
    assert budget["reasoningbank_embedding_usd"] == pytest.approx(
        pilot.TASK_COUNT * len(pilot.SEEDS) * 8192 * (0.02 / 1_000_000)
    )
