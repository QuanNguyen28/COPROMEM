from __future__ import annotations

import json
from pathlib import Path

import pytest

from copromem.integrations.reasoning_bank.appworld import ReasoningBank, build_experience
from copromem.integrations.reasoning_bank.checkpoints import (
    DynamicCheckpointError,
    ReasoningBankDynamicCheckpoints,
)


def _append_settled(ledger: Path, call_id: str = "call-1", role: str = "reasoningbank_judge") -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": "reserve", "id": call_id, "usd": 1, "role": role}) + "\n")
        handle.write(json.dumps({"event": "settle", "id": call_id, "usd": 0.1, "role": role}) + "\n")


def _append_update_settlements(ledger: Path, prefix: str) -> None:
    for suffix, role in (("judge", "reasoningbank_judge"),
                         ("extract", "reasoningbank_extraction"),
                         ("embedding", "reasoningbank_embedding")):
        _append_settled(ledger, f"{prefix}-{suffix}", role)


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
                                update=lambda index=index: (_append_update_settlements(manager.ledger_path, f"call-{index}"),
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
                   evidence_journal_sha256="journal", update=lambda: (_append_update_settlements(manager.ledger_path, "first"),
                                                                        bank.commit(_experience(1)))[1])
    target = manager._snapshot_path(1) if kind == "snapshot" else manager._marker_path(1)
    target.unlink()
    with pytest.raises(DynamicCheckpointError, match="ambiguous"):
        manager.reconcile(initial)


def test_corruption_and_wrong_predecessor_fail_closed(tmp_path: Path):
    manager = _manager(tmp_path, 1)
    initial, bank = ReasoningBank(), ReasoningBank()
    manager.update(bank=bank, initial_bank=initial, trajectory=_trajectory(1), retrieval_record={},
                   evidence_journal_sha256="journal", update=lambda: (_append_update_settlements(manager.ledger_path, "first"),
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
    manager.update(bank=bank, initial_bank=initial, trajectory=_trajectory(1), retrieval_record={},
                   evidence_journal_sha256="journal", update=lambda: (_append_update_settlements(manager.ledger_path, "first"),
                                                                        bank.commit(_experience(1)))[1])
    with pytest.raises(DynamicCheckpointError, match="next frozen"):
        manager.update(bank=bank, initial_bank=initial, trajectory=_trajectory(1), retrieval_record={},
                   evidence_journal_sha256="journal", update=lambda: None)


def test_completed_marker_uses_closed_interval_not_later_executor_or_retrieval(tmp_path: Path):
    manager = _manager(tmp_path, 2)
    initial, bank = ReasoningBank(), ReasoningBank()
    manager.update(bank=bank, initial_bank=initial, trajectory=_trajectory(1), retrieval_record={},
                   evidence_journal_sha256="journal-1",
                   update=lambda: (_append_update_settlements(manager.ledger_path, "first"), bank.commit(_experience(1)))[1])
    marker = json.loads(manager._marker_path(1).read_text(encoding="utf-8"))
    assert isinstance(marker["ledger_settlement_end_byte_offset"], int)
    # Both kinds of later settlement were the production failure trigger; they
    # must lie outside the marker's explicit closed interval.
    _append_settled(manager.ledger_path, "later-executor", "executor:reasoningbank_dynamic:t2:trial=1:seed=2")
    _append_settled(manager.ledger_path, "later-retrieval", "reasoningbank_embedding")
    restored = manager.reconcile(initial)
    assert restored.next_trajectory_id == _trajectory(2)["trajectory_id"]


def test_legacy_marker_derives_boundary_without_later_calls(tmp_path: Path):
    manager = _manager(tmp_path, 2)
    initial, bank = ReasoningBank(), ReasoningBank()
    manager.update(bank=bank, initial_bank=initial, trajectory=_trajectory(1), retrieval_record={},
                   evidence_journal_sha256="journal-1",
                   update=lambda: (_append_update_settlements(manager.ledger_path, "first"), bank.commit(_experience(1)))[1])
    marker_path = manager._marker_path(1)
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker.pop("ledger_settlement_end_byte_offset")
    marker.pop("ledger_settlement_interval_sha256")
    marker_path.write_text(json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    _append_settled(manager.ledger_path, "later-executor", "executor:reasoningbank_dynamic:t2:trial=1:seed=2")
    _append_settled(manager.ledger_path, "later-retrieval", "reasoningbank_embedding")
    assert manager.reconcile(initial).next_index == 2


@pytest.mark.parametrize("kind", ["extra", "missing", "duplicate", "reordered", "tampered"])
def test_settlement_interval_tampering_fails_closed(tmp_path: Path, kind: str):
    manager = _manager(tmp_path, 1)
    initial, bank = ReasoningBank(), ReasoningBank()
    manager.update(bank=bank, initial_bank=initial, trajectory=_trajectory(1), retrieval_record={},
                   evidence_journal_sha256="journal",
                   update=lambda: (_append_update_settlements(manager.ledger_path, "first"), bank.commit(_experience(1)))[1])
    marker = json.loads(manager._marker_path(1).read_text(encoding="utf-8"))
    if kind == "extra":
        # Add an unbound lifecycle pair inside the interval by extending the
        # marker boundary and recomputing its byte hash.
        _append_settled(manager.ledger_path, "extra", "reasoningbank_embedding")
        marker["ledger_settlement_end_byte_offset"] = manager.ledger_path.stat().st_size
        payload = manager.ledger_path.read_bytes()[int(_read_intent_offset(manager)):]
        marker["ledger_settlement_interval_sha256"] = __import__("hashlib").sha256(payload).hexdigest()
    elif kind == "missing":
        marker["newly_settled_provider_ids"] = marker["newly_settled_provider_ids"][:-1]
    elif kind == "duplicate":
        marker["newly_settled_provider_ids"].append(marker["newly_settled_provider_ids"][0])
    elif kind == "reordered":
        marker["newly_settled_provider_ids"] = list(reversed(marker["newly_settled_provider_ids"]))
    else:
        marker["ledger_settlement_interval_sha256"] = "0" * 64
    manager._marker_path(1).write_text(json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(DynamicCheckpointError):
        manager.reconcile(initial)


def _read_intent_offset(manager: ReasoningBankDynamicCheckpoints) -> int:
    return int(json.loads(manager._intent_path(1).read_text(encoding="utf-8"))["ledger_byte_offset"])


def test_restart_after_completed_update_then_scored_but_not_updated(tmp_path: Path):
    manager = _manager(tmp_path, 2)
    initial, bank = ReasoningBank(), ReasoningBank()
    manager.update(bank=bank, initial_bank=initial, trajectory=_trajectory(1), retrieval_record={},
                   evidence_journal_sha256="journal-1",
                   update=lambda: (_append_update_settlements(manager.ledger_path, "first"), bank.commit(_experience(1)))[1])
    # This models a durable scored second trajectory: only executor/retrieval
    # calls exist, so recovery must not reinterpret them as update 1 activity.
    _append_settled(manager.ledger_path, "trial-2-executor", "executor:reasoningbank_dynamic:t2:trial=1:seed=2")
    _append_settled(manager.ledger_path, "trial-2-query", "reasoningbank_embedding")
    state = manager.reconcile(initial)
    assert state.next_trajectory_id == _trajectory(2)["trajectory_id"]
