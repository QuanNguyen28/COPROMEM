"""Isolated source-level cache fixtures; no cloud imports or real embeddings."""

from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest

IMAGE = "sha256:81bddf9a168c6b80d4ecf30f35cf1a96a5646ef823cfecb5958d90ccb9a6a5a3"
REVISION = "ed80611788292ea739f1effd31f16c53823b8a0d"
SOURCE_SHA256 = "ac40e71d216668ed5af49bb5c94b77cf7906ef0149c74e4e55ade792e88fd4e2"


def main():
    root = Path(__file__).resolve().parents[2]
    vendor = root / "artifacts/research/baseline_sources/reasoning-bank"
    store = RunStore(root / "artifacts/research/reasoningbank_audit_20260916")
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=vendor, text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=vendor, text=True
    )
    source = (vendor / "WebArena/memory_management.py").read_bytes()
    if (
        revision != REVISION
        or dirty
        or hashlib.sha256(source).hexdigest() != SOURCE_SHA256
    ):
        raise IntegrityError("ReasoningBank source is not the pinned clean checkout")
    fixture = (root / "research/fixtures/reasoningbank_cache_lifecycle.py").read_text(
        encoding="utf-8"
    )
    provenance = {
        "revision": revision,
        "source_sha256": SOURCE_SHA256,
        "fixture": fixture,
        "runner_source": Path(__file__).read_text(encoding="utf-8"),
        "image": IMAGE,
        "limitations": "Reuses an isolated ExpeL torch environment, NOT ReasoningBank's native dependencies. Function bodies unchanged; import-time initialization bypassed; embeddings are toy stubs. No model or policy reproduction.",
    }
    store.write("cache_fixture_sources", digest(provenance), provenance)
    results = []
    for replicate in range(2):
        # Random name only enables bounded cleanup if the offline fixture times out.
        name = "copromem-reasoningbank-cache-" + uuid.uuid4().hex[:12]
        command = [
            "docker",
            "run",
            "--rm",
            "-i",
            "--name",
            name,
            "--label",
            "io.copromem.reasoningbank-probe=" + digest(provenance),
            "--network",
            "none",
            "--read-only",
            "--user",
            "10001:10001",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--cpus",
            "1",
            "--memory",
            "1g",
            "--pids-limit",
            "64",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777",
            "--mount",
            f"type=bind,source={vendor},target=/vendor,readonly",
            "-e",
            "OMP_NUM_THREADS=1",
            "-e",
            "OPENBLAS_NUM_THREADS=1",
            "-e",
            "PYTHONDONTWRITEBYTECODE=1",
            IMAGE,
            "-",
        ]
        try:
            process = subprocess.run(
                command,
                input=fixture,
                text=True,
                encoding="utf-8",
                capture_output=True,
                timeout=45,
                check=False,
            )
            raw = {
                "exit_code": process.returncode,
                "stdout": process.stdout,
                "stderr": process.stderr,
            }
        except subprocess.TimeoutExpired as exc:
            inspected = subprocess.run(
                ["docker", "inspect", "--format", "{{json .Config.Labels}}", name],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            labels = json.loads(inspected.stdout) if inspected.returncode == 0 else {}
            if labels.get("io.copromem.reasoningbank-probe") == digest(provenance):
                subprocess.run(
                    ["docker", "kill", name],
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
            raw = {
                "exit_code": None,
                "timeout": True,
                "stdout": str(exc.stdout),
                "stderr": str(exc.stderr),
            }
        record = {
            "utc": datetime.now(timezone.utc).isoformat(),
            "replicate": replicate,
            "source_digest": digest(provenance),
            "command": command,
            **raw,
        }
        store.write("cache_fixture_runs", digest(record), record)
        print(
            json.dumps(
                {
                    "run_id": digest(record),
                    "replicate": replicate,
                    "exit_code": raw["exit_code"],
                }
            ),
            flush=True,
        )
        if raw["exit_code"] != 0:
            raise RuntimeError("cache fixture failed; raw evidence preserved")
        results.append(json.loads(raw["stdout"]))
    if results[0] != results[1] or results[0]["passed"] != 10:
        raise IntegrityError("source fixtures did not reproduce all ten checks")
    audit = {
        "source_digest": digest(provenance),
        "identical_repeats": True,
        "result": results[0],
        "paid_calls": 0,
    }
    store.write("cache_fixture_audits", digest(audit), audit)
    print(json.dumps({"audit_id": digest(audit), **audit}, indent=2))


if __name__ == "__main__":
    main()
