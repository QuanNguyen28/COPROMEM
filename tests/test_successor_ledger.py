import json
from pathlib import Path

import pytest

from copromem.checkpoints import RunStore
from copromem.providers import BudgetExceeded
from copromem.successor_ledger import SuccessorLedger


def parent(root: Path):
    for i in range(10):
        (root / "reservations").mkdir(parents=True, exist_ok=True)
        (root / "reservations" / f"{i}.json").write_text(json.dumps({"reserved_usd": 0.003131748}))
    return root


def test_successor_carries_parent_immutably_and_counts_attempts(tmp_path):
    source = parent(tmp_path / "parent")
    ledger = SuccessorLedger(RunStore(tmp_path / "next"), parent_root=source)
    assert ledger.attempts_used == 10 and ledger.charged_or_reserved == pytest.approx(0.03131748)
    ledger.reserve("new", 0.01, {"role": "fixture"})
    assert ledger.attempts_used == 11
    assert (source / "reservations" / "0.json").exists()


def test_successor_fails_closed_on_attempt_and_dollar_limits(tmp_path):
    ledger = SuccessorLedger(RunStore(tmp_path / "next"), parent_root=parent(tmp_path / "parent"))
    for i in range(78):
        ledger.reserve(f"k{i}", 0.0, {"role": "fixture"})
    with pytest.raises(BudgetExceeded):
        ledger.reserve("overflow", 0.0, {"role": "fixture"})
