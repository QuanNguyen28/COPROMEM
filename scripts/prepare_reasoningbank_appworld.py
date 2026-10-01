#!/usr/bin/env python3
"""Zero-provider preflight for the ReasoningBank AppWorld port."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from copromem.integrations.reasoning_bank.appworld import (
    FAILED_EXTRACTION_PROMPT, SUCCESSFUL_EXTRACTION_PROMPT, UPSTREAM_COMMIT,
)
from copromem.integrations.reasoning_bank.appworld_protocol import protocol_record


def _git(checkout: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(checkout), *args], text=True).strip()


def _constants(path: Path) -> dict[str, str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in {"SUCCESSFUL_SI", "FAILED_SI"}:
                result[node.targets[0].id] = ast.literal_eval(node.value)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-checkout", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    checkout = args.upstream_checkout.resolve()
    commit = _git(checkout, "rev-parse", "HEAD")
    if commit != UPSTREAM_COMMIT:
        raise SystemExit(f"expected upstream {UPSTREAM_COMMIT}, found {commit}")
    if _git(checkout, "status", "--porcelain"):
        raise SystemExit("upstream ReasoningBank checkout must be clean")
    prompts = _constants(checkout / "WebArena" / "prompts" / "memory_instruction.py")
    prompt_checks = {
        "successful": prompts.get("SUCCESSFUL_SI", "").strip() == SUCCESSFUL_EXTRACTION_PROMPT.strip(),
        "failed": prompts.get("FAILED_SI", "").strip() == FAILED_EXTRACTION_PROMPT.strip(),
    }
    if not all(prompt_checks.values()):
        raise SystemExit("vendored ReasoningBank extraction prompt differs from pinned upstream")
    source_files = [
        checkout / "WebArena" / "memory_management.py",
        checkout / "WebArena" / "induce_memory.py",
        checkout / "WebArena" / "prompts" / "memory_instruction.py",
    ]
    record = {
        "status": "zero_provider_preflight_passed",
        "protocol": protocol_record(),
        "upstream_commit": commit,
        "upstream_source_sha256": {
            str(path.relative_to(checkout)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in source_files
        },
        "prompt_parity": prompt_checks,
        "provider_calls": 0,
        "payloads_opened": 0,
        "appworld_tasks_executed": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

