from __future__ import annotations

import json

from copromem.integrations.reasoning_bank.appworld import ReasoningBank, build_experience
from copromem.integrations.reasoning_bank.checkpoints import ReasoningBankDynamicCheckpoints
from copromem.integrations.reasoning_bank.dynamic_runtime import ReasoningBankDynamicRuntime
from copromem.integrations.reasoning_bank.lifecycle import ReasoningBankLifecycle


def _lifecycle(bank):
    return ReasoningBankLifecycle(
        bank=bank, embedder=lambda *_: [1.0, 0.0],
        judge=lambda *_: ("success", {"label": "success"}),
        extractor=lambda *_: ("# Memory Item 1\n## Title T\n## Description D\n## Content C", {"id": "e"}),
    )


def test_retrieval_is_durable_and_nonmutating_before_dispatch(tmp_path):
    existing = build_experience(task_id="old", query="old", trajectory=[], status="success",
                                judge_record={"label": "success"},
                                extraction_text="# Memory Item 1\n## Title T\n## Description D\n## Content C",
                                query_embedding=[1.0, 0.0])
    bank = ReasoningBank([existing])
    initial = ReasoningBank.restore(bank.state())
    manager = ReasoningBankDynamicCheckpoints(root=tmp_path / "checkpoints", expected_trajectory_ids=["x"],
                                               ledger_path=tmp_path / "ledger.jsonl")
    runtime = ReasoningBankDynamicRuntime(lifecycle=_lifecycle(bank), initial_bank=initial,
                                          checkpoints=manager, run_root=tmp_path, registry_sha256="registry")
    before = bank.state()["semantic_state_sha256"]
    callback = runtime.retrieval_callback(tmp_path / "retrieval.json")
    rendered = callback("new public instruction", "appworld", {})
    row = json.loads((tmp_path / "retrieval.json").read_text(encoding="utf-8"))
    assert rendered and row["guidance_nonempty"] is True
    assert row["bank_pre_state_sha256"] == before
    assert bank.state()["semantic_state_sha256"] == before
    copy = dict(row); checksum = copy.pop("record_sha256")
    from copromem.integrations.reasoning_bank.appworld import sha256
    assert checksum == sha256(copy)
