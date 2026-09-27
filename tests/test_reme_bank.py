from __future__ import annotations

import pathlib
import json

from research.official_pilot.reme_bank import construct_once, load_clone
from scripts.run_fixed_dynamic_v4 import progress_event_callback


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


def test_v4_progress_callback_is_unary_and_persisted_restart_skips_provider_work(tmp_path: pathlib.Path) -> None:
    progress = tmp_path / "progress.jsonl"
    callback = progress_event_callback(progress)
    callback({"event": "reme_initial_bank_item", "trajectory_id": "a"})
    assert json.loads(progress.read_text(encoding="utf-8")) == {"event": "reme_initial_bank_item", "trajectory_id": "a"}
    dump = tmp_path / "snapshot.jsonl"
    dump.write_text('{"memory_id":"m","content":"x"}\n', encoding="utf-8")
    checkpoint = tmp_path / "construction.jsonl"
    checkpoint.write_text('{"trajectory_id":"a","state":"persisted"}\n', encoding="utf-8")
    provider_calls: list[str] = []
    result, count = construct_once(lambda _base, endpoint, _payload: provider_calls.append(endpoint) or {}, "builder",
                                   [{"trajectory_id":"a", "task_id":"a", "task_history":[], "after_score":1.0}],
                                   checkpoint, dump, callback)
    assert count == 1 and provider_calls == []
    assert result
