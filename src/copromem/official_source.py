"""Lossless public-log parsing and strict allowlisting for offline source records."""

from __future__ import annotations

import hashlib
import json
import re
import stat
import zlib
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .checkpoints import IntegrityError, RunStore, digest

PUBLIC_FILES = (
    "logs/environment_io.md",
    "logs/api_calls.jsonl",
    "version/code.txt",
    "version/data.txt",
)
HORIZONTAL_RULE = "-" * 76


@dataclass(frozen=True)
class LogInteraction:
    index: int
    code: str
    output: str
    code_start: int
    code_end: int
    output_start: int
    output_end: int


def parse_public_log(text: str) -> list[LogInteraction]:
    """Parse the reviewed native writer grammar, preserving field bytes-as-text.

    Exact fence lines inside a field are ambiguous in this format and rejected.
    No stripping, code repair, AST execution or evaluator inference is performed.
    """
    if not isinstance(text, str) or "\r" in text:
        raise IntegrityError("public log must be unnormalized LF text")
    header = re.compile(
        r"### (?:Environment Interaction|Execution) ([1-9][0-9]*)\n"
        + re.escape(HORIZONTAL_RULE)
        + r"\n```python\n"
    )
    rows: list[LogInteraction] = []
    cursor = 0
    while cursor < len(text):
        # Native writer separates interactions using newline-only whitespace.
        while cursor < len(text) and text[cursor] == "\n":
            cursor += 1
        if cursor == len(text):
            break
        match = header.match(text, cursor)
        if not match or int(match.group(1)) != len(rows) + 1:
            raise IntegrityError("invalid or noncontiguous public interaction header")
        code_start = match.end()
        code_end = text.find("\n```\n\n```\n", code_start)
        if code_end < 0:
            raise IntegrityError("missing exact code/output separator")
        code = text[code_start:code_end]
        if re.search(r"(?m)^```.*$", code):
            raise IntegrityError("ambiguous fence inside code field")
        output_start = code_end + len("\n```\n\n```\n")
        output_end = text.find("\n```\n", output_start)
        if output_end < 0:
            raise IntegrityError("missing output closing fence")
        output = text[output_start:output_end]
        if re.search(r"(?m)^```.*$", output):
            raise IntegrityError("ambiguous fence inside output field")
        rows.append(
            LogInteraction(
                len(rows) + 1,
                code,
                output,
                code_start,
                code_end,
                output_start,
                output_end,
            )
        )
        cursor = output_end + len("\n```\n")
    if not rows:
        raise IntegrityError("empty public interaction log")
    return rows


