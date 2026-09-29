from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_v62_decision_record_keeps_official_reme_sequential_and_v6_core_distinct():
    record = json.loads((ROOT / "research/reme_copromem_fixed_dynamic_review/v62-protocol-decisions.json").read_text())
    assert record["reme_dynamic"]["official_upstream_semantics"] == "sequential_online_per_trajectory"
    assert record["reme_dynamic"]["within_task_independence_claim"] is False
    assert record["copromem"]["v5"] != record["copromem"]["v6_2"]
    assert record["structured_guidance"]["is_v6_2_repair"] is False
