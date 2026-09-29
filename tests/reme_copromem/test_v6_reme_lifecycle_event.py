from pathlib import Path


def test_upstream_reme_event_is_written_once_without_event_keyword_collision(monkeypatch, tmp_path: Path):
    from scripts import run_v6_shared_acquisition as runner
    captured = []
    monkeypatch.setattr(runner, "_event", lambda run, event, **fields: captured.append((run, event, fields)))
    record = {"event": "reme_initial_bank_item", "trajectory_id": "fixture::seed=1::trajectory=0", "memory_count": 2}
    runner._emit_reme_lifecycle(tmp_path, record)
    assert captured == [(tmp_path, "reme_lifecycle", {"upstream_event": "reme_initial_bank_item", "trajectory_id": "fixture::seed=1::trajectory=0", "memory_count": 2})]
    assert record["event"] == "reme_initial_bank_item"
