#!/usr/bin/env python3
"""Zero-provider import and identity gate for the AppWorld execution runtime.

This file is deliberately executed by the exact interpreter that will run the
engineering entrypoint.  It imports the upstream agent itself, rather than
only checking an entrypoint that can defer that import until after a ledger is
opened.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import sys
from typing import Any


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _distribution_set() -> list[dict[str, str]]:
    rows = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        if name:
            rows.append({"name": name.lower(), "version": distribution.version})
    return sorted(rows, key=lambda row: (row["name"], row["version"]))


def build_identity(*, expected_python: Path, agent_root: Path, runtime_root: Path) -> dict[str, Any]:
    executable = Path(sys.executable)
    if not executable.is_absolute() or executable != expected_python:
        raise RuntimeError("selected production Python differs from the declared absolute executable")
    if not agent_root.is_dir() or str(agent_root) not in sys.path:
        raise RuntimeError("upstream AppWorld agent root is absent from the production PYTHONPATH")

    # These imports are the real transitive boundary that failed in Engineering
    # 012.  Keep them before any runner, lock, ledger, task, or provider call.
    import ray
    import appworld
    import appworld_react_agent
    import copromem.experiments.reme_copromem.runner

    entrypoint = runtime_root / "scripts" / "run_reasoningbank_appworld_engineering.py"
    spec = importlib.util.spec_from_file_location("copromem_reasoningbank_engineering_entrypoint", entrypoint)
    if spec is None or spec.loader is None:
        raise RuntimeError("ReasoningBank evaluation entrypoint is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    distributions = _distribution_set()
    identity = {
        "version": "reasoningbank-appworld-python-runtime-v1",
        "python_executable": str(executable),
        "python_version": sys.version.split()[0],
        "python_prefix": str(Path(sys.prefix).resolve()),
        "python_base_prefix": str(Path(sys.base_prefix).resolve()),
        "ray_version": importlib.metadata.version("ray"),
        "appworld_version": importlib.metadata.version("appworld"),
        "dependency_set_sha256": hashlib.sha256(_canonical(distributions)).hexdigest(),
        "appworld_react_agent_sha256": _sha(Path(appworld_react_agent.__file__).resolve()),
        "appworld_module_sha256": _sha(Path(appworld.__file__).resolve()),
        "entrypoint_sha256": _sha(entrypoint),
        "imports": ["ray", "appworld", "appworld_react_agent", "copromem.experiments.reme_copromem.runner", "reasoningbank_entrypoint"],
    }
    identity["runtime_identity_sha256"] = hashlib.sha256(_canonical(identity)).hexdigest()
    return identity


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-python", required=True, type=Path)
    parser.add_argument("--agent-root", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    identity = build_identity(expected_python=args.expected_python, agent_root=args.agent_root,
                              runtime_root=args.runtime_root)
    _write(args.output, identity)


if __name__ == "__main__":
    main()
