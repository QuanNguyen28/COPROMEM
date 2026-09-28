from __future__ import annotations

import json

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
