"""Freeze an exposure-screened AppWorld development manifest without model calls.

This deliberately never asks AppWorld for ``test_normal`` (or opens a path with
that component).  It inventories only explicitly requested development splits,
then rejects every task identifier observed in the supplied working tree and
backup roots.  A manifest is emitted only when fourteen clean IDs remain.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
from collections import defaultdict
from pathlib import Path


TASK_ID = re.compile(rb"(?<![0-9a-f])[0-9a-f]{7}_[0-9]+(?![0-9])")
SKIP_PARTS = {".git", ".conda", "node_modules", "__pycache__", "test_normal"}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def safe_files(root: Path):
    for directory, names, files in os.walk(root):
        path = Path(directory)
        names[:] = [name for name in names if name not in SKIP_PARTS]
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        for name in files:
            candidate = path / name
            if not candidate.is_symlink():
                yield candidate


def observed_ids(roots: list[Path]) -> tuple[dict[str, list[str]], dict[str, int]]:
    evidence: dict[str, list[str]] = defaultdict(list)
    counters = {"files": 0, "bytes": 0, "skipped_large_files": 0}
    for root in roots:
        for path in safe_files(root):
            counters["files"] += 1
            relative = str(path)
            for value in TASK_ID.findall(relative.encode("utf-8", "ignore")):
                evidence[value.decode("ascii")].append(relative + " [filename]")
            # Task IDs are short. Read all normal artifacts and, for exceptionally
            # large retained trajectories, scan incrementally rather than omit them.
            try:
                with path.open("rb") as handle:
                    tail = b""
                    while block := handle.read(1024 * 1024):
                        counters["bytes"] += len(block)
                        for value in TASK_ID.findall(tail + block):
                            evidence[value.decode("ascii")].append(relative)
                        tail = (tail + block)[-16:]
            except (OSError, PermissionError):
                counters["skipped_large_files"] += 1
    return dict(evidence), counters


def inventory() -> dict[str, list[str]]:
    from appworld import load_task_ids

    # These are development-eligible sources.  No test split is queried.
    result: dict[str, list[str]] = {}
    for split in ("train", "development", "dev"):
        try:
            result[split] = sorted(load_task_ids(split))
        except Exception as exc:  # package versions do not all expose a dev alias
            result[split] = [f"UNAVAILABLE:{type(exc).__name__}"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--backup", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260925)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()

    roots = [args.repo.resolve(), *(item.resolve() for item in args.backup if item.exists())]
    exposures, counts = observed_ids(roots)
    splits = inventory()
    eligible = sorted({task for ids in splits.values() for task in ids if not task.startswith("UNAVAILABLE:")})
    clean = [task for task in eligible if task not in exposures]
    ordered = sorted(clean, key=lambda task: sha256_bytes(f"{args.seed}\n{task}".encode()))
    audit = {
        "schema": "appworld-development-exposure-audit/v1",
        "appworld_version": importlib.metadata.version("appworld"),
        "source_revision": args.source_revision,
        "selection_seed": args.seed,
        "inventory": splits,
        "scan_roots": [str(item) for item in roots],
        "scan_counts": counts,
        "exposure_count": len(exposures),
        "exposed_task_ids": sorted(exposures),
        "eligible_count": len(eligible),
        "clean_count": len(clean),
        "ordering": "ascending SHA-256(seed + newline + task_id)",
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "exposure_audit.json").write_bytes(canonical(audit) + b"\n")
    if len(ordered) < 14:
        raise SystemExit(f"Only {len(ordered)} clean development IDs; refusing to freeze a 14-task manifest")
    manifest = {
        "schema": "reme-copromem-appworld-development-manifest/v1",
        "source_revision": args.source_revision,
        "appworld_version": audit["appworld_version"],
        "selection_seed": args.seed,
        "selection_order": audit["ordering"],
        "exposure_audit_sha256": sha256_bytes(canonical(audit)),
        "acquisition_task_ids": ordered[:6],
        "evaluation_task_ids": ordered[6:14],
        "disjoint": True,
        "test_normal_queried": False,
    }
    manifest_path = args.output / "development_manifest.json"
    manifest_path.write_bytes(canonical(manifest) + b"\n")
    print(json.dumps({
        "audit_sha256": sha256_bytes(canonical(audit)),
        "manifest_sha256": sha256_bytes(canonical(manifest)),
        "acquisition_task_ids": manifest["acquisition_task_ids"],
        "evaluation_task_ids": manifest["evaluation_task_ids"],
    }, indent=2))


if __name__ == "__main__":
    main()
