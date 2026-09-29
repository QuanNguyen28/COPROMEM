import json

import pytest

from copromem.integrations.reme.bank import construct_once


def test_partial_persisted_checkpoint_without_snapshot_fails_before_provider_dispatch(tmp_path):
    checkpoint = tmp_path / "construction.jsonl"
    checkpoint.write_text(json.dumps({"trajectory_id": "t", "task_id": "task", "state": "persisted"}) + "\n", encoding="utf-8")
    called = []
    with pytest.raises(RuntimeError, match="lacks a durable shared-bank snapshot"):
        construct_once(lambda *_: called.append(True), "http://unused", [{"trajectory_id": "t", "task_id": "task", "task_history": [], "after_score": 1.0}], checkpoint, tmp_path / "bank.jsonl", lambda _: None)
    assert not called
