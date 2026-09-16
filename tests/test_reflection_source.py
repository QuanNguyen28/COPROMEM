import json
import runpy
from copy import deepcopy
from pathlib import Path

import pytest

from copromem.checkpoints import (
    GenerationService,
    IntegrityError,
    RunStore,
    canonical,
    digest,
)
from copromem.real_gsm8k_experiment import CallResult, Usage
from copromem.reflection_source import create_note, reflection_input, retry_settings
from copromem.stateful_source import context_for_step, validate_settings


def settings():
    return json.loads(
        (
            Path(__file__).parents[1]
            / "research/configs/cycle15_reflection_source.json"
        ).read_text()
    )


def frame(history=None):
    return {
        "task_id": "fixture_1",
        "public_instruction": "Act on the public request.",
        "results": history or [],
        "completion_flag": False,
        "harness_only_state": {"secret": "DO_NOT_SEND"},
        "native_evaluation": {"pass_count": 99, "test_name": "DO_NOT_SEND"},
    }


def populated(store=None):
    config = settings()
    source = {
        "task_id": "fixture_1",
        "episode_id": "old-fixture-r0",
        "reflection_input": reflection_input(frame(), False, config),
    }
    store = store or RunStore()
    store.write("protocol", "preregistration", config)
    store.write("reflection_sources", source["task_id"], source)
    store.write(
        "reflection_allocation",
        "sources",
        {"sources": {source["task_id"]: digest(source)}},
    )

    class Client:
        model = config["model"]
        count = 0

        @property
        def request_configuration(self):
            return {
                "provider": config["provider"],
                "allow_fallbacks": False,
                "max_prompt_price_per_million": 0.5,
                "max_completion_price_per_million": 2.0,
            }

        def chat(self, system, user, max_tokens, *, seed):
            assert "DO_NOT_SEND" not in user
            self.count += 1
            return CallResult(
                "Check observed arguments before acting.", Usage(), self.model
            )

    client = Client()
    service = GenerationService(client, store, config["cycle_id"])
    note = create_note(service, store, config, source)
    return store, config, source, client, service, note


def test_reflection_input_is_public_plus_one_binary_outcome():
    config = settings()
    validate_settings(config)
    value = reflection_input(frame(), False, config)
    assert set(value) == {"previous_attempt", "previous_native_success"}
    assert value["previous_native_success"] is False
    assert "DO_NOT_SEND" not in canonical(value)
    assert "pass_count" not in canonical(value)
    assert len(canonical(value)) <= config["reflection_context_chars"]


@pytest.mark.parametrize("outcome", [0, 1, "failed", None, {"success": False}])
def test_nonbinary_training_feedback_is_rejected(outcome):
    with pytest.raises(ValueError, match="binary"):
        reflection_input(frame(), outcome, settings())


def test_reflection_input_caps_and_reports_omission():
    config = {
        **settings(),
        "reflection_context_chars": 600,
        "history_output_chars": 200,
    }
    value = reflection_input(
        frame([{"program": "print(1)", "output": "x" * 300} for _ in range(8)]),
        False,
        config,
    )
    assert len(canonical(value)) <= 600
    assert value["previous_attempt"]["omitted_history_entries"] > 0
    assert value["previous_attempt"]["history"][0]["truncated"]


def test_recorded_note_reuses_exact_generation_and_changes_only_context_extension():
    store, config, source, client, service, note = populated()
    assert create_note(service, store, config, source) == note
    assert client.count == 1
    runtime = retry_settings(config, store, source["task_id"])
    assert runtime == {**config, "source_retry_note": note}
    current = frame()
    before = deepcopy(current)
    context = context_for_step(current, runtime, 0)
    assert context["source_retry_note"] == note
    assert current == before
    old = context_for_step(
        current, {**config, "context_version": "public-history-budget-v2"}, 0
    )
    assert "source_retry_note" not in old
    assert {
        key: value for key, value in context.items() if key != "source_retry_note"
    } == old


def test_note_consumes_the_same_context_cap_and_cannot_cross_tasks():
    store, config, source, _, _, _ = populated()
    runtime = retry_settings(config, store, source["task_id"])
    observed = frame([{"program": "print(1)", "output": "x" * 200} for _ in range(5)])
    reduced = {**runtime, "context_chars": 750}
    new = context_for_step(observed, reduced, 0)
    old = context_for_step(
        observed, {**reduced, "context_version": "public-history-budget-v2"}, 0
    )
    assert len(canonical(new)) <= 750
    assert new["omitted_history_entries"] > old["omitted_history_entries"]
    with pytest.raises(IntegrityError, match="another task"):
        context_for_step({**observed, "task_id": "other_1"}, runtime, 0)
    with pytest.raises(ValueError, match="context cap"):
        context_for_step(observed, {**runtime, "context_chars": 10}, 0)


@pytest.mark.parametrize(
    "mutation", ["source", "note", "response", "request", "allocation"]
)
def test_retry_note_cannot_be_changed_outside_recorded_provenance(mutation):
    store, config, source, _, _, _ = populated()
    original_read = store.read

    def changed(kind, key):
        value = deepcopy(original_read(kind, key))
        if kind == "reflection_sources" and mutation == "source":
            value["reflection_input"]["previous_native_success"] = True
        elif kind == "source_retry_notes" and mutation == "note":
            value["lesson"] = "Unrecorded hand-written correction."
        elif kind == "calls" and mutation == "response":
            value["response"]["text"] = "Unrecorded correction."
        elif kind == "calls" and mutation == "request":
            value["request"]["provider_configuration"]["provider"] = "other"
        elif kind == "reflection_allocation" and mutation == "allocation":
            value["sources"][source["task_id"]] = "wrong"
        return value

    store.read = changed
    with pytest.raises(IntegrityError):
        retry_settings(config, store, source["task_id"])


def test_context_audit_reconstructs_bound_note(tmp_path):
    store, config, source, _, _, _ = populated(RunStore(tmp_path))
    runtime = retry_settings(config, store, source["task_id"])
    boundary = frame()
    context = context_for_step(boundary, runtime, 0)
    handoff = {"public_context": context}
    store.write("public_handoffs", digest(handoff), handoff)
    store.write("stream_frames", "retry-000", boundary)
    store.write(
        "source_steps",
        "retry-00",
        {
            "episode_id": "retry",
            "step": 0,
            "public_checkpoint_id": digest(handoff),
            "code": "print(1)",
            "public_output": "1",
        },
    )
    audit = runpy.run_path(
        str(Path(__file__).parents[1] / "research/scripts/audit_context_visibility.py")
    )["audit"](tmp_path)
    assert audit["totals"]["boundaries"] == 1
    assert audit["model_calls"] == 0
