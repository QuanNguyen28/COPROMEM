from __future__ import annotations

import json
import pathlib

import pytest

from copromem.integrations.reme.transport import AppendOnlyLedger, DispatchFailure


def test_append_only_ledger_rejects_duplicate_and_over_reservation(tmp_path):
    ledger = AppendOnlyLedger(tmp_path / "ledger.jsonl", 1.0)
    ledger.reserve("call-a", 0.60, {"role": "executor"})
    with pytest.raises(DispatchFailure, match="duplicate"):
        ledger.reserve("call-a", 0.01, {"role": "executor"})
    with pytest.raises(DispatchFailure, match="cap"):
        ledger.reserve("call-b", 0.41, {"role": "executor"})
    ledger.settle("call-a", 0.20, {"role": "executor"})
    ledger.reserve("call-b", 0.80, {"role": "executor"})
    rows = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert [row["event"] for row in rows] == ["reserve", "settle", "reserve"]


def test_append_only_ledger_rejects_double_or_unbounded_settlement(tmp_path):
    ledger = AppendOnlyLedger(tmp_path / "ledger.jsonl", 1.0)
    ledger.reserve("call-a", 0.50, {"role": "executor"})
    with pytest.raises(DispatchFailure, match="exceeds"):
        ledger.settle("call-a", 0.51, {"role": "executor"})
    with pytest.raises(DispatchFailure, match="unknown"):
        ledger.settle("missing", 0.01, {"role": "executor"})
    ledger.settle("call-a", 0.49, {"role": "executor"})
    with pytest.raises(DispatchFailure, match="unknown"):
        ledger.settle("call-a", 0.49, {"role": "executor"})


def test_registered_role_call_limits_are_fail_closed(tmp_path):
    ledger = AppendOnlyLedger(tmp_path / "ledger.jsonl", 1.0,
                              {"executor": 1, "reme_lifecycle": 0,
                               "reme_embedding": 0, "copromem_decomposition": 0})
    ledger.reserve("first", 0.10, {"role": "executor:no_memory:a:trial=0:seed=1"})
    with pytest.raises(DispatchFailure, match="executor call limit"):
        ledger.reserve("second", 0.10, {"role": "executor:no_memory:a:trial=1:seed=2"})
    with pytest.raises(DispatchFailure, match="unregistered"):
        ledger.reserve("other", 0.10, {"role": "unknown"})


def test_usd_100_engineering_cap_rejects_exposure_before_dispatch(tmp_path):
    ledger = AppendOnlyLedger(tmp_path / "ledger.jsonl", 100.0,
                              {"executor": 720, "reme_lifecycle": 512,
                               "reme_embedding": 4096, "copromem_decomposition": 0})
    ledger.reserve("first", 99.99, {"role": "executor:no_memory:a:trial=0:seed=1"})
    with pytest.raises(DispatchFailure, match="USD cap"):
        ledger.reserve("over-cap", 0.02, {"role": "executor:no_memory:a:trial=1:seed=2"})


def test_append_retries_transient_drvfs_permission_error_without_duplicate(tmp_path, monkeypatch):
    ledger_path = tmp_path / "ledger.jsonl"
    ledger = AppendOnlyLedger(ledger_path, 1.0)
    original_open = pathlib.Path.open
    attempts = {"append": 0}

    def flaky_open(path, mode="r", *args, **kwargs):
        if path == ledger_path and mode == "a" and attempts["append"] == 0:
            attempts["append"] += 1
            raise PermissionError(13, "simulated drvfs sharing violation")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "open", flaky_open)
    ledger.reserve("call-a", 0.20, {"role": "executor:no_memory:a:trial=1:seed=1"})
    ledger.settle("call-a", 0.10, {"role": "executor:no_memory:a:trial=1:seed=1"})
    rows = [json.loads(line) for line in ledger_path.read_text().splitlines()]
    assert attempts["append"] == 1
    assert [(row["event"], row["id"]) for row in rows] == [("reserve", "call-a"), ("settle", "call-a")]


def test_append_retry_recognizes_durable_row_after_post_write_failure(tmp_path, monkeypatch):
    ledger_path = tmp_path / "ledger.jsonl"
    ledger = AppendOnlyLedger(ledger_path, 1.0)
    original_fsync = __import__("os").fsync
    calls = {"n": 0}

    def post_write_failure(fd):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError(13, "simulated fsync ambiguity")
        return original_fsync(fd)

    monkeypatch.setattr("copromem.integrations.reme.transport.os.fsync", post_write_failure)
    ledger.reserve("call-a", 0.20, {"role": "executor:no_memory:a:trial=1:seed=1"})
    rows = [json.loads(line) for line in ledger_path.read_text().splitlines()]
    assert rows == [{"event": "reserve", "id": "call-a", "usd": 0.20, "role": "executor:no_memory:a:trial=1:seed=1"}]
