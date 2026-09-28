from __future__ import annotations

import json
import pathlib

import pytest

from copromem.integrations.reme.bank import construct_once, load_clone
from copromem.experiments.reme_copromem.config import progress_event_callback


def test_reme_initial_bank_uses_pinned_legacy_summary_add_dump_load_contract(tmp_path: pathlib.Path) -> None:
    calls: list[tuple[str, str, dict]] = []
    dumped = '{"memory_id":"m","content":"x"}\n'

    def post(base: str, endpoint: str, payload: dict) -> dict:
        calls.append((base, endpoint, payload))
        if endpoint == "summary_task_memory":
            return {"metadata": {"memory_list": [{"memory_id": "m", "content": "x"}]}}
        if endpoint == "dump_memory":
            pathlib.Path(payload["dump_file_path"]).write_text(dumped, encoding="utf-8")
            return {"metadata": {"dumped_count": 1}}
        return {"metadata": {"ok": True}}

    rows = [
        {"trajectory_id": "a::seed=1::trajectory=0", "task_id": "a", "task_history": [], "after_score": 1.0},
        {"trajectory_id": "b::seed=1::trajectory=0", "task_id": "b", "task_history": [], "after_score": 0.0},
    ]
    checkpoint, dump = tmp_path / "construction.jsonl", tmp_path / "snapshot.jsonl"
    events: list[dict] = []
    snapshot, count = construct_once(post, "builder", rows, checkpoint, dump, events.append)
    assert count == 2
    assert [endpoint for _, endpoint, _ in calls].count("summary_task_memory") == 2
    assert [endpoint for _, endpoint, _ in calls].count("add_task_memory") == 2
    construct_once(post, "builder", rows, checkpoint, dump, events.append)
    assert [endpoint for _, endpoint, _ in calls].count("summary_task_memory") == 2
    assert load_clone(post, "fixed", dump, snapshot) == snapshot
    assert load_clone(post, "dynamic", dump, snapshot) == snapshot


def test_progress_callback_is_unary_and_persisted_restart_skips_provider_work(tmp_path: pathlib.Path) -> None:
    progress = tmp_path / "progress.jsonl"
    callback = progress_event_callback(progress)
    callback({"event": "reme_initial_bank_item", "trajectory_id": "a"})
    assert json.loads(progress.read_text(encoding="utf-8")) == {"event": "reme_initial_bank_item", "trajectory_id": "a"}
    dump, checkpoint = tmp_path / "snapshot.jsonl", tmp_path / "construction.jsonl"
    provider_calls: list[str] = []
    def post(_base, endpoint, payload):
        provider_calls.append(endpoint)
        if endpoint == "summary_task_memory": return {"metadata": {"memory_list": []}}
        if endpoint == "dump_memory":
            pathlib.Path(payload["dump_file_path"]).write_text("", encoding="utf-8")
        return {"metadata": {"ok": True}}
    rows = [{"trajectory_id":"a", "task_id":"a", "task_history":[], "after_score":1.0}]
    construct_once(post, "builder", rows, checkpoint, dump, callback)
    provider_calls.clear()
    result, count = construct_once(post, "builder", rows, checkpoint, dump, callback)
    assert count == 1 and provider_calls == []
    assert result


def test_incomplete_reme_dump_cannot_be_loaded_as_complete(tmp_path: pathlib.Path) -> None:
    dump = tmp_path / "partial.jsonl"
    dump.write_text('{"memory_id":"m","content":"x"}\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="completion marker is absent"):
        load_clone(lambda *_: {}, "fixed", dump, "anything")
