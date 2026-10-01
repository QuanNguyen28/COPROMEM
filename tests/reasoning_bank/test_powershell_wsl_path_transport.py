from __future__ import annotations

import base64
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "scripts" / "launch_reasoningbank_appworld_engineering_detached.ps1"
RUNTIME = Path(r"C:\Users\xiqhq\.codex\worktrees\reasoningbank-appworld\COPROMEM-runtime-e44564e9")


def _powershell_wslpath(*paths: str) -> list[str]:
    values = ", ".join("'" + path.replace("'", "''") + "'" for path in paths)
    source = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        "$PSNativeCommandArgumentPassing = 'Standard'",
        "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)",
        "$OutputEncoding = [Console]::OutputEncoding",
        f"$paths = @({values})",
        "foreach ($path in $paths) {",
        "  $env:COPROMEM_WSL_TRANSPORT_PATH = $path",
        "  $env:WSLENV = 'COPROMEM_WSL_TRANSPORT_PATH/p'",
        "  $result = @(& wsl.exe -d Ubuntu -- /bin/sh -c 'test -e \"$COPROMEM_WSL_TRANSPORT_PATH\" && printf \"%s\\n\" \"$COPROMEM_WSL_TRANSPORT_PATH\"')",
        "  if ($LASTEXITCODE -ne 0 -or $result.Count -ne 1) { throw 'wslpath failed' }",
        "  [Console]::WriteLine($result[0].Trim())",
        "}",
    ])
    encoded = base64.b64encode(source.encode("utf-16le")).decode("ascii")
    result = subprocess.run(["pwsh", "-NoProfile", "-EncodedCommand", encoded], text=True, encoding="utf-8", capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


def test_powershell_direct_argv_preserves_real_runtime_path():
    assert _powershell_wslpath(str(RUNTIME)) == [
        "/mnt/c/Users/xiqhq/.codex/worktrees/reasoningbank-appworld/COPROMEM-runtime-e44564e9"
    ]


def test_powershell_direct_argv_preserves_spaces_parentheses_apostrophes_and_unicode(tmp_path: Path):
    target = tmp_path / "fixture path" / "(parentheses)" / "O'Brien Δ"
    target.mkdir(parents=True)
    converted = _powershell_wslpath(str(target))
    windows = target.resolve().as_posix()
    assert converted == [f"/mnt/{windows[0].lower()}{windows[2:]}"]


def test_powershell_launcher_uses_wslenv_path_transport_and_fail_closed_checks():
    source = LAUNCHER.read_text(encoding="utf-8")
    assert "$PSNativeCommandArgumentPassing = 'Standard'" in source
    assert 'COPROMEM_WSL_TRANSPORT_PATH' in source
    assert '"$name/p"' in source
    assert "test -e \"$COPROMEM_WSL_TRANSPORT_PATH\"" in source
    assert "/bin/sh -c" in source
    assert "WSLENV path conversion failed" in source
    assert "bash -lc" not in source
