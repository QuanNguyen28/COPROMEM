"""Run the frozen 32-public-file extraction gate in the pinned isolated image."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest
from copromem.official_source import selected_member_names
from copromem.stateful_adapter import stop_owned_container

IMAGE = "sha256:b5f9aaedde041e30fc4ff795ab46d47849cfc72701b9ffc8c8983fdefe36fcf6"
INVENTORY_ID = "9a43b08f57874a1e209cbbb40d87c4b145a9179c42f2a3e3993256aae79a1414"
ARCHIVE_SHA = "e5ec6367d32b1883d28aaa25e4fe5026c89a08d5fb7a5742a83bfb65fe6bb2da"


def main():
    root = Path(__file__).resolve().parents[2]
    store = RunStore(
        root / "artifacts/research/official_appworld_train_source_20260916_v013"
    )
    inventory = store.read("inventories", INVENTORY_ID)
    if (
        inventory is None
        or digest(inventory) != INVENTORY_ID
        or inventory["archive_sha256"] != ARCHIVE_SHA
    ):
        raise IntegrityError("official inventory changed")
    source_store = RunStore(root / "artifacts/research/cycle15_reflection_source")
    selection = source_store.read("dataset", "selection")
    if (
        digest(selection)
        != "161cf98db391278e13f59667b63d55c1b6cf8a576f9a6ee40e694314699f0dd5"
    ):
        raise IntegrityError("frozen build selection changed")
    run = "legacy_react_code_agent/openai/gpt-4o-2024-05-13/train"
    names = selected_member_names(run, selection["build"])
    rows = {
        row["path"]: row for row in inventory["selected_build_train_member_metadata"]
    }
    if not set(names) <= set(rows):
        raise IntegrityError("selected file absent from frozen inventory")
    request = {
        "run": run,
        "tasks": selection["build"],
        "archive_sha256": ARCHIVE_SHA,
        "zip_sha256": inventory["decrypted_zip_sha256"],
        "members": {name: rows[name] for name in names},
    }
    archive = store.root / "archive/experiment-outputs-0.1.3.bundle"
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != ARCHIVE_SHA:
            raise IntegrityError("archive bytes changed")
    fixture_path = root / "research/fixtures/extract_appworld_public_logs.py"
    fixture = fixture_path.read_text(encoding="utf-8")
    texts = {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in [
            Path(__file__),
            fixture_path,
            root
            / "research/033_TRAIN_ARCHIVE_INVENTORY_RESULT_AND_PUBLIC_FILE_GATE.md",
            *sorted((root / "src/copromem").glob("*.py")),
        ]
    }
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=root, text=True
    ).strip()
    if branch != "codex/copromem-research-loop":
        raise IntegrityError("wrong research branch")
    protocol = {
        "request": request,
        "image": IMAGE,
        "source_texts": texts,
        "branch": branch,
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "inventory_id": INVENTORY_ID,
    }
    key = digest(protocol)
    store.write("public_extraction_protocols", key, protocol)
    store.write("extraction_request", "extraction", request)
    selected = store.root / "selected_public" / key
    previous = store.read("public_extraction_reports", key)
    if previous is not None:
        if previous["protocol_digest"] != key:
            raise IntegrityError("stored extraction provenance mismatch")
        print(
            json.dumps(
                {
                    "cached": True,
                    "protocol_digest": key,
                    "decision": previous["report"]["decision"],
                }
            )
        )
        return
    if selected.exists():
        raise IntegrityError(
            "partial or unbound selected-public output exists; never overwrite"
        )
    selected.mkdir(parents=True)
    name = "copromem-public-extraction-" + key[:12]
    command = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--name",
        name,
        "--label",
        "io.copromem.research=cycle05",
        "--label",
        "io.copromem.output=" + digest(str(selected.resolve())),
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
        "2g",
        "--pids-limit",
        "64",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777",
        "--mount",
        f"type=bind,source={archive.parent},target=/archive,readonly",
        "--mount",
        f"type=bind,source={store.root / 'extraction_request'},target=/request,readonly",
        "--mount",
        f"type=bind,source={root / 'src'},target=/implementation,readonly",
        "--mount",
        f"type=bind,source={selected},target=/selected",
        "--env",
        "PYTHONPATH=/implementation",
        "--entrypoint",
        "python",
        IMAGE,
        "-",
    ]
    try:
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
            "exit_code": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        stopped = stop_owned_container(name, selected)
        raw = {
            "exit_code": None,
            "timeout": True,
            "cleanup": stopped,
            "stdout": str(exc.stdout),
            "stderr": str(exc.stderr),
        }
    record = {
        "protocol_digest": key,
        "utc": datetime.now(timezone.utc).isoformat(),
        "command": command,
        **raw,
    }
    store.write("public_extraction_runs", digest(record), record)
    if raw["exit_code"] != 0:
        raise RuntimeError("public extraction failed; partial evidence retained")
    report = json.loads(
        (selected / "extraction_report.json").read_text(encoding="utf-8")
    )
    if report["request_digest"] != digest(request) or report["members_read"] != names:
        raise IntegrityError("extraction output disagrees with requested allowlist")
    for relative, metadata in report["files"].items():
        path = selected / "raw" / relative
        if (
            not path.resolve().is_relative_to((selected / "raw").resolve())
            or hashlib.sha256(path.read_bytes()).hexdigest() != metadata["sha256"]
        ):
            raise IntegrityError("extracted public bytes changed")
    result = {
        "protocol_digest": key,
        "run_digest": digest(record),
        "selected_directory": str(selected),
        "report": report,
    }
    store.write("public_extraction_reports", key, result)
    print(
        json.dumps(
            {
                "protocol_digest": key,
                "run_digest": digest(record),
                "selected_directory": str(selected),
                **json.loads(raw["stdout"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
