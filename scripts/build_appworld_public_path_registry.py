#!/usr/bin/env python3
"""Build the v5.2 public path registry from AppWorld OpenAPI documents.

This command intentionally has no task, trajectory, model, scorer, or network
argument.  The output is a public-metadata snapshot that can be committed and
verified before any task is opened.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from copromem.experiments.reme_copromem.public_path_registry import build_public_registry, verify_public_registry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-docs", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    registry = build_public_registry(args.api_docs)
    verify_public_registry(registry)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(registry, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"registry_sha256": registry["registry_sha256"], "operations": len(registry["operations"]),
                      "edges": len(registry["dependency_edges"]), "sources": len(registry["source_metadata"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
