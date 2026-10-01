from __future__ import annotations

import importlib.util
from pathlib import Path


def _audit_module():
    path = Path(__file__).parents[2] / "scripts" / "audit_reasoningbank_engineering_006.py"
    spec = importlib.util.spec_from_file_location("engineering_006_audit", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hash_only_query_embedding_is_not_offline_reproducible():
    audit = _audit_module()
    reproducible, reason = audit.retrieval_selection_reproducibility({"query_embedding_sha256": "a" * 64})
    assert reproducible is False
    assert reason == "query_embedding_values_absent; hash_only_cannot_recompute_cosine_top1"


def test_durable_query_embedding_requires_its_canonical_hash():
    audit = _audit_module()
    vector = [0.6, 0.8]
    reproducible, reason = audit.retrieval_selection_reproducibility({
        "query_embedding": vector,
        "query_embedding_sha256": audit.sha256(vector),
    })
    assert reproducible is True
    assert reason == "reproducible"


def test_empty_bank_has_a_reproducible_empty_top1_result():
    audit = _audit_module()
    # No vector is needed to establish that a top-1 selection is empty when
    # the frozen pre-state contains no candidate at all.
    bank = audit.ReasoningBank()
    assert bank.experiences == ()
