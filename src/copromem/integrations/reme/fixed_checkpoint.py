"""Read-only semantic identity checkpoints for official upstream ReMe Fixed."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping

from .bank import _fsync_directory, _fsync_file, file_hash, semantic_bank_hash


class ReMeFixedIntegrityError(RuntimeError):
    pass


def _atomic(path: Path, value: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, path); _fsync_directory(path.parent)
    return file_hash(path)


class ReMeFixedIntegrityManager:
    """Dump/attest a Fixed service without invoking lifecycle or embeddings."""
    VERSION = "reme-fixed-integrity-v1"

    def __init__(self, *, root: Path, frozen_semantic_hash: str,
                 dump_current: Callable[[Path], None], assert_no_mutation_roles: Callable[[], None] | None = None) -> None:
        self.root, self.frozen_semantic_hash = root.resolve(), str(frozen_semantic_hash)
        self.dump_current = dump_current
        self.assert_no_mutation_roles = assert_no_mutation_roles or (lambda: None)
        self.root.mkdir(parents=True, exist_ok=True)

    def checkpoint(self, *, label: str, predecessor_checkpoint_sha256: str | None = None) -> dict[str, Any]:
        if not label or "/" in label or "\\" in label:
            raise ReMeFixedIntegrityError("Fixed checkpoint label is invalid")
        marker = self.root / f"{label}.json"
        dump = self.root / f"{label}.jsonl"
        if marker.exists():
            value = json.loads(marker.read_text(encoding="utf-8"))
            if value.get("file_sha256") != file_hash(dump) or value.get("semantic_sha256") != semantic_bank_hash(dump):
                raise ReMeFixedIntegrityError("persisted Fixed checkpoint has drifted")
            return value
        self.assert_no_mutation_roles()
        self.dump_current(dump)
        if not dump.is_file():
            raise ReMeFixedIntegrityError("official ReMe Fixed dump is absent")
        _fsync_file(dump)
        semantic = semantic_bank_hash(dump)
        if semantic != self.frozen_semantic_hash:
            raise ReMeFixedIntegrityError("official ReMe Fixed semantic state mutated")
        value = {"version": self.VERSION, "label": label, "file": dump.name,
                 "file_sha256": file_hash(dump), "semantic_sha256": semantic,
                 "predecessor_checkpoint_sha256": predecessor_checkpoint_sha256}
        value["checkpoint_sha256"] = hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                                                  separators=(",", ":")).encode("utf-8")).hexdigest()
        _atomic(marker, value)
        return value

    def reconcile(self) -> tuple[dict[str, Any], ...]:
        rows = []
        predecessor = None
        for marker in sorted(self.root.glob("*.json")):
            value = json.loads(marker.read_text(encoding="utf-8"))
            dump = self.root / str(value.get("file", ""))
            if (value.get("version") != self.VERSION or value.get("predecessor_checkpoint_sha256") != predecessor
                    or value.get("file_sha256") != file_hash(dump)
                    or value.get("semantic_sha256") != self.frozen_semantic_hash
                    or semantic_bank_hash(dump) != self.frozen_semantic_hash):
                raise ReMeFixedIntegrityError("Fixed checkpoint chain is incomplete or inconsistent")
            predecessor = value.get("checkpoint_sha256")
            rows.append(value)
        return tuple(rows)
