from __future__ import annotations

import json

from copromem.integrations.reasoning_bank.appworld import MEMORY_PROMPT, ReasoningBank, build_experience, sha256
from copromem.integrations.reasoning_bank.checkpoints import ReasoningBankDynamicCheckpoints
from copromem.integrations.reasoning_bank.dynamic_runtime import ReasoningBankDynamicRuntime
from copromem.integrations.reasoning_bank.lifecycle import ReasoningBankLifecycle


IDENTITY = {
    "trajectory_id": "evaluation:reasoningbank_dynamic:x:trial=1:seed=1",
    "task_id": "x", "arm": "reasoningbank_dynamic", "trial_id": 1, "seed": 1,
    "benchmark": "appworld", "manifest_sha256": "a" * 64,
    "runtime_identity_sha256": "b" * 64, "registry_sha256": "c" * 64,
}


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
                                          checkpoints=manager, run_root=tmp_path, registry_sha256="c" * 64)
    before = bank.state()["semantic_state_sha256"]
    callback = runtime.retrieval_callback(tmp_path / "retrieval.json", identity=IDENTITY)
    rendered = callback("new public instruction", "appworld", {})
    row = json.loads((tmp_path / "retrieval.json").read_text(encoding="utf-8"))
    assert rendered and row["guidance_nonempty"] is True
    assert rendered.startswith(MEMORY_PROMPT)
    assert row["guidance"]["rendered_sha256"] == sha256(rendered)
    assert row["guidance_sha256"] == sha256(rendered)
    assert row["guidance"]["raw_memory_sha256"] != row["guidance"]["rendered_sha256"]
    assert row["bank_pre_state_sha256"] == before
    assert bank.state()["semantic_state_sha256"] == before
    copy = dict(row); checksum = copy.pop("record_sha256")
    assert checksum == sha256(copy)


def test_callback_is_exact_pinned_lifecycle_rendering_not_raw_memory(tmp_path):
    existing = build_experience(
        task_id="old", query="old", trajectory=[], status="success",
        judge_record={"label": "success"},
        extraction_text="# Memory Item 1\n## Title T\n## Description D\n## Content C",
        query_embedding=[1.0, 0.0],
    )
    direct_bank = ReasoningBank([existing])
    direct = _lifecycle(direct_bank).retrieve_for_instruction("new public instruction", "appworld", {})
    runtime_bank = ReasoningBank([existing])
    manager = ReasoningBankDynamicCheckpoints(
        root=tmp_path / "checkpoints", expected_trajectory_ids=["x"],
        ledger_path=tmp_path / "ledger.jsonl",
    )
    runtime = ReasoningBankDynamicRuntime(
        lifecycle=_lifecycle(runtime_bank), initial_bank=ReasoningBank.restore(runtime_bank.state()),
        checkpoints=manager, run_root=tmp_path, registry_sha256="c" * 64,
    )
    observed = runtime.retrieval_callback(tmp_path / "retrieval.json", identity=IDENTITY)(
        "new public instruction", "appworld", {},
    )
    row = json.loads((tmp_path / "retrieval.json").read_text(encoding="utf-8"))
    raw = runtime.store.load_text(row["guidance"]["raw_memory_bytes"])
    persisted = runtime.store.load_text(row["guidance"]["rendered_bytes"])
    assert raw == existing.memory_items[0]
    assert direct == observed == persisted
    assert observed != raw
    assert row["guidance"]["rendered_sha256"] == sha256(observed)


def test_production_callback_rejects_narrow_identity_before_retrieval(tmp_path):
    bank = ReasoningBank()
    manager = ReasoningBankDynamicCheckpoints(root=tmp_path / "checkpoints", expected_trajectory_ids=["x"],
                                               ledger_path=tmp_path / "ledger.jsonl")
    runtime = ReasoningBankDynamicRuntime(lifecycle=_lifecycle(bank), initial_bank=ReasoningBank.restore(bank.state()),
                                          checkpoints=manager, run_root=tmp_path, registry_sha256="c" * 64)
    try:
        runtime.retrieval_callback(tmp_path / "retrieval.json", identity={"task_id": "x"})
    except RuntimeError as exc:
        assert "before dispatch" in str(exc)
    else:
        raise AssertionError("narrow identity was accepted")
