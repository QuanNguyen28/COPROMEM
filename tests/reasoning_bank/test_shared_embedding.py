from __future__ import annotations

from types import SimpleNamespace

from copromem.integrations.reasoning_bank import shared_embedding


def test_shared_embedding_reuses_locked_azure_transport(monkeypatch, tmp_path):
    captured = {}

    class FakeLockedEmbeddings:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def create(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(data=[SimpleNamespace(embedding=[1.0] * 1024)])

    monkeypatch.setattr(shared_embedding, "LockedEmbeddings", FakeLockedEmbeddings)
    result = shared_embedding.SharedAzureOpenRouterEmbedder(
        api_key="test", ledger=object(), progress=tmp_path / "progress.jsonl"
    )("query", "RETRIEVAL_QUERY")
    assert len(result) == 1024
    assert captured["role"] == "reasoningbank_embedding"
    assert captured["allowed_model"] == "openai/text-embedding-3-small"
    assert captured["provider"] == captured["provider_only"] == "azure"
    assert captured["request"] == {
        "model": "openai/text-embedding-3-small", "input": "query",
        "dimensions": 1024, "encoding_format": "float",
    }
