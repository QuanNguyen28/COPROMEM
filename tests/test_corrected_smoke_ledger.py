import json
from pathlib import Path

import pytest

from copromem.checkpoints import RunStore
from copromem.corrected_smoke_ledger import CorrectedSmokeLedger
from copromem.providers import BudgetExceeded


def _root(path: Path, count: int, amount: float) -> Path:
    (path / "reservations").mkdir(parents=True)
    (path / "settlements").mkdir()
    for i in range(count):
        (path / "reservations" / f"{i}.json").write_text(json.dumps({"reserved_usd": amount}))
        (path / "settlements" / f"{i}.json").write_text(json.dumps({"actual_usd": amount}))
    return path


def test_carries_all_prior_records_and_fails_closed(tmp_path):
    # 10 x .003131748 plus 46 x .0007141373913043478 is exactly the recorded total.
    first = _root(tmp_path / "first", 10, .003131748)
    second = _root(tmp_path / "second", 46, (0.06416778 - .03131748) / 46)
    ledger = CorrectedSmokeLedger(RunStore(tmp_path / "corrected"), historical_roots=[first, second], max_new_attempts=1)
    assert ledger.attempts_used == 56
    ledger.reserve("one", .006, {"role": "executor"})
    with pytest.raises(BudgetExceeded):
        ledger.reserve("two", .006, {"role": "executor"})
