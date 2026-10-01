from __future__ import annotations

import json
import shlex
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DETACHED = ROOT / "scripts" / "launch_reasoningbank_appworld_engineering_detached_wsl.sh"
PRODUCTION_PYTHON = "/home/xiqhq/copromem-appworld/venv/bin/python"
AGENT_ROOT = "/home/xiqhq/copromem-reme/benchmark/appworld"


def _wsl(path: Path) -> str:
    windows = path.resolve().as_posix()
    assert windows[1:3] == ":/"
    return f"/mnt/{windows[0].lower()}{windows[2:]}"


def _wait_terminal(stage: Path) -> dict:
    terminal = stage / "child-terminal.json"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if terminal.is_file():
            return json.loads(terminal.read_text(encoding="utf-8"))
        time.sleep(0.05)
    raise AssertionError("detached child did not write an atomic terminal record")


def _launch(tmp_path: Path, body: str) -> tuple[Path, subprocess.CompletedProcess[str]]:
    probe = tmp_path / "probe-run"; stage = probe / "launcher-stages"
    protected = tmp_path / "protected.env"
    protected.write_text("export OPENROUTER_API_KEY=synthetic_fixture_value\n", encoding="utf-8")
    child = tmp_path / "child.sh"
    child.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body, encoding="utf-8", newline="\n")
    runtime = _wsl(ROOT)
    shell = (f"REASONINGBANK_PROTECTED_ENV_FILE={shlex.quote(_wsl(protected))} "
             f"PYTHONPATH={shlex.quote(runtime + ':' + runtime + '/src:' + AGENT_ROOT)} "
             f"exec {shlex.quote(_wsl(DETACHED))} --run {shlex.quote(_wsl(probe))} "
             f"--stage-dir {shlex.quote(_wsl(stage))} --python {shlex.quote(PRODUCTION_PYTHON)} "
             f"--runtime-root {shlex.quote(runtime)} --agent-root {shlex.quote(AGENT_ROOT)} "
             f"-- bash {shlex.quote(_wsl(child))}")
    result = subprocess.run(["wsl.exe", "bash", "-lc", shell], text=True, capture_output=True, check=False)
    return probe, result


def test_detached_wrapper_propagates_credential_survives_parent_and_captures_streams(tmp_path: Path):
    marker = _wsl(tmp_path / "credential-marker")
    probe, result = _launch(tmp_path, "\n".join([
        f'test -n "${{OPENROUTER_API_KEY:-}}" && printf present > {shlex.quote(marker)}',
        "printf detached-stdout",
        "printf detached-stderr >&2",
        "sleep 0.2",
    ]) + "\n")
    assert result.returncode == 0
    terminal = _wait_terminal(probe / "launcher-stages")
    assert terminal["stage"] == "child-exited" and terminal["exit_code"] == 0
    assert (tmp_path / "credential-marker").read_text(encoding="utf-8") == "present"
    assert (probe / "launcher-stages" / "child-started.json").is_file()
    assert json.loads((probe / "launcher-stages" / "python-dependency-gate.json").read_text(encoding="utf-8"))["stage"] == "python-dependency-gate-passed"
    assert (probe / "runner.stdout.log").read_text(encoding="utf-8") == "detached-stdout"
    assert (probe / "runner.stderr.log").read_text(encoding="utf-8") == "detached-stderr"
    assert "synthetic_fixture_value" not in result.stdout + result.stderr


def test_detached_wrapper_records_pre_python_failure_and_exit_code(tmp_path: Path):
    probe, result = _launch(tmp_path, "exit 17\n")
    assert result.returncode == 0
    terminal = _wait_terminal(probe / "launcher-stages")
    assert terminal["exit_code"] == 17
    assert (probe / "runner.stdout.log").is_file() and (probe / "runner.stderr.log").is_file()


def test_detached_wrapper_records_python_import_failure_without_false_runner_status(tmp_path: Path):
    probe, result = _launch(tmp_path, "python3 -c 'import copromem_missing_fixture_module'\n")
    assert result.returncode == 0
    terminal = _wait_terminal(probe / "launcher-stages")
    assert terminal["exit_code"] != 0
    assert "ModuleNotFoundError" in (probe / "runner.stderr.log").read_text(encoding="utf-8")
    assert not (probe / "runner-status.json").exists()


def test_detached_wrapper_child_can_acknowledge_repository_import_and_entrypoint_parsing(tmp_path: Path):
    runtime = _wsl(ROOT)
    probe, result = _launch(tmp_path, "\n".join([
        f"PYTHONPATH={shlex.quote(runtime + ':' + runtime + '/src')} python3 -c 'import copromem; print(\"repository-import\")'",
        f'python3 {shlex.quote(runtime + "/scripts/run_reasoningbank_appworld_engineering.py")} --help >/dev/null',
    ]) + "\n")
    assert result.returncode == 0
    terminal = _wait_terminal(probe / "launcher-stages")
    assert terminal["exit_code"] == 0
    assert "repository-import" in (probe / "runner.stdout.log").read_text(encoding="utf-8")


def test_detached_and_foreground_use_the_same_explicit_appworld_python(tmp_path: Path):
    foreground = subprocess.run(["wsl.exe", "--", PRODUCTION_PYTHON, "-c", "import sys; print(sys.executable)"],
                                text=True, capture_output=True, check=True).stdout.strip()
    marker = _wsl(tmp_path / "python-executable")
    probe, result = _launch(tmp_path, f"{shlex.quote(PRODUCTION_PYTHON)} -c 'import sys; print(sys.executable)' > {shlex.quote(marker)}\n")
    assert result.returncode == 0
    assert _wait_terminal(probe / "launcher-stages")["exit_code"] == 0
    assert (tmp_path / "python-executable").read_text(encoding="utf-8").strip() == foreground
