import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from copromem import appworld_preflight


def test_native_failure_is_recorded_by_unmodified_parent(monkeypatch, tmp_path):
    monkeypatch.setattr(
        sys, "argv", ["probe", "--root", str(tmp_path), "--run-id", "failure-test"]
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "SENSITIVE_TEST_KEY")

    def failed(command, **kwargs):
        assert "OPENROUTER_API_KEY" not in kwargs["env"]
        assert kwargs["env"]["PYTHON_DOTENV_DISABLED"] == "1"
        return SimpleNamespace(
            returncode=1, stdout="native failed", stderr="SIGALRM unavailable"
        )

    monkeypatch.setattr(subprocess, "run", failed)
    with pytest.raises(SystemExit):
        appworld_preflight.main()
    path = tmp_path / "preflight_records/supervisor/failure-test.json"
    assert json.loads(path.read_text())["exit_code"] == 1
    assert "SENSITIVE_TEST_KEY" not in path.read_text()


def test_native_timeout_does_not_erase_supervisor_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(
        sys, "argv", ["probe", "--root", str(tmp_path), "--run-id", "timeout-test"]
    )

    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(SystemExit):
        appworld_preflight.main()
    path = tmp_path / "preflight_records/supervisor/timeout-test.json"
    assert json.loads(path.read_text())["error_type"] == "TimeoutExpired"


def test_clock_errors_cannot_pass_as_matching_timestamps():
    world = SimpleNamespace(execute=lambda code: "Execution failed. AttributeError")
    with pytest.raises(ValueError):
        appworld_preflight.read_clock(world)


def test_clock_requires_valid_native_datetime():
    def execute(code):
        assert code == "print(datetime.datetime.now().isoformat())"
        return "2023-05-18T12:04:00\n"

    assert (
        appworld_preflight.read_clock(SimpleNamespace(execute=execute))
        == "2023-05-18T12:04:00"
    )
