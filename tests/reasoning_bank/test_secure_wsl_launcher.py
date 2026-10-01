from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "scripts" / "launch_reasoningbank_appworld_engineering_wsl.sh"


def test_wsl_launchers_are_frozen_with_lf_checkout_semantics():
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.sh text eol=lf" in attributes


def _wsl(path: Path) -> str:
    windows = path.resolve().as_posix()
    assert windows[1:3] == ":/"
    return f"/mnt/{windows[0].lower()}{windows[2:]}"


def _run(child: Path, *, env_file: Path | None, source_override: str | None = None) -> subprocess.CompletedProcess[str]:
    # The launch boundary is WSL-only.  Git-for-Windows Bash cannot verify the
    # WSL process environment or `exec` inheritance contract.
    env_value = source_override if source_override is not None else (_wsl(env_file) if env_file is not None else "")
    shell = (f"REASONINGBANK_PROTECTED_ENV_FILE={shlex.quote(env_value)} "
             f"exec {shlex.quote(_wsl(LAUNCHER))} bash {shlex.quote(_wsl(child))}")
    return subprocess.run(["wsl.exe", "bash", "-lc", shell], text=True, capture_output=True, check=False)


def _child(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "child.sh"
    path.write_text(source, encoding="utf-8")
    return path


def test_protected_source_is_exported_to_the_execed_runner_without_echoing_it(tmp_path: Path):
    protected = tmp_path / "protected.env"
    protected.write_text("OPENROUTER_API_KEY=synthetic_fixture_value\n", encoding="utf-8")
    result = _run(_child(tmp_path, 'test -n "${OPENROUTER_API_KEY:-}" && printf PRESENT\n'), env_file=protected)
    assert result.returncode == 0
    assert result.stdout.strip() == "PRESENT"
    assert "synthetic_fixture_value" not in result.stdout + result.stderr


def test_missing_or_nonabsolute_protected_source_fails_before_child_execution(tmp_path: Path):
    child = _child(tmp_path, "exit 99\n")
    missing = _run(child, env_file=None)
    assert missing.returncode == 41
    relative = tmp_path / "relative.env"
    relative.write_text("OPENROUTER_API_KEY=fixture\n", encoding="utf-8")
    result = _run(child, env_file=None, source_override=relative.name)
    assert result.returncode == 41


def test_missing_key_in_protected_source_fails_before_child_execution(tmp_path: Path):
    protected = tmp_path / "protected.env"
    protected.write_text("UNRELATED=value\n", encoding="utf-8")
    result = _run(_child(tmp_path, "exit 99\n"), env_file=protected)
    assert result.returncode == 41
