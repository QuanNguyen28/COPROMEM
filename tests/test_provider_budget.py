import json

import pytest

from copromem.checkpoints import RunStore
from copromem.providers import BudgetedOpenRouterClient, BudgetExceeded, BudgetLedger


def test_budget_reserves_before_attempt_and_survives_restart(tmp_path):
    ledger = BudgetLedger(RunStore(tmp_path), 0.1, 3)
    first = ledger.reserve(0.06)
    with pytest.raises(BudgetExceeded):
        ledger.reserve(0.05)
    ledger.settle(first, 0.02)
    ledger.reserve(0.06)  # ambiguous/unsettled request retains reserve
    resumed = BudgetLedger(RunStore(tmp_path), 0.1, 3)
    assert resumed.charged_or_reserved == pytest.approx(0.08)
    with pytest.raises(BudgetExceeded):
        resumed.reserve(0.03)


def test_transport_pins_provider_logs_seed_and_accounts_cost(monkeypatch, tmp_path):
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps(
                {
                    "id": "response-1",
                    "provider": "Mistral",
                    "model": "mock/model",
                    "choices": [
                        {"message": {"content": None}, "finish_reason": "length"}
                    ],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                        "cost": 0.00001,
                    },
                }
            ).encode()

    def open_request(request, timeout):
        requests.append(json.loads(request.data))
        assert len(list((tmp_path / "reservations").glob("*.json"))) == 1
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", open_request)
    ledger = BudgetLedger(RunStore(tmp_path), 0.1, 10)
    client = BudgetedOpenRouterClient("SENSITIVE", "mock/model", "mistral", ledger)
    result = client.chat("system", "user", 100, seed=42)
    assert requests[0]["seed"] == 42
    assert requests[0]["provider"]["allow_fallbacks"] is False
    assert requests[0]["provider"]["only"] == ["mistral"]
    assert result.text == ""  # null must not turn into the bogus memory string 'None'
    assert ledger.charged_or_reserved == pytest.approx(0.00001)
    assert result.metadata["finish_reason"] == "length"
    for path in tmp_path.rglob("*.json"):
        assert "SENSITIVE" not in path.read_text()


def test_no_request_can_start_after_attempt_cap():
    ledger = BudgetLedger(RunStore(), 0.1, 1)
    ledger.reserve(0.001)
    with pytest.raises(BudgetExceeded):
        ledger.reserve(0.001)


def test_invalid_or_higher_than_authorized_budget_rejected():
    with pytest.raises(ValueError):
        BudgetLedger(RunStore(), 5.01, 100)


def test_overrun_is_recorded_and_blocks_new_calls_even_after_resume(tmp_path):
    ledger = BudgetLedger(RunStore(tmp_path), 0.2, 10)
    key = ledger.reserve(0.01)
    with pytest.raises(BudgetExceeded):
        ledger.settle(key, 0.02)
    assert ledger.charged_or_reserved == pytest.approx(0.02)
    with pytest.raises(BudgetExceeded):
        ledger.reserve(0.01)
    resumed = BudgetLedger(RunStore(tmp_path), 0.2, 10)
    with pytest.raises(BudgetExceeded):
        resumed.reserve(0.01)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, True, "0.5"])
def test_invalid_price_ceiling_rejected_without_reservation(value):
    ledger = BudgetLedger(RunStore(), 1, 10)
    with pytest.raises(ValueError):
        BudgetedOpenRouterClient(
            "fixture",
            "mock/model",
            "mock/provider",
            ledger,
            prompt_price_per_million=value,
        )
    assert not ledger.reservations
