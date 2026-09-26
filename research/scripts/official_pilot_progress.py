#!/usr/bin/env python3
"""Append-only, flushed progress records for the official upstream pilot."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/mnt/e/Project/AAMAS/COPROMEM/artifacts/research/official_reme_copromem_pilot")
LOG = ROOT / "progress.jsonl"


def append(record: dict) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    record = {"timestamp": datetime.now(timezone.utc).isoformat(), **record}
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


if __name__ == "__main__":
    append({
        "stage": "setup",
        "event": "official_upstream_split_environment_restoration",
        "status": "in_progress",
        "next_scheduled_work": "complete E-backed FlowLLM/FastMCP service installation",
        "recoverable_error": "AgentScope 1.0.20 MCP-1 API conflicts with FastMCP MCP-2 runtime; split into separate official processes",
    })
