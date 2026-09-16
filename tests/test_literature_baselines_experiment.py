from decimal import Decimal

from copromem.literature_baselines_experiment import (
    _repo_revision,
    extract_code,
    safe_execute_arithmetic,
)


def test_restricted_arithmetic_execution() -> None:
    prediction, report = safe_execute_arithmetic("a = 12\nb = 3\nanswer = a / b")
    assert prediction == Decimal("4.0")
    assert report.startswith("Done")


def test_restricted_execution_rejects_unsafe_code() -> None:
    prediction, report = safe_execute_arithmetic("import os\nanswer = 1")
    assert prediction is None
    assert "only single-target assignments" in report


def test_extracts_fenced_code() -> None:
    assert extract_code("```python\nanswer = 7\n```") == "answer = 7"


def test_empty_vendor_directory_cannot_report_parent_commit(tmp_path) -> None:
    directory = tmp_path / "empty_vendor"
    directory.mkdir()
    assert _repo_revision(directory) is None


def test_vendor_revision_checks_repository_root(tmp_path, monkeypatch) -> None:
    directory = tmp_path / "vendor"
    directory.mkdir()
    (directory / ".git").write_text("gitdir: example", encoding="utf-8")
    monkeypatch.setattr(
        "subprocess.check_output", lambda *args, **kwargs: str(tmp_path)
    )
    assert _repo_revision(directory) is None


def test_legacy_cli_requires_explicit_opt_in_before_credentials_or_network(
    monkeypatch, tmp_path
):
    import sys

    import pytest

    from copromem import literature_baselines_experiment as module

    monkeypatch.setattr(sys, "argv", ["legacy", "--output", str(tmp_path / "new.json")])

    def forbidden(*args, **kwargs):
        raise AssertionError("must reject before reading credentials or data")

    monkeypatch.setattr(module, "load_env", forbidden)
    monkeypatch.setattr(module, "fetch_split", forbidden)
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2
