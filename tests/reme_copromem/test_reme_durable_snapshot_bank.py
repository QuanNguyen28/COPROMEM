from __future__ import annotations

import json
import pathlib

import pytest

from copromem.integrations.reme.bank import construct_durable_snapshot_bank, freeze_durable_final_snapshot, load_clone
from copromem.integrations.reme.transport import AppendOnlyLedger
from scripts.run_v61_reme_durable_construction_successor import _require_settled, capacity_decision


class FakeReMe:
    """Zero-provider implementation of the registered legacy HTTP contracts."""

    def __init__(self, fail_dump_at: int | None = None) -> None:
        self.stores: dict[str, list[dict]] = {"builder": [], "verifier": []}
        self.calls: list[str] = []
        self.fail_dump_at = fail_dump_at
        self.dumps = 0

    def post(self, base: str, endpoint: str, payload: dict) -> dict:
        self.calls.append(endpoint)
        if endpoint == "summary_task_memory":
            task_id = payload["trajectories"][0]["task_id"]
            return {"metadata": {"memory_list": [{"memory_id": f"m-{task_id}", "content": task_id, "vector": [1.0]}]}}
        if endpoint == "add_task_memory":
            self.stores[base].extend(payload["memory_list"])
            return {"metadata": {"ok": True}}
        if endpoint == "dump_memory":
            self.dumps += 1
            if self.fail_dump_at == self.dumps:
                raise OSError("simulated failure before durable snapshot")
            pathlib.Path(payload["dump_file_path"]).write_text(
                "".join(json.dumps(row, sort_keys=True) + "\n" for row in self.stores[base]), encoding="utf-8")
            return {"metadata": {"ok": True}}
        if endpoint == "load_memory":
            self.stores[base] = [json.loads(line) for line in pathlib.Path(payload["load_file_path"]).read_text(encoding="utf-8").splitlines() if line]
            return {"metadata": {"ok": True}}
        raise AssertionError(endpoint)


def _items() -> list[dict]:
    return [{"trajectory_id": f"t-{i}", "task_id": f"task-{i}", "task_history": [], "after_score": 1.0,
             "history_sha256": f"history-{i}"} for i in range(2)]


def test_durable_snapshots_restart_without_repeating_completed_items(tmp_path: pathlib.Path) -> None:
    fake = FakeReMe(); events: list[dict] = []
    checkpoint, snapshots = tmp_path / "construction.jsonl", tmp_path / "snapshots"
    result = construct_durable_snapshot_bank(fake.post, "builder", "verifier", _items(), checkpoint, snapshots, events.append)
    assert result[1] == 2
    assert [row["trajectory_id"] for row in map(json.loads, checkpoint.read_text().splitlines())] == ["t-0", "t-1"]
    fake.calls.clear()
    assert construct_durable_snapshot_bank(fake.post, "builder", "verifier", _items(), checkpoint, snapshots, events.append) == result
    assert fake.calls == ["load_memory"]
    published = tmp_path / "shared-bank.jsonl"
    assert freeze_durable_final_snapshot(snapshots, 2, published) == result[0]
    assert load_clone(fake.post, "fixed", published, result[0]) == result[0]


def test_failure_before_snapshot_creates_intent_and_restart_fails_closed(tmp_path: pathlib.Path) -> None:
    failing = FakeReMe(fail_dump_at=1)
    checkpoint, snapshots = tmp_path / "construction.jsonl", tmp_path / "snapshots"
    with pytest.raises(OSError, match="simulated"):
        construct_durable_snapshot_bank(failing.post, "builder", "verifier", _items(), checkpoint, snapshots, lambda _: None)
    assert not checkpoint.exists()
    with pytest.raises(RuntimeError, match="intent lacks"):
        construct_durable_snapshot_bank(FakeReMe().post, "builder", "verifier", _items(), checkpoint, snapshots, lambda _: None)


def test_snapshot_without_completion_marker_and_corruption_fail_closed(tmp_path: pathlib.Path) -> None:
    fake = FakeReMe(); checkpoint, snapshots = tmp_path / "construction.jsonl", tmp_path / "snapshots"
    construct_durable_snapshot_bank(fake.post, "builder", "verifier", _items(), checkpoint, snapshots, lambda _: None)
    # A metadata/snapshot mismatch cannot be treated as a completed prefix.
    (snapshots / "after-0002.jsonl").write_text("corrupt\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="snapshot metadata mismatch"):
        construct_durable_snapshot_bank(fake.post, "builder", "verifier", _items(), checkpoint, snapshots, lambda _: None)


def test_snapshot_before_completion_marker_fails_closed(tmp_path: pathlib.Path) -> None:
    fake = FakeReMe(); checkpoint, snapshots = tmp_path / "construction.jsonl", tmp_path / "snapshots"
    construct_durable_snapshot_bank(fake.post, "builder", "verifier", _items(), checkpoint, snapshots, lambda _: None)
    checkpoint.write_text(checkpoint.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="intent lacks"):
        construct_durable_snapshot_bank(FakeReMe().post, "builder", "verifier", _items(), checkpoint, snapshots, lambda _: None)


def test_checkpoint_order_mismatch_fails_closed(tmp_path: pathlib.Path) -> None:
    checkpoint, snapshots = tmp_path / "construction.jsonl", tmp_path / "snapshots"
    checkpoint.write_text(json.dumps({"trajectory_id": "t-1", "state": "completed"}) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="checkpoint order mismatch"):
        construct_durable_snapshot_bank(FakeReMe().post, "builder", "verifier", _items(), checkpoint, snapshots, lambda _: None)


def test_unsettled_reservation_blocks_construction_before_provider_work(tmp_path: pathlib.Path) -> None:
    ledger = AppendOnlyLedger(tmp_path / "ledger.jsonl", 100.0, {"executor": 0, "reme_lifecycle": 1, "reme_embedding": 0, "copromem_decomposition": 0})
    ledger.reserve("pending", 0.01, {"role": "reme_lifecycle:test"})
    with pytest.raises(RuntimeError, match="unresolved reservation"):
        _require_settled(ledger)


def test_storage_amendment_uses_5_4_3_thresholds_fail_closed() -> None:
    policy = {"launch_floor_gib": 5.0, "warning_gib": 4.0, "mandatory_stop_gib": 3.0}
    assert capacity_decision(5.0, policy, launch=True) == "ok"
    assert capacity_decision(3.5, policy) == "warning"
    with pytest.raises(RuntimeError, match="launch floor"):
        capacity_decision(4.99, policy, launch=True)
    with pytest.raises(RuntimeError, match="mandatory stop"):
        capacity_decision(2.99, policy)
