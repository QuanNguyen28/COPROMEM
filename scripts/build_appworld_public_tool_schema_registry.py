#!/usr/bin/env python3
"""Build v5.3 from public AppWorld function-calling and OpenAPI metadata only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from copromem.experiments.reme_copromem.public_tool_schema_registry import (
    build_public_tool_schema_registry, verify_public_tool_schema_registry,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--openapi", required=True, type=Path)
    parser.add_argument("--function-calling", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    registry = build_public_tool_schema_registry(args.openapi, args.function_calling)
    verify_public_tool_schema_registry(registry)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(registry, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"registry_sha256": registry["registry_sha256"], "operations": len(registry["operations"]),
                      "edges": len(registry["dependency_edges"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
