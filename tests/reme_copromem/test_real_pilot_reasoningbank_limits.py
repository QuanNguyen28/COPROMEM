"""Zero-provider admission checks for the real-pilot ReasoningBank arm."""
from __future__ import annotations

import pytest

from scripts import run_v622_parallel_real_pilot as pilot


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
