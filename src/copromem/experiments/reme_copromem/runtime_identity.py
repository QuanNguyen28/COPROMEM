"""Path-independent runtime content identities for frozen evaluation runs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


class RuntimeIdentityError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def content_hash(path: Path) -> str:
    if not path.is_file():
        raise RuntimeIdentityError("required runtime content is absent")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hash(root: Path, *, include: tuple[str, ...] = ("*.py", "*.json", "*.toml", "*.lock", "*.txt")) -> str:
    """Hash source content and relative names, deliberately excluding absolute paths."""
    if not root.is_dir():
        raise RuntimeIdentityError("required runtime source tree is absent")
    paths = sorted({path for pattern in include for path in root.rglob(pattern) if path.is_file()})
    if not paths:
        raise RuntimeIdentityError("runtime source tree has no registered source files")
    body = [{"relative": path.relative_to(root).as_posix(), "sha256": content_hash(path)} for path in paths]
    return hashlib.sha256(_canonical(body)).hexdigest()


def build_runtime_identity(*, content: Mapping[str, Path], trees: Mapping[str, Path] | None = None,
                           labels: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Return a portable record that never serializes machine-specific paths."""
    if not content:
        raise RuntimeIdentityError("at least one runtime content identity is required")
    entries = {str(name): {"kind": "file", "sha256": content_hash(Path(path))}
               for name, path in sorted(content.items())}
    for name, path in sorted((trees or {}).items()):
        if name in entries:
            raise RuntimeIdentityError("duplicate runtime identity name")
        entries[str(name)] = {"kind": "tree", "sha256": tree_hash(Path(path))}
    record = {"version": "runtime-content-identity-v1", "entries": entries,
              "labels": dict(sorted((labels or {}).items()))}
    record["runtime_identity_sha256"] = hashlib.sha256(_canonical(record)).hexdigest()
    return record


def verify_runtime_identity(record: Mapping[str, Any], *, content: Mapping[str, Path],
                            trees: Mapping[str, Path] | None = None,
                            labels: Mapping[str, str] | None = None) -> None:
    expected = dict(record)
    observed = build_runtime_identity(content=content, trees=trees, labels=labels)
    if expected != observed:
        raise RuntimeIdentityError("runtime content identity drift")
