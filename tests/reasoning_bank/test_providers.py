from __future__ import annotations

from types import SimpleNamespace

from copromem.integrations.reasoning_bank import providers
from copromem.integrations.reasoning_bank.appworld import SUCCESSFUL_EXTRACTION_PROMPT


class _Completion:
    def __init__(self, text: str, role: str) -> None:
        self.last_record = {"id": role + "-id", "role": role}
        self.text = text

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.text))])


class _Client:
    created: list["_Client"] = []
    def __init__(self, *, role: str, **_kwargs) -> None:
        self.role = role
        text = "success" if role == providers.JUDGE_ROLE else "# Memory Item 1\n## Title T\n## Description D\n## Content C"
        self.chat = SimpleNamespace(completions=_Completion(text, role))
        self.created.append(self)


def test_provider_roles_temperatures_and_extraction_prompt_are_frozen(monkeypatch, tmp_path):
    _Client.created.clear()
    monkeypatch.setattr(providers, "LockedOpenAI", _Client)
    client = providers.ReasoningBankProviders(api_key="not-used", ledger=object(), progress=tmp_path / "progress.jsonl")
    status, judge = client.judge("q", [{"role": "user", "content": "public"}], 0.0)
    extraction, extracted = client.extract(SUCCESSFUL_EXTRACTION_PROMPT, "q", [], 1.0)
    assert status == "success"
    assert extraction.startswith("# Memory Item")
    assert [item.role for item in _Client.created] == [providers.JUDGE_ROLE, providers.EXTRACTION_ROLE]
    assert _Client.created[0].chat.completions.kwargs["temperature"] == 0.0
    assert _Client.created[1].chat.completions.kwargs["temperature"] == 1.0
    assert _Client.created[1].chat.completions.kwargs["messages"][0]["content"] == SUCCESSFUL_EXTRACTION_PROMPT
    assert judge["label"] == "success" and "response_sha256" in extracted


def test_provider_rejects_wrong_frozen_temperatures(monkeypatch, tmp_path):
    monkeypatch.setattr(providers, "LockedOpenAI", _Client)
    client = providers.ReasoningBankProviders(api_key="not-used", ledger=object(), progress=tmp_path / "p")
    import pytest
    with pytest.raises(ValueError):
        client.judge("q", [], 0.1)
    with pytest.raises(ValueError):
        client.extract("system", "q", [], 0.0)
