#!/usr/bin/env python3
"""Run the zero-provider v6 contrastive integration fixture once.

The target is deliberately an explicit E-backed artifact directory.  It fails
if that directory already contains evidence, avoiding accidental overwrite of
the fixture's append-only records.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from copromem.experiments.reme_copromem.contrastive_v6_integration_fixture import run_fixture, run_restart_drills, run_telemetry_equivalence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True, help="new absolute E-backed fixture artifact directory")
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_absolute() or not str(root).startswith("/mnt/e/"):
        raise SystemExit("--root must be an absolute E-backed WSL path")
    if root.exists() and any(root.iterdir()):
        raise SystemExit("fixture root already contains immutable evidence")
    root.mkdir(parents=True, exist_ok=True)
    run_fixture(root)
    run_restart_drills(root / "restarts")
    run_telemetry_equivalence(root)
    print(root / "final-fixture-report.json")


if __name__ == "__main__":
    main()
