from __future__ import annotations

import json

import pytest

from copromem.integrations.reasoning_bank.appworld import ReasoningBank, build_experience
from copromem.integrations.reasoning_bank.retrieval_provenance import (
    ContentAddressedStore,
    RetrievalProvenanceError,
    materialize,
    verify,
)


def _item(identity: str, vector: list[float]):
    return build_experience(task_id=identity, query=identity, trajectory=[identity], status="success",
                            judge_record={"label": "success"},
                            extraction_text=f"# Memory Item 1\n## Title {identity}\n## Description D\n## Content C",
                            query_embedding=vector)


def _record(tmp_path, bank, vector, name="r.json"):
    return materialize(bank=bank, query="public query", query_vector=vector,
                       store=ContentAddressedStore(tmp_path / "objects"), path=tmp_path / name,
                       identity={"trajectory_id": "t", "task_id": "x", "arm": "reasoningbank_dynamic", "trial_id": 1, "seed": 1},
                       embedding={"model": "openai/text-embedding-3-small", "provider": "azure", "dimensions": len(vector)})


def test_empty_bank_proves_empty_top1_and_guidance(tmp_path):
    guidance, record = _record(tmp_path, ReasoningBank(), [1.0, 0.0])
    assert guidance == "" and record["selection"]["empty_bank"] is True
    assert verify(path=tmp_path / "r.json", store=ContentAddressedStore(tmp_path / "objects"))["selection"]["selected_experience_id"] is None


def test_top1_tie_break_and_restart_are_deterministic(tmp_path):
    first, second = _item("first", [1.0, 0.0]), _item("second", [1.0, 0.0])
    guidance, record = _record(tmp_path, ReasoningBank([first, second]), [1.0, 0.0])
    assert record["selection"]["selected_experience_id"] == first.experience_id
    assert record["selection"]["selected_rank"] == 1 and guidance
    assert verify(path=tmp_path / "r.json", store=ContentAddressedStore(tmp_path / "objects")) == record


@pytest.mark.parametrize("mutation", ["query", "candidate", "order", "score", "selected", "guidance"])
def test_tampering_fails_closed(tmp_path, mutation):
    first, second = _item("first", [1.0, 0.0]), _item("second", [0.0, 1.0])
    _guidance, record = _record(tmp_path, ReasoningBank([first, second]), [1.0, 0.0])
    path = tmp_path / "r.json"; value = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "query": value["query"]["vector"]["sha256"] = "0" * 64
    elif mutation == "candidate": value["candidates"][0]["vector"]["sha256"] = "0" * 64
    elif mutation == "order": value["candidates"] = list(reversed(value["candidates"]))
    elif mutation == "score": value["candidates"][0]["score"]["decimal"] = "0"
    elif mutation == "selected": value["selection"]["selected_experience_id"] = second.experience_id
    else: value["guidance"]["sha256"] = "0" * 64
    copy = dict(value); copy.pop("record_sha256"); value["record_sha256"] = __import__("copromem.integrations.reasoning_bank.appworld", fromlist=["sha256"]).sha256(copy)
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(RetrievalProvenanceError): verify(path=path, store=ContentAddressedStore(tmp_path / "objects"))


def test_invalid_vectors_fail_before_persistence(tmp_path):
    with pytest.raises(RetrievalProvenanceError): _record(tmp_path, ReasoningBank(), [float("nan"), 0.0])
    with pytest.raises(RetrievalProvenanceError): _record(tmp_path, ReasoningBank(), [0.0, 0.0])
