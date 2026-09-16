"""Pinned source/parser fixtures in an isolated existing image; no baseline edits."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest

COMMIT = "e6fa3902e2cfb9681f454b355691b771f70543f8"
IMAGE = "sha256:b5f9aaedde041e30fc4ff795ab46d47849cfc72701b9ffc8c8983fdefe36fcf6"
WHEEL_SHA = "53e6e208cf4a1ad53fb8b1b4467b756375a4f827331e290618aedcf481cb1d5c"


def main():
    root = Path(__file__).resolve().parents[2]
    source = root / "artifacts/research/baseline_sources/AgentSpec"
    store = RunStore(root / "artifacts/research/agentspec_audit_20260916")
    fixture = root / "research/fixtures/agentspec_parser_fixture.py"
    wheel = store.root / "wheels/antlr4_python3_runtime-4.13.0-py3-none-any.whl"
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=source, text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=source, text=True
    )
    if (
        commit != COMMIT
        or dirty
        or hashlib.sha256(wheel.read_bytes()).hexdigest() != WHEEL_SHA
    ):
        raise IntegrityError("upstream commit/worktree or runtime wheel changed")
    names = subprocess.check_output(
        ["git", "ls-files"], cwd=source, text=True
    ).splitlines()
    files = {
        name: hashlib.sha256((source / name).read_bytes()).hexdigest()
        for name in names
        if (source / name).is_file()
    }
    sparse = subprocess.check_output(
        ["git", "sparse-checkout", "list"], cwd=source, text=True
    )
    protocol = {
        "source": "https://github.com/haoyuwang99/AgentSpec",
        "commit": commit,
        "sparse_checkout": sparse,
        "materialized_file_hashes": files,
        "image_id": IMAGE,
        "wheel_sha256": WHEEL_SHA,
        "runtime_requirement": "antlr4-python3-runtime==4.13 (installed wheel 4.13.0)",
        "fixture_source": fixture.read_text(encoding="utf-8"),
        "runner_source": Path(__file__).read_text(encoding="utf-8"),
        "model_calls": 0,
        "dataset_payloads_opened": False,
    }
    store.write("protocols", digest(protocol), protocol)
    results = []
    for replicate in range(2):
        key = digest({"protocol": digest(protocol), "replicate": replicate})
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            "1g",
            "--cpus",
            "1",
            "--user",
            "65532:65532",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--mount",
            f"type=bind,source={source},target=/upstream,readonly",
            "--mount",
            f"type=bind,source={fixture},target=/fixture.py,readonly",
            "--mount",
            f"type=bind,source={wheel},target=/antlr.whl,readonly",
            "--entrypoint",
            "python",
            IMAGE,
            "/fixture.py",
        ]
        record = store.read("fixture_runs", key)
        if record is None:
            completed = subprocess.run(
                command,
                text=True,
                capture_output=True,
                encoding="utf-8",
                timeout=90,
                check=False,
            )
            record = {
                "protocol_digest": digest(protocol),
                "replicate": replicate,
                "command": command,
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
            store.write("fixture_runs", key, record)
        if record["exit_code"] != 0:
            raise RuntimeError(
                "native parser fixture failed; raw process preserved at " + key
            )
        rows = [
            json.loads(line.split("=", 1)[1])
            for line in record["stdout"].splitlines()
            if line.startswith("AGENTSPEC_FIXTURE=")
        ]
        if len(rows) != 1:
            raise IntegrityError("missing or ambiguous fixture result")
        results.append(rows[0])
    if results[0] != results[1]:
        raise IntegrityError("fixture outcomes do not repeat")
    audit = {
        "protocol_digest": digest(protocol),
        "unchanged_upstream_commit": COMMIT,
        "identical_repeats": 2,
        "cases": len(results[0]["cases"]),
        "result": results[0],
        "model_calls": 0,
        "real_tool_actions": 0,
        "native_benchmark_episodes": 0,
    }
    store.write("fixture_audits", digest(audit), audit)
    print(json.dumps({"audit_id": digest(audit), **audit}, indent=2))


if __name__ == "__main__":
    main()
