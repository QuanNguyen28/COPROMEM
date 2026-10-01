from __future__ import annotations

import json

import pytest

from copromem.integrations.reasoning_bank.appworld import MEMORY_PROMPT, ReasoningBank, build_experience, render_retrieval_guidance
from copromem.integrations.reasoning_bank.retrieval_provenance import (
    ContentAddressedStore,
    RetrievalProvenanceError,
    bind_initial_prompt,
    materialize,
    typed_result,
    verify,
)
from copromem.experiments.reme_copromem.prompt_memory import render_executor_memory_slot


IDENTITY = {
    "trajectory_id": "evaluation:reasoningbank_dynamic:x:trial=1:seed=1",
    "task_id": "x", "arm": "reasoningbank_dynamic", "trial_id": 1, "seed": 1,
    "benchmark": "appworld", "manifest_sha256": "a" * 64,
    "runtime_identity_sha256": "b" * 64, "registry_sha256": "c" * 64,
}


def _item(identity: str, vector: list[float]):
    return build_experience(task_id=identity, query=identity, trajectory=[identity], status="success",
                            judge_record={"label": "success"},
                            extraction_text=f"# Memory Item 1\n## Title {identity}\n## Description D\n## Content C",
                            query_embedding=vector)


def _record(tmp_path, bank, vector, name="r.json"):
    try:
        lifecycle = bank.retrieve("public query", vector)
        rendered = render_retrieval_guidance(lifecycle.guidance)
        lifecycle_provenance = lifecycle.provenance
    except ValueError:
        # ``materialize`` must still reject malformed vectors at its own
        # public boundary before consulting lifecycle provenance.
        rendered, lifecycle_provenance = "", {}
    return materialize(bank=bank, query="public query", query_vector=vector,
                       store=ContentAddressedStore(tmp_path / "objects"), path=tmp_path / name,
                       identity=IDENTITY,
                       embedding={"model": "openai/text-embedding-3-small", "provider": "azure", "dimensions": len(vector)},
                       rendered_guidance=rendered, lifecycle_provenance=lifecycle_provenance)


def test_empty_bank_proves_empty_top1_and_guidance(tmp_path):
    guidance, record = _record(tmp_path, ReasoningBank(), [1.0, 0.0])
    assert guidance == "" and record["selection"]["empty_bank"] is True
    assert verify(path=tmp_path / "r.json", store=ContentAddressedStore(tmp_path / "objects"))["selection"]["selected_experience_id"] is None


def test_top1_tie_break_and_restart_are_deterministic(tmp_path):
    first, second = _item("first", [1.0, 0.0]), _item("second", [1.0, 0.0])
    guidance, record = _record(tmp_path, ReasoningBank([first, second]), [1.0, 0.0])
    assert record["selection"]["selected_experience_id"] == first.experience_id
    assert record["selection"]["selected_rank"] == 1 and guidance.startswith(MEMORY_PROMPT)
    raw = ContentAddressedStore(tmp_path / "objects").load_text(record["guidance"]["raw_memory_bytes"])
    assert guidance != raw
    assert verify(path=tmp_path / "r.json", store=ContentAddressedStore(tmp_path / "objects")) == record


@pytest.mark.parametrize("mutation", ["query", "candidate", "order", "score", "selected", "guidance", "lifecycle"])
def test_tampering_fails_closed(tmp_path, mutation):
    first, second = _item("first", [1.0, 0.0]), _item("second", [0.0, 1.0])
    _guidance, record = _record(tmp_path, ReasoningBank([first, second]), [1.0, 0.0])
    path = tmp_path / "r.json"; value = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "query": value["query"]["vector"]["sha256"] = "0" * 64
    elif mutation == "candidate": value["candidates"][0]["vector"]["sha256"] = "0" * 64
    elif mutation == "order": value["candidates"] = list(reversed(value["candidates"]))
    elif mutation == "score": value["candidates"][0]["score"]["decimal"] = "0"
    elif mutation == "selected": value["selection"]["selected_experience_id"] = second.experience_id
    elif mutation == "guidance": value["guidance"]["rendered_sha256"] = "0" * 64
    else: value["lifecycle_provenance"]["selected_experience_ids"] = ["wrong"]
    copy = dict(value); copy.pop("record_sha256"); value["record_sha256"] = __import__("copromem.integrations.reasoning_bank.appworld", fromlist=["sha256"]).sha256(copy)
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(RetrievalProvenanceError): verify(path=path, store=ContentAddressedStore(tmp_path / "objects"))


def test_invalid_vectors_fail_before_persistence(tmp_path):
    with pytest.raises(RetrievalProvenanceError): _record(tmp_path, ReasoningBank(), [float("nan"), 0.0])
    with pytest.raises(RetrievalProvenanceError): _record(tmp_path, ReasoningBank(), [0.0, 0.0])


