#!/usr/bin/env python3
"""Zero-provider health/import check for the pinned split ReMe service."""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--run", type=pathlib.Path, required=True); args = parser.parse_args()
    root = pathlib.Path(__file__).resolve().parents[1]
    source = pathlib.Path("/mnt/e/Project/AAMAS/_work/reme_paper_2f37a159")
    os.environ.setdefault("COPROMEM_ROOT", str(root)); os.environ.setdefault("COPROMEM_REME_SOURCE", str(source))
    os.environ.setdefault("COPROMEM_REME_PYTHON", "/mnt/e/Project/AAMAS/reme-upstream-fixed-dynamic/bin/python")
    if not source.is_dir() or not pathlib.Path(os.environ["COPROMEM_REME_PYTHON"]).is_file():
        raise SystemExit("pinned ReMe source or isolated interpreter is absent")
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if commit != "2f37a159b72a04ac1885a7db7f1a663a833e7791": raise SystemExit("wrong pinned ReMe source")
    from copromem.experiments.reme_copromem.runner import ReMeService
    run = args.run.resolve(); run.mkdir(parents=True, exist_ok=True)
    service = ReMeService(port=18390, name="reme-health-zero-provider", run=run, ledger=run / "ledger.jsonl", progress=run / "progress.jsonl", cap_usd=100.0)
    try:
        service.wait_healthy(timeout=120.0)
    finally:
        service.close()
    (run / "reme-health.json").write_text(json.dumps({"status": "healthy", "source_commit": commit, "provider_calls": 0}, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__": main()
