"""Fetch official encrypted outputs and list metadata without reading task bodies."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest

IMAGE = "sha256:b5f9aaedde041e30fc4ff795ab46d47849cfc72701b9ffc8c8983fdefe36fcf6"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", choices=["0.1.0", "0.1.3"], default="0.1.0")
    args = parser.parse_args()
    filename = f"experiment-outputs-{args.version}.bundle"
    url = "https://s3.us-west-2.amazonaws.com/appworld.dev/" + filename
    cap = 100_000_000 if args.version == "0.1.0" else 200_000_000
    suffix = "" if args.version == "0.1.0" else "_v013"
    preregistration = (
        "031_OFFICIAL_TRAIN_ARCHIVE_INVENTORY_GATE.md"
        if args.version == "0.1.0"
        else "032_ARCHIVE_V010_RESULT_AND_V013_INVENTORY_GATE.md"
    )
    root = Path(__file__).resolve().parents[2]
    store = RunStore(
        root / ("artifacts/research/official_appworld_train_source_20260916" + suffix)
    )
    archive_dir = store.root / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    target = archive_dir / filename
    old = store.read("downloads", "official-output-bundle")
    if old is None:
        if target.exists():
            raise IntegrityError("unbound or partial archive exists; never overwrite")
        with urllib.request.urlopen(url, timeout=30) as response:
            length = int(response.headers.get("Content-Length", 0))
            if not 0 < length <= cap:
                raise IntegrityError("unexpected or excessive archive length")
            hasher, total = hashlib.sha256(), 0
            with target.open("xb") as stream:
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > cap:
                        raise IntegrityError("archive exceeds registered byte limit")
                    hasher.update(chunk)
                    stream.write(chunk)
            if total != length:
                raise IntegrityError("archive length incomplete; partial retained")
            old = {
                "url": url,
                "bytes": total,
                "sha256": hasher.hexdigest(),
                "utc": datetime.now(timezone.utc).isoformat(),
                "response_headers": dict(response.headers),
            }
        store.write("downloads", "official-output-bundle", old)
    with target.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != old["sha256"] or target.stat().st_size != old["bytes"]:
        raise IntegrityError("downloaded archive changed")
    fixture = (root / "research/fixtures/list_appworld_output_archive.py").read_text(
        encoding="utf-8"
    )
    source = {
        "runner": Path(__file__).read_text(encoding="utf-8"),
        "fixture": fixture,
        "preregistration": (root / "research" / preregistration).read_text(
            encoding="utf-8"
        ),
        "image": IMAGE,
        "download": old,
    }
    store.write("inventory_sources", digest(source), source)
    command = [
        "docker",
        "run",
        "--rm",
        "-i",
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
        "1g" if args.version == "0.1.0" else "2g",
        "--pids-limit",
        "64",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777",
        "--mount",
        f"type=bind,source={archive_dir},target=/archive,readonly",
        "--env",
        "ARCHIVE_FILENAME=" + filename,
        "--entrypoint",
        "python",
        IMAGE,
        "-",
    ]
    process = subprocess.run(
        command,
        input=fixture,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=45,
        check=False,
    )
    raw = {
        "command": command,
        "source_digest": digest(source),
        "exit_code": process.returncode,
        "stdout": process.stdout,
        "stderr": process.stderr,
    }
    store.write("inventory_runs", digest(raw), raw)
    if process.returncode:
        raise RuntimeError("metadata inventory failed; raw record preserved")
    result = json.loads(process.stdout)
    if result["archive_sha256"] != old["sha256"]:
        raise IntegrityError("container inventory used a different archive")
    record = {"source_digest": digest(source), "run_digest": digest(raw), **result}
    store.write("inventories", digest(record), record)
    print(
        json.dumps(
            {
                "inventory_id": digest(record),
                **{
                    k: v
                    for k, v in record.items()
                    if k != "selected_build_train_member_metadata"
                },
                "selected_member_count": len(
                    record["selected_build_train_member_metadata"]
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
