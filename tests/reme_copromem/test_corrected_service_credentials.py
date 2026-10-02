import pytest

from copromem.integrations.reme import corrected_service


def test_service_accepts_wrapper_inherited_credential_without_runtime_env_file(tmp_path, monkeypatch):
    """A clean detached runtime must not need to copy the protected secret."""
    monkeypatch.setattr(corrected_service, "ROOT", tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "fixture-process-only")
    assert corrected_service.load_env() == {"OPENROUTER_API_KEY": "fixture-process-only"}


def test_service_uses_legacy_locked_env_file_only_when_process_has_no_key(tmp_path, monkeypatch):
    monkeypatch.setattr(corrected_service, "ROOT", tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=fixture-file-only\nOTHER=value\n", encoding="utf-8")
    assert corrected_service.load_env()["OPENROUTER_API_KEY"] == "fixture-file-only"


def test_service_fails_closed_when_no_wrapper_or_legacy_credential_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(corrected_service, "ROOT", tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="credential file is absent"):
        corrected_service.load_env()