def selected_member_names(run: str, tasks: list[str]) -> list[str]:
    parts = run.split("/")
    if (
        not parts
        or parts[-1] != "train"
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise IntegrityError("an explicit train run is required")
    if "\\" in run or ":" in run or not tasks or len(tasks) != len(set(tasks)):
        raise IntegrityError("unsafe or duplicate selection")
    if any(not re.fullmatch(r"[a-f0-9]{7}_[1-9][0-9]*", task) for task in tasks):
        raise IntegrityError("invalid selected task ID")
    return [f"{run}/tasks/{task}/{name}" for task in tasks for name in PUBLIC_FILES]


def validate_member_inventory(
    infos: list[Any],
    expected: dict[str, dict],
    *,
    per_file_cap: int = 1_000_000,
    total_cap: int = 4_000_000,
) -> None:
    """Validate metadata before any ZIP member body is opened."""
    counts = Counter(info.filename for info in infos)
    if any(count != 1 for count in counts.values()):
        raise IntegrityError("duplicate ZIP member names")
    selected = {info.filename: info for info in infos if info.filename in expected}
    if set(selected) != set(expected):
        raise IntegrityError("missing allowlisted ZIP member")
    total = 0
    for name, info in selected.items():
        if (
            name.startswith("/")
            or any(part in {"", ".", ".."} for part in name.split("/"))
            or "\\" in name
            or ":" in name
        ):
            raise IntegrityError("unsafe selected member path")
        if info.is_dir() or stat.S_ISLNK(info.external_attr >> 16):
            raise IntegrityError("selected member is a directory or symlink")
        entry = expected[name]
        if any(
            (observed != entry[key])
            for key, observed in (
                ("bytes", info.file_size),
                ("compressed_bytes", info.compress_size),
                ("crc", info.CRC),
            )
        ):
            raise IntegrityError("selected member metadata changed")
        if not 0 <= info.file_size <= per_file_cap:
            raise IntegrityError("selected member exceeds size cap")
        total += info.file_size
    if total > total_cap:
        raise IntegrityError("selected member total exceeds cap")


def audit_extracted_source(store: RunStore, key: str) -> dict:
    """Regenerate every parsed field from the exact allowlisted raw bytes."""
    protocol = store.read("public_extraction_protocols", key)
    saved = store.read("public_extraction_reports", key)
    if (
        protocol is None
        or saved is None
        or digest(protocol) != key
        or saved["protocol_digest"] != key
    ):
        raise IntegrityError("extraction protocol/report provenance mismatch")
    request, report = protocol["request"], saved["report"]
    selected = (store.root / "selected_public" / key).resolve()
    if Path(saved["selected_directory"]).resolve() != selected:
        raise IntegrityError("extracted directory outside the bound source store")
    names = selected_member_names(request["run"], request["tasks"])
    relative = [name.removeprefix(request["run"] + "/tasks/") for name in names]
    if (
        report["members_read"] != names
        or report["request_digest"] != digest(request)
        or set(report["files"]) != set(relative)
    ):
        raise IntegrityError("extraction member allowlist changed")
    raw_root = selected / "raw"
    actual = {
        path.relative_to(raw_root).as_posix()
        for path in raw_root.rglob("*")
        if path.is_file()
    }
    if actual != set(relative) or any(
        path.is_symlink() for path in selected.rglob("*")
    ):
        raise IntegrityError("extra, missing or linked extracted public file")
    if (
        json.loads((selected / "extraction_report.json").read_text(encoding="utf-8"))
        != report
    ):
        raise IntegrityError(
            "extraction report no longer matches saved container result"
        )
    raw_by_path = {}
    for name, path in zip(names, relative, strict=True):
        data = (raw_root / path).read_bytes()
        metadata = report["files"][path]
        expected = request["members"][name]
        if (
            metadata["archive_member"] != name
            or metadata["bytes"] != len(data)
            or metadata["sha256"] != hashlib.sha256(data).hexdigest()
            or len(data) != expected["bytes"]
            or zlib.crc32(data) != expected["crc"]
        ):
            raise IntegrityError("raw public source bytes/hash/ZIP CRC changed")
        raw_by_path[path] = data
    rows = report["tasks"]
    if [row["task_id"] for row in rows] != request["tasks"]:
        raise IntegrityError("parsed task order or membership changed")
    parsed_by_task = {}
    for row in rows:
        task = row["task_id"]
        if row["parse_status"] != "parsed":
            raise IntegrityError("rejected source log is not usable")
        interactions = parse_public_log(
            raw_by_path[f"{task}/logs/environment_io.md"].decode("utf-8")
        )
        expected = {
            "task_id": task,
            "versions": {
                name: raw_by_path[f"{task}/version/{name}.txt"].decode("utf-8").strip()
                for name in ("code", "data")
            },
            "interactions": [asdict(item) for item in interactions],
            "source_log_sha256": hashlib.sha256(
                raw_by_path[f"{task}/logs/environment_io.md"]
            ).hexdigest(),
        }
        parsed = json.loads(
            (selected / "parsed" / (task + ".json")).read_text(encoding="utf-8")
        )
        if (
            parsed != expected
            or digest(parsed) != row["parsed_digest"]
            or row["interactions"] != len(interactions)
            or row["versions"] != parsed["versions"]
        ):
            raise IntegrityError("parsed source does not regenerate losslessly")
        parsed_by_task[task] = parsed
    if {path.name for path in (selected / "parsed").iterdir()} != {
        task + ".json" for task in request["tasks"]
    }:
        raise IntegrityError("extra or missing parsed task record")
    return {
        "audit": "lossless-official-public-source-bytes-and-parsed-fields-v1",
        "protocol_digest": key,
        "extraction_report_digest": digest(saved),
        "tasks": request["tasks"],
        "raw_files_verified": len(relative),
        "parsed_digests": {task: digest(row) for task, row in parsed_by_task.items()},
        "paid_calls": 0,
        "task_executions": 0,
    }