def test_rendered_lifecycle_callback_and_initial_prompt_are_byte_identical(tmp_path):
    item = _item("unicode", [1.0, 0.0])
    guidance, record = _record(tmp_path, ReasoningBank([item]), [1.0, 0.0])
    raw = ContentAddressedStore(tmp_path / "objects").load_text(record["guidance"]["raw_memory_bytes"])
    # The regression originally observed 56 raw bytes passed as 342 rendered
    # bytes in the lifecycle; sizes are deliberately not assumed here, only
    # exact UTF-8 identities are.
    assert raw != guidance
    identity = dict(record["identity"])
    messages = [{"role": "user", "content": "Preamble\n" + render_executor_memory_slot(guidance) + "\nTrailing Δ"}]
    binding = bind_initial_prompt(path=tmp_path / "r.json", store=ContentAddressedStore(tmp_path / "objects"),
                                  messages=messages, callback_guidance=guidance, identity=identity)
    verified = verify(path=tmp_path / "r.json", store=ContentAddressedStore(tmp_path / "objects"), require_prompt_binding=True)
    result = typed_result(record=verified, store=ContentAddressedStore(tmp_path / "objects"))
    assert result.raw_memory == raw and result.rendered_guidance == guidance
    sealed = json.loads((tmp_path / "r.json.prompt-binding.json").read_text(encoding="utf-8"))
    assert sealed["rendered_guidance_sha256"] == result.rendered_guidance_sha256
    assert sealed["callback_guidance_sha256"] == result.rendered_guidance_sha256
    # Rebinding exact bytes is read-only/idempotent.
    assert bind_initial_prompt(path=tmp_path / "r.json", store=ContentAddressedStore(tmp_path / "objects"),
                               messages=messages, callback_guidance=guidance, identity=identity) == binding


@pytest.mark.parametrize("mutation", ["raw", "callback", "duplicate_slot", "identity", "binding"])
def test_prompt_binding_tampering_fails_closed(tmp_path, mutation):
    guidance, record = _record(tmp_path, ReasoningBank([_item("one", [1.0, 0.0])]), [1.0, 0.0])
    identity = dict(record["identity"])
    messages = [{"role": "user", "content": render_executor_memory_slot(guidance)}]
    bind_initial_prompt(path=tmp_path / "r.json", store=ContentAddressedStore(tmp_path / "objects"),
                        messages=messages, callback_guidance=guidance, identity=identity)
    if mutation == "raw":
        with pytest.raises(RetrievalProvenanceError):
            bind_initial_prompt(path=tmp_path / "r.json", store=ContentAddressedStore(tmp_path / "objects"),
                                messages=messages, callback_guidance="raw replacement", identity=identity)
        return
    if mutation == "callback":
        messages[0]["content"] = "missing slot"
        with pytest.raises(RetrievalProvenanceError):
            bind_initial_prompt(path=tmp_path / "r.json", store=ContentAddressedStore(tmp_path / "objects"),
                                messages=messages, callback_guidance=guidance, identity=identity)
        return
    if mutation == "duplicate_slot":
        messages[0]["content"] += render_executor_memory_slot(guidance)
        with pytest.raises(RetrievalProvenanceError):
            bind_initial_prompt(path=tmp_path / "r.json", store=ContentAddressedStore(tmp_path / "objects"),
                                messages=messages, callback_guidance=guidance, identity=identity)
        return
    if mutation == "identity":
        identity["task_id"] = "drift"
        with pytest.raises(RetrievalProvenanceError):
            bind_initial_prompt(path=tmp_path / "r.json", store=ContentAddressedStore(tmp_path / "objects"),
                                messages=messages, callback_guidance=guidance, identity=identity)
        return
    binding_path = tmp_path / "r.json.prompt-binding.json"
    binding_path.write_text('{"tampered":true}', encoding="utf-8")
    with pytest.raises(RetrievalProvenanceError):
        verify(path=tmp_path / "r.json", store=ContentAddressedStore(tmp_path / "objects"), require_prompt_binding=True)


@pytest.mark.parametrize("field", ["trajectory_id", "task_id", "arm", "trial_id", "seed", "benchmark",
                                    "manifest_sha256", "runtime_identity_sha256", "registry_sha256"])
def test_every_canonical_identity_field_is_fail_closed(tmp_path, field):
    identity = dict(IDENTITY)
    identity[field] = "" if field not in {"trial_id", "seed"} else 0
    with pytest.raises(RetrievalProvenanceError):
        materialize(bank=ReasoningBank(), query="public query", query_vector=[1.0, 0.0],
                    store=ContentAddressedStore(tmp_path / "objects"), path=tmp_path / "r.json",
                    identity=identity,
                    embedding={"model": "openai/text-embedding-3-small", "provider": "azure", "dimensions": 2},
                    rendered_guidance="", lifecycle_provenance={})


def test_empty_reasoningbank_prompt_is_byte_identical_to_no_memory(tmp_path):
    guidance, record = _record(tmp_path, ReasoningBank(), [1.0, 0.0])
    assert guidance == ""
    no_memory_messages = [{"role": "user", "content": "Public instruction\nTools: []"}]
    reasoningbank_messages = json.loads(json.dumps(no_memory_messages))
    bind_initial_prompt(path=tmp_path / "r.json", store=ContentAddressedStore(tmp_path / "objects"),
                        messages=reasoningbank_messages, callback_guidance=guidance,
                        identity=record["identity"])
    binding = json.loads((tmp_path / "r.json.prompt-binding.json").read_text(encoding="utf-8"))
    assert binding["memory_slot_occurrences"] == 0
    assert binding["initial_prompt_messages_sha256"] == __import__("copromem.integrations.reasoning_bank.appworld", fromlist=["sha256"]).sha256(no_memory_messages)
    assert reasoningbank_messages == no_memory_messages
