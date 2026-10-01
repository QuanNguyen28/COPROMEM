from __future__ import annotations

import json
from pathlib import Path

import pytest

from copromem.integrations.reasoning_bank.appworld import ReasoningBank, build_experience
from copromem.integrations.reasoning_bank.checkpoints import (
    DynamicCheckpointError,
    ReasoningBankDynamicCheckpoints,
)


def _append_settled(ledger: Path, call_id: str = "call-1") -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": "reserve", "id": call_id, "usd": 1, "role": "reasoningbank_judge"}) + "\n")
        handle.write(json.dumps({"event": "settle", "id": call_id, "usd": 0.1, "role": "reasoningbank_judge"}) + "\n")


def _trajectory(index: int) -> dict[str, object]:
    return {"trajectory_id": f"evaluation:reasoningbank_dynamic:t{index}:trial=1:seed={index}",
            "task_id": f"t{index}", "trial_id": 1, "seed": index,
            "history": [{"role": "user", "content": "public"}], "after_score": 1.0}


def _experience(index: int):
    return build_experience(task_id=f"t{index}", query=f"q{index}", trajectory=["public"], status="success",
                            judge_record={"label": "success", "id": index},
                            extraction_text=("# Memory Item 1\n## Title T\n## Description D\n"
                                             "## Content Public procedure."), query_embedding=[1.0, float(index)])


def _manager(tmp_path: Path, count: int = 2):
    order = [_trajectory(index)["trajectory_id"] for index in range(1, count + 1)]
    return ReasoningBankDynamicCheckpoints(root=tmp_path / "e-backed" / "dynamic", expected_trajectory_ids=order,
                                            ledger_path=tmp_path / "e-backed" / "ledger.jsonl")


def test_first_second_update_and_restart_restore_longest_verified_prefix(tmp_path: Path):
    manager = _manager(tmp_path)
    initial, bank = ReasoningBank(), ReasoningBank()
    for index in (1, 2):
        result = manager.update(bank=bank, initial_bank=initial, trajectory=_trajectory(index),
                                retrieval_record={"index": index}, evidence_journal_sha256=f"journal-{index}",
                                update=lambda index=index: (_append_settled(manager.ledger_path, f"call-{index}"),
                                                             bank.commit(_experience(index)))[1])
        assert result.update_index == index
    restored = manager.reconcile(initial)
    assert restored.next_trajectory_id is None
    assert restored.restored_bank.state() == bank.state()
    assert [entry.trajectory_id for entry in restored.completed] == [
        _trajectory(1)["trajectory_id"], _trajectory(2)["trajectory_id"]]


def test_intent_without_marker_fails_closed_and_does_not_repeat_update(tmp_path: Path):
    manager = _manager(tmp_path, 1)
    initial, bank = ReasoningBank(), ReasoningBank()
    called = 0
    def update():
        nonlocal called
        called += 1
        raise RuntimeError("provider interrupted")
    with pytest.raises(RuntimeError):
        manager.update(bank=bank, initial_bank=initial, trajectory=_trajectory(1), retrieval_record={},
                       evidence_journal_sha256="journal", update=update)
    assert called == 1
    with pytest.raises(DynamicCheckpointError, match="ambiguous"):
        manager.reconcile(initial)


@pytest.mark.parametrize("kind", ["snapshot", "marker"])
def test_missing_snapshot_or_marker_fails_closed(tmp_path: Path, kind: str):
    manager = _manager(tmp_path, 1)
    initial, bank = ReasoningBank(), ReasoningBank()
    manager.update(bank=bank, initial_bank=initial, trajectory=_trajectory(1), retrieval_record={},
                   evidence_journal_sha256="journal", update=lambda: (_append_settled(manager.ledger_path),
                                                                        bank.commit(_experience(1)))[1])
    target = manager._snapshot_path(1) if kind == "snapshot" else manager._marker_path(1)
    target.unlink()
    with pytest.raises(DynamicCheckpointError, match="ambiguous"):
        manager.reconcile(initial)


def test_corruption_and_wrong_predecessor_fail_closed(tmp_path: Path):
    manager = _manager(tmp_path, 1)
    initial, bank = ReasoningBank(), ReasoningBank()
    manager.update(bank=bank, initial_bank=initial, trajectory=_trajectory(1), retrieval_record={},
                   evidence_journal_sha256="journal", update=lambda: (_append_settled(manager.ledger_path),
                                                                        bank.commit(_experience(1)))[1])
    manager._snapshot_path(1).write_text("{}", encoding="utf-8")
    with pytest.raises(DynamicCheckpointError):
        manager.reconcile(initial)


def test_duplicate_and_wrong_order_are_rejected(tmp_path: Path):
    manager = _manager(tmp_path, 2)
    initial, bank = ReasoningBank(), ReasoningBank()
    with pytest.raises(DynamicCheckpointError, match="next frozen"):
        manager.update(bank=bank, initial_bank=initial, trajectory=_trajectory(2), retrieval_record={},
                       evidence_journal_sha256="journal", update=lambda: None)
    _append_settled(manager.ledger_path)
    manager.update(bank=bank, initial_bank=initial, trajectory=_trajectory(1), retrieval_record={},
                   evidence_journal_sha256="journal", update=lambda: bank.commit(_experience(1)))
    with pytest.raises(DynamicCheckpointError, match="next frozen"):
        manager.update(bank=bank, initial_bank=initial, trajectory=_trajectory(1), retrieval_record={},
                       evidence_journal_sha256="journal", update=lambda: None)
