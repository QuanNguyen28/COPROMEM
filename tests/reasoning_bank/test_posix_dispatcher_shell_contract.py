from __future__ import annotations

import subprocess
from pathlib import Path


RUNTIME = "/mnt/c/Users/xiqhq/.codex/worktrees/reasoningbank-appworld/COPROMEM-runtime-2de91716"
COMMAND = f'COPROMEM_WSL_TRANSPORT_PATH="{RUNTIME}"; export COPROMEM_WSL_TRANSPORT_PATH; test -e "$COPROMEM_WSL_TRANSPORT_PATH" && printf "%s\\n" "$COPROMEM_WSL_TRANSPORT_PATH"'


def _wsl(path: Path) -> str:
    windows = path.resolve().as_posix()
    return f"/mnt/{windows[0].lower()}{windows[2:]}"


def test_dispatcher_posix_command_runs_under_dash_and_bash(tmp_path: Path):
    script = tmp_path / "dispatcher-posix.sh"
    script.write_text(COMMAND + "\n", encoding="utf-8", newline="\n")
    for shell in ("/bin/dash", "/bin/bash"):
        result = subprocess.run(["wsl.exe", "-d", "Ubuntu", "--", shell, _wsl(script)],
                                text=True, capture_output=True, check=False)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == RUNTIME


def test_bash_only_contract_is_confined_to_explicit_bash_scripts():
    paths = [
        "scripts/launch_reasoningbank_appworld_engineering_wsl.sh",
        "scripts/launch_reasoningbank_appworld_engineering_detached_wsl.sh",
        "scripts/reasoningbank_detached_supervisor.sh",
    ]
    for path in paths:
        source = open(path, encoding="utf-8").read()
        assert source.startswith("#!/usr/bin/env bash\n")
