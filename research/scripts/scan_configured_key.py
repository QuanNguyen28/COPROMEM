"""Exact configured-key byte scan of explicit scopes; never print or persist the key."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values

from copromem.checkpoints import RunStore, digest


def contains_bytes(path: Path, needle: bytes) -> tuple[bool, int]:
    overlap, total, found = b"", 0, False
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            total += len(chunk)
            block = overlap + chunk
            found = found or needle in block
            overlap = block[-max(1, len(needle) - 1) :]
    return found, total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scopes", nargs="+", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    value = dotenv_values(root / ".env").get("OPENROUTER_API_KEY")
    if not value or len(value) < 12:
        raise ValueError("configured key unavailable; exact-value audit not performed")
    needle = value.encode("utf-8")
    selected = {
        path for path in root.iterdir() if path.is_file() and path.name != ".env"
    }
    for name in args.scopes:
        target = (root / name).resolve()
        if not target.is_relative_to(root) or not target.exists():
            raise ValueError("scan scope must exist inside the project")
        paths = target.rglob("*") if target.is_dir() else [target]
        selected.update(
            path
            for path in paths
            if path.is_file()
            and not path.is_symlink()
            and path.name != ".env"
            and ".git" not in path.relative_to(root).parts
        )
    matches, unreadable, total_bytes, count = [], [], 0, 0
    for path in sorted(selected):
        try:
            matched, size = contains_bytes(path, needle)
        except OSError:
            unreadable.append(path.relative_to(root).as_posix())
            continue
        count += 1
        total_bytes += size
        if matched:
            matches.append(path.relative_to(root).as_posix())
    record = {
        "audit": "configured-key-exact-byte-explicit-scopes-v2",
        "utc": datetime.now(timezone.utc).isoformat(),
        "scopes": args.scopes,
        "root_files_except_env": True,
        "git_directories_excluded": True,
        "files_scanned": count,
        "bytes_scanned": total_bytes,
        "matching_paths": matches,
        "unreadable_paths": unreadable,
        "key_value_persisted": False,
        "limitation": "Dated non-atomic exact current configured-key byte scan of explicit scopes, not encoded secrets, general credentials, excluded env or unlisted old evidence.",
    }
    store = RunStore(root / "artifacts/research/safety_audits")
    store.write("records", digest(record), record)
    print(
        {
            "audit_id": digest(record),
            "files_scanned": count,
            "bytes_scanned": total_bytes,
            "matches": len(matches),
            "unreadable": len(unreadable),
        }
    )


if __name__ == "__main__":
    main()
