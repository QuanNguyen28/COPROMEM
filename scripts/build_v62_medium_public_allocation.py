#!/usr/bin/env python3
"""Build the public-only, pre-payload v6.2 medium allocation audit."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from copromem.experiments.reme_copromem.medium_allocation import allocate_round_robin, canonical_digest
from copromem.experiments.reme_copromem.runner import write_json
from copromem.experiments.reme_copromem.v61_custody import classify


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=pathlib.Path)
    args = parser.parse_args(); run = args.run.resolve(); run.mkdir(parents=True, exist_ok=True)
    inventory_path = ROOT / "research/reme_copromem_fixed_dynamic_review/v62-medium-public-test-normal-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    task_ids = set(map(str, inventory["task_ids"]))
    custody = classify(ROOT, inventory_path, include_research=False, candidate_ids=task_ids)
    known = {item["task_id"] for item in custody["decisions"]}
    custody["decisions"].extend({"task_id": task_id, "classification": "public_mention_only",
                                  "evidence": [{"path": str(inventory_path.relative_to(ROOT)).replace("\\", "/"),
                                                "category": "public_mention_only", "reason": "permitted public inventory"}]}
                                for task_id in sorted(task_ids - known))
    custody["decisions"].sort(key=lambda item: item["task_id"])
    custody["decision_trace_sha256"] = canonical_digest(custody["decisions"])
    allocation = dict(allocate_round_robin(inventory_ids=task_ids,
                                            hard_exposed_ids=custody["hard_exclusion"],
                                            ambiguous_ids=custody["ambiguous_exclusion"], count=30))
    allocation.update({"custody_trace_sha256": custody["decision_trace_sha256"],
                       "public_inventory_file_sha256": canonical_digest(inventory),
                       "registry_sha256": json.loads((ROOT / "research/reme_copromem_fixed_dynamic_review/appworld_public_tool_schema_registry_v5_3.json").read_text(encoding="utf-8"))["registry_sha256"],
                       "selection_commits_all_selected_ids_to_exploratory_exposure": True})
    if not allocation["sufficient"]:
        raise RuntimeError("fewer than 30 public, non-hard-exposed IDs are available")
    write_json(run / "custody-audit.json", custody)
    write_json(run / "allocation-audit.json", allocation)


if __name__ == "__main__":
    main()
