from pathlib import Path
import json
import pytest

from copromem.checkpoints import RunStore
from copromem.exploratory_successor_ledger import ExploratorySuccessorLedger
from copromem.providers import BudgetExceeded


def _historical(root: Path) -> Path:
    (root / "reservations").mkdir(parents=True)
    (root / "reservations" / "one.json").write_text(json.dumps({"reserved_usd": 0.01}))
    return root


def test_exploratory_ledger_preserves_cumulative_dispatch_ceiling(tmp_path):
    ledger = ExploratorySuccessorLedger(
        RunStore(tmp_path / "new"), historical_roots=[_historical(tmp_path / "old")],
        expected_historical_attempts=1, expected_historical_exposure=0.01,
        max_new_attempts=2, max_new_reserved_usd=0.02, max_usd=0.04,
    )
    ledger.reserve("a", 0.01, {})
    ledger.settle("a", 0.0001)
    ledger.reserve("b", 0.01, {})
    with pytest.raises(BudgetExceeded, match="attempt ceiling"):
        ledger.reserve("c", 0.0001, {})
    assert ledger.reserved_new_total == 0.02
