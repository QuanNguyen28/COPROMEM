from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "check_reasoningbank_appworld_runtime.py"
PRODUCTION_PYTHON = "/home/xiqhq/copromem-appworld/venv/bin/python"
AGENT_ROOT = "/home/xiqhq/copromem-reme/benchmark/appworld"


def _wsl(path: Path) -> str:
    text = path.resolve().as_posix()
    assert text[1:3] == ":/"
    return f"/mnt/{text[0].lower()}{text[2:]}"


def _gate(tmp_path: Path, python: str, expected: str) -> subprocess.CompletedProcess[str]:
    runtime = _wsl(ROOT); output = _wsl(tmp_path / "python-runtime-identity.json")
    return subprocess.run(["wsl.exe", "--", "env", f"PYTHONPATH={runtime}:{runtime}/src:{AGENT_ROOT}", python,
                           _wsl(CHECK), "--expected-python", expected, "--agent-root", AGENT_ROOT,
                           "--runtime-root", runtime, "--output", output], text=True, capture_output=True, check=False)


def test_python_without_ray_fails_the_zero_provider_gate(tmp_path: Path):
    result = _gate(tmp_path, "/usr/bin/python3", "/usr/bin/python3")
    assert result.returncode != 0
    assert "ModuleNotFoundError" in result.stderr
    assert not (tmp_path / "python-runtime-identity.json").exists()


def test_pinned_appworld_python_imports_real_agent_and_writes_identity(tmp_path: Path):
    result = _gate(tmp_path, PRODUCTION_PYTHON, PRODUCTION_PYTHON)
    assert result.returncode == 0, result.stderr
    identity = json.loads((tmp_path / "python-runtime-identity.json").read_text(encoding="utf-8"))
    assert identity["python_executable"] == PRODUCTION_PYTHON
    assert identity["ray_version"] == "2.58.0"
    assert identity["appworld_version"] == "0.1.3.post1"
    assert identity["imports"][-2:] == ["copromem.experiments.reme_copromem.runner", "reasoningbank_entrypoint"]
    assert len(identity["dependency_set_sha256"]) == 64
