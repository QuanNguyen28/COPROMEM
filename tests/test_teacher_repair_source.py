import json
import runpy
from pathlib import Path

import pytest

M = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/teacher_repair_source.py")
)


def test_exact_duplicates_keep_all_indices_and_distinct_outputs():
    r = M["grouped_history"](["print(1)"] * 3, ["one", "one", "two"], 1)
    assert [x["indices"] for x in r] == [[0, 1], [2]]
    assert all(x["output_truncated"] for x in r)
    assert [x["output"] for x in r] == ["o", "t"]


def test_valid_patch_is_parsed_not_executed_and_abstention_is_explicit():
    p = M["parse_proposal"](
        json.dumps(
            {
                "action_index": 2,
                "code": "raise RuntimeError('not executed')",
                "diagnosis": "fixture",
            }
        ),
        [2],
    )
    assert p["status"] == "valid_proposal"
    assert (
        M["parse_proposal"](
            '{"action_index":null,"code":null,"diagnosis":"unknown"}', [2]
        )["status"]
        == "abstained"
    )


@pytest.mark.parametrize(
    "value",
    [
        '{"action_index":true,"code":"print(1)","diagnosis":"x"}',
        '{"action_index":3,"code":"print(1)","diagnosis":"x"}',
        '{"action_index":2,"code":"import os","diagnosis":"x"}',
        '{"action_index":2,"code":"print(1)","diagnosis":"x","native_success":true}',
        '{"action_index":2,"action_index":2,"code":"print(1)","diagnosis":"x"}',
        '{"action_index":2,"code":"def broken:","diagnosis":"x"}',
    ],
)
def test_invalid_unsafe_or_ambiguous_patch_is_not_repaired(value):
    with pytest.raises((ValueError, SyntaxError)):
        M["parse_proposal"](value, [2])


def test_provider_metadata_requires_no_seed_but_enforces_route_and_price():
    metadata = {
        "id": M["MODEL"],
        "endpoints": [
            {
                "tag": "anthropic",
                "supported_parameters": ["temperature", "max_tokens", "reasoning"],
                "pricing": {"prompt": "0.000003", "completion": "0.000015"},
                "context_length": 1000000,
                "max_completion_tokens": 128000,
            }
        ],
    }
    assert M["endpoint"](metadata, 1000)["tag"] == "anthropic"
    metadata["endpoints"][0]["pricing"]["prompt"] = "0.000004"
    with pytest.raises(ValueError):
        M["endpoint"](metadata, 1000)


def test_candidate_binds_exact_target_and_hashes_the_parsed_ast():
    slot = {"source_view": {"source_id": "fixture"}, "task_id": "fixture"}
    parsed = {"action_index": 2, "code": "print(1)"}
    c = M["effect_candidate"](slot, {"step": {"step": 2}}, "call", parsed)
    assert len(c["proposal"]["program_ast_digest"]) == 64
    assert c["target_action_index"] == 2
    with pytest.raises(ValueError):
        M["effect_candidate"](slot, {"step": {"step": 3}}, "call", parsed)


def test_teacher_transport_omits_seed_records_usage_and_never_persists_key(monkeypatch):
    import io

    from copromem.checkpoints import GenerationService, RunStore, canonical
    from copromem.providers import BudgetLedger

    sent = []

    def response(request, timeout):
        sent.append(json.loads(request.data))
        assert timeout == 180
        return io.BytesIO(
            json.dumps(
                {
                    "model": M["MODEL"],
                    "provider": "Anthropic",
                    "choices": [
                        {"message": {"content": "fixture"}, "finish_reason": "stop"}
                    ],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 2,
                        "total_tokens": 12,
                        "cost": 0.00006,
                    },
                }
            ).encode()
        )

    monkeypatch.setattr(M["urllib"].request, "urlopen", response)
    store = RunStore()
    client = M["TeacherClient"]("fixture-private-key-value", BudgetLedger(store, 3, 4))
    service = GenerationService(client, store, M["VERSION"])
    gen = service.call("system", "user", 10, 0)
    assert gen.text == "fixture" and gen.usage["usd"] == 0.00006
    assert "seed" not in sent[0] and not sent[0]["reasoning"]["enabled"]
    assert client.http_attempts == 1
    assert not store.read("calls", gen.request_id)["seed_forwarded"]
    assert "fixture-private-key-value" not in canonical(list(store._objects.values()))


def test_teacher_transport_failure_keeps_reservation_and_has_no_retry(monkeypatch):
    from copromem.checkpoints import (
        GenerationService,
        RecordedCallError,
        RunStore,
        canonical,
    )
    from copromem.providers import BudgetLedger

    def fail(*args, **kwargs):
        raise OSError("fixture-private-key-value")

    monkeypatch.setattr(M["urllib"].request, "urlopen", fail)
    store = RunStore()
    ledger = BudgetLedger(store, 3, 4)
    client = M["TeacherClient"]("fixture-private-key-value", ledger)
    with pytest.raises(RecordedCallError):
        GenerationService(client, store, M["VERSION"]).call("system", "user", 10, 0)
    assert client.http_attempts == 1 and ledger.charged_or_reserved > 0
    assert not ledger.settlements
    assert "fixture-private-key-value" not in canonical(list(store._objects.values()))
