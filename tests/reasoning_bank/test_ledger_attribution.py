from __future__ import annotations

import json

from copromem.experiments.reme_copromem.live_summary import reconcile_ledger


def test_reasoningbank_calls_are_owned_by_dynamic_arm_not_historical(tmp_path):
    path = tmp_path / "ledger.jsonl"
    rows = []
    for call_id, role, usd in [("historical-construction-carry", "historical_carry_forward", 1.0),
                               ("judge", "reasoningbank_judge", .1),
                               ("extract", "reasoningbank_extraction", .2),
                               ("embed", "reasoningbank_embedding", .3)]:
        rows.extend(({"event": "reserve", "id": call_id, "usd": usd, "role": role},
                     {"event": "settle", "id": call_id, "usd": usd, "role": role}))
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    result = reconcile_ledger(path, historical_expected_usd=1.0,
                              registered_arms=["no_memory", "reasoningbank_dynamic"])
    dynamic = [call for call in result.calls if call.arm == "reasoningbank_dynamic"]
    assert [call.kind for call in dynamic] == ["embedding", "lifecycle", "lifecycle"]
    assert float(result.historical_settled_exposure) == 1.0
    assert float(result.settled_evaluation_cost) == .6
