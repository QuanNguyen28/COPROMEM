#!/usr/bin/env python3
"""Zero-provider inventory count for v5.3 fresh-pair selection diagnostics."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from copromem.experiments.reme_copromem.public_tool_schema_registry import verify_public_tool_schema_registry
from scripts.reme_copromem.prepare_tool_schema_v53 import ROOT, INVENTORY_RELATIVE_PATH, _candidate_paths, prior_ids


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--registry", type=Path, required=True); parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    registry = json.loads(args.registry.read_text(encoding="utf-8")); verify_public_tool_schema_registry(registry)
    inventory = json.loads((ROOT / INVENTORY_RELATIVE_PATH).read_text(encoding="utf-8")); excluded = prior_ids()
    rows = [{"task_id": str(row["task_id"]), "family": str(row["task_id"]).rsplit("_", 1)[0],
             "candidate_paths": [list(path) for path in _candidate_paths(registry, str(row["instruction"]))] }
            for row in inventory["tasks"] if str(row["task_id"]) not in excluded]
    by_family = {}
    for row in rows: by_family.setdefault(row["family"], []).append(row)
    groups = [{"family": family, "fresh_ids": sorted(item["task_id"] for item in values),
               "positive_descriptor_ids": sorted(item["task_id"] for item in values if item["candidate_paths"]),
               "positive_descriptor_count": sum(len(item["candidate_paths"]) for item in values),
               "candidate_paths": {item["task_id"]: item["candidate_paths"] for item in values if item["candidate_paths"]}}
              for family, values in sorted(by_family.items())]
    result = {"provider_calls": 0, "registry_sha256": registry["registry_sha256"], "excluded_id_count": len(excluded), "excluded_ids": sorted(excluded),
              "fresh_task_count": len(rows), "families": groups}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"excluded_id_count": len(excluded), "fresh_task_count": len(rows),
                      "families_with_positive_descriptors": sum(bool(row["positive_descriptor_ids"]) for row in groups)}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
