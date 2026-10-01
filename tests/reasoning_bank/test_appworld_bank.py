from __future__ import annotations

import json

import pytest

from copromem.integrations.reasoning_bank.appworld import (
    Experience, ReasoningBank, build_experience, load_state, split_memory_items, write_state,
)


def experience(identity: str, query: str, vector: list[float], content: str) -> Experience:
    return Experience(identity, identity, query, "success", (content,), tuple(vector),
                      "a" * 64, "b" * 64, "c" * 64)


def test_top_one_retrieval_is_stable_reproducible_and_non_mutating():
    bank = ReasoningBank([
        experience("one", "delete phone contact", [1.0, 0.0], "delete guidance"),
        experience("two", "create note", [0.0, 1.0], "note guidance"),
    ])
    before = bank.state()
    result = bank.retrieve("remove contact", [0.9, 0.1])
    assert result.guidance == "delete guidance"
    assert result.provenance["selected_experience_ids"] == ["one"]
    assert bank.reproduce("remove contact", [0.9, 0.1], result.provenance) == result.guidance
    assert bank.state() == before


def test_empty_bank_returns_empty_guidance():
    result = ReasoningBank().retrieve("anything", [1.0])
    assert result.guidance == ""
    assert result.provenance["retrieval_empty"] is True


def test_fixed_tie_breaks_by_append_order():
    first = experience("first", "a", [1.0, 0.0], "first")
    second = experience("second", "b", [1.0, 0.0], "second")
    assert ReasoningBank([first, second]).retrieve("q", [1.0, 0.0]).guidance == "first"


def test_commit_is_idempotent_and_conflicts_fail():
    item = experience("same", "a", [1.0], "x")
    bank = ReasoningBank()
    first = bank.commit(item)
    assert bank.commit(item) == first
    with pytest.raises(ValueError, match="conflicting"):
        bank.commit(experience("same", "b", [1.0], "y"))


def test_state_round_trip_and_tamper_rejection(tmp_path):
    path = tmp_path / "bank.json"
    bank = ReasoningBank([experience("one", "a", [1.0], "x")])
    write_state(path, bank)
    assert load_state(path).state() == bank.state()
    value = json.loads(path.read_text())
    value["experiences"][0]["query"] = "tampered"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="state hash"):
        load_state(path)


def test_builds_success_and_failure_experiences():
    for status in ("success", "failure"):
        item = build_experience(
            task_id="task", query="query", trajectory=[{"role": "assistant", "content": "act"}],
            status=status, judge_record={"label": status},
            extraction_text="# Memory Item 1\n## Title T\n## Description D\n## Content C",
            query_embedding=[1.0, 2.0],
        )
        assert item.status == status
        assert item.experience_id.startswith("rb_")


def test_empty_extraction_rejected():
    with pytest.raises(ValueError, match="no memory"):
        split_memory_items("  ")

