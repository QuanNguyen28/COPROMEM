#!/usr/bin/env python3
"""Read-only, post-freeze audit of v5.3 public callable-path recognition.

The registry is verified before immutable history artifacts are opened.  The
output deliberately contains only hashes, public operation names, public slot
names, and classification records; it excludes instructions, code, values,
scores, prompts, responses, and scorer state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from copromem.benchmarks.appworld.adapter import normalize_appworld_history
from copromem.experiments.reme_copromem.public_tool_schema_registry import (
    canonical_operation_signature,
    canonical_digest,
    public_tool_path_audit,
    verify_public_tool_schema_registry,
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(registry: dict[str, Any], artifact: Path) -> dict[str, Any]:
    row = _load(artifact)
    events = normalize_appworld_history(row["history"], True)
    signatures, rejected = [], []
    for index, event in enumerate(events):
        try:
            signature = canonical_operation_signature(registry, event.operation, event.input_slots)
        except ValueError as exc:
            rejected.append({"index": index, "operation": event.operation, "reason": str(exc)})
        else:
            signatures.append({"index": index, "signature": signature,
                               "observed": bool(event.observed and event.check)})

    # Enumerate direct ordered public read/write paths.  This is a diagnostic
    # query over a registry already frozen without run evidence; it neither
    # mutates state nor labels any path a task solution.
    candidates = []
    for left_pos, left in enumerate(signatures):
        if not left["observed"]:
            continue
        for right in signatures[left_pos + 1:]:
            if not right["observed"]:
                continue
            audit = public_tool_path_audit(registry, [left["signature"], right["signature"]])
            if audit["passed"]:
                candidates.append({"event_indices": [left["index"], right["index"]],
                                   "operations": [left["signature"]["operation"], right["signature"]["operation"]],
                                   "path_sha256": audit["path_sha256"]})
    candidates.sort(key=lambda item: (item["event_indices"], item["path_sha256"]))
    return {"artifact_sha256": _sha(artifact), "history_sha256": row.get("history_sha256"),
            "normalized_event_count": len(events), "recognized": bool(candidates),
            "candidate_paths": candidates, "rejected_operations": rejected,
            "public_signatures": [{"index": item["index"], "operation": item["signature"]["operation"],
                                    "public_required": item["signature"]["public_required"],
                                    "public_optional_present": item["signature"]["public_optional_present"],
                                    "runtime_context_present": item["signature"]["runtime_context_present"],
                                    "observed": item["observed"]} for item in signatures]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    registry = _load(args.registry)
    verify_public_tool_schema_registry(registry)  # freeze/verify before evidence access
    artifacts = sorted((args.run / "evaluation" / "copromem_dynamic").glob("**/trial-*.json"))
    result = {"audit_version": "v5_3_tool_schema_retrospective_v1", "provider_calls": 0,
              "registry_sha256": registry["registry_sha256"], "registry_frozen_before_history_read": True,
              "run_label": args.run.name, "artifact_count": len(artifacts),
              "artifacts": [_rows(registry, artifact) for artifact in artifacts]}
    result["all_artifacts_recognized"] = bool(artifacts) and all(item["recognized"] for item in result["artifacts"])
    result["audit_sha256"] = canonical_digest(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"registry_sha256": result["registry_sha256"], "artifacts": len(artifacts),
                      "all_recognized": result["all_artifacts_recognized"], "audit_sha256": result["audit_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
