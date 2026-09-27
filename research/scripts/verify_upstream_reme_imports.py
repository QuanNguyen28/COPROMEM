#!/usr/bin/env python3
"""Zero-cost import audit for the pinned paper-era ReMe AppWorld source.

Run this with the isolated upstream-ReMe environment.  It imports source by
absolute path, rather than depending on the newer ``reme_ai`` package
metadata, so the audit covers the legacy AppWorld service that the pinned
benchmark agent actually calls.
"""
from __future__ import annotations

import importlib
import hashlib
import pathlib
import subprocess
import sys


SOURCE = pathlib.Path("/home/xiqhq/copromem-reme").resolve()
EXPECTED_COMMIT = "2f37a159b72a04ac1885a7db7f1a663a833e7791"


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(SOURCE), *args], text=True).strip()


def main() -> None:
    if not SOURCE.is_dir():
        raise RuntimeError(f"pinned ReMe source is absent: {SOURCE}")
    if git("rev-parse", "HEAD") != EXPECTED_COMMIT:
        raise RuntimeError("pinned ReMe checkout does not match the registered commit")
    if str(SOURCE) not in sys.path:
        sys.path.insert(0, str(SOURCE))

    modules = [
        "reme",
        "reme.reme",
        "reme.core.llm.openai_llm",
        "reme.core.embedding.openai_embedding_model",
    ]
    imported = {}
    for name in modules:
        print(f"importing={name}", flush=True)
        imported[name] = importlib.import_module(name)
        print(f"imported={name}", flush=True)
    for name, module in imported.items():
        origin = pathlib.Path(module.__file__).resolve()
        if SOURCE not in origin.parents and origin != SOURCE:
            raise RuntimeError(f"{name} was not imported from pinned source: {origin}")

    service = SOURCE / "reme" / "config" / "service.yaml"
    required_routes = {
        "retrieve_task_memory",
        "summary_task_memory",
        "add_task_memory",
        "record_task_memory",
        "delete_task_memory",
        "load_memory",
        "dump_memory",
    }
    text = service.read_text(encoding="utf-8")
    absent = sorted(route for route in required_routes if f"  {route}:" not in text)
    if absent:
        raise RuntimeError(f"pinned service config lacks routes: {absent}")

    print(f"reme_commit={EXPECTED_COMMIT}")
    listing = subprocess.check_output(
        ["git", "-C", str(SOURCE), "ls-tree", "-r", "HEAD"],
    )
    print(f"reme_tree_digest={hashlib.sha256(listing).hexdigest()}")
    print("upstream_reme_imports=passed")


if __name__ == "__main__":
    main()
