from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_final_predispatch_audit_fails_closed_on_unwired_runtime_and_terminal_gates():
    audit = json.loads((ROOT / "research/reme_copromem_fixed_dynamic_review/v62-final-predispatch-audit.json").read_text())
    assert audit["terminal_classification"] == "NO-GO"
    assert audit["gates"]["runtime_identity_production_integration"] == "fail"
    assert audit["gates"]["terminal_reconciliation_production_integration"] == "fail"
    assert audit["evaluation_007"]["immutable"] is True
    assert audit["paid_or_benchmark_activity"] is False
