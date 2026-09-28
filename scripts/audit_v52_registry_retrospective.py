#!/usr/bin/env python3
"""Post-freeze, zero-provider diagnostic for immutable v5.1 run evidence.

The registry is loaded first and its hash is recorded before any history is
read.  This script emits only public operation/slot signatures and artifact
hashes; task text, action code, values, model responses, and scores are never
written to its output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from copromem.benchmarks.appworld.adapter import normalize_appworld_history
from copromem.experiments.reme_copromem.public_path_registry import (
    canonical_digest, observed_public_operation_matches, operation_index, public_path_audit, verify_public_registry,
)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sanitized(event) -> dict:
    return {"operation": event.operation, "input_slots": sorted(event.input_slots),
            "output_slots": sorted(event.output_slots), "parameters": {}}


def _public_signature(event: dict) -> dict:
    inputs = event["input_slots"]
    return {"operation": event["operation"],
            "named_public_inputs": [slot for slot in inputs if slot != "access_token" and not slot.startswith("var_")],
            "local_binding_count": sum(slot.startswith("var_") for slot in inputs + event["output_slots"]),
            "infrastructure_input_present": "access_token" in inputs}


def _paths(registry: dict, events: list[dict]) -> list[dict]:
    index = operation_index(registry)
    results: dict[str, dict] = {}
    for left_index, left in enumerate(events):
        left_meta = index.get(left["operation"])
        if not left_meta or left_meta["access_mode"] != "read":
            continue
        for right_index in range(left_index + 1, len(events)):
            right = events[right_index]; right_meta = index.get(right["operation"])
            if not right_meta or right_meta["access_mode"] != "write":
                continue
            if not (set(left["output_slots"]) & set(right["input_slots"])):
                continue
            audit = public_path_audit(registry, [left, right])
            key = audit["selected_path_sha256"]
            results[key] = {"path_sha256": key, "passed": audit["passed"],
                            "operations": [row["operation"] for row in audit["selected_path"]],
                            "rejection": audit["first_rejection"]}
    return [results[key] for key in sorted(results)]


def _canonical_public_events(registry: dict, events: list[dict]) -> tuple[list[dict], list[dict]]:
    index = operation_index(registry); canonical = []; rejected = []
    for position, event in enumerate(events):
        meta = index.get(event["operation"])
        if meta is None:
            continue
        expected = {"operation": meta["operation"], "input_slots": meta["input_slots"], "output_slots": meta["output_slots"]}
        matched, audit = observed_public_operation_matches(registry, event, expected)
        if matched:
            canonical.append({"operation": meta["operation"], "input_slots": meta["input_slots"],
                              "output_slots": meta["output_slots"], "parameters": {}})
        else:
            rejected.append({"index": position, "operation": event["operation"], "reason": audit.get("reason")})
    return canonical, rejected


def _run(registry: dict, run: Path) -> dict:
    artifacts = sorted((run / "evaluation" / "copromem_dynamic").glob("**/trial-*.json"))
    rows = []
    for artifact in artifacts:
        row = _load(artifact)
        events = normalize_appworld_history(row["history"], float(row.get("after_score", 0.0)) == 1.0)
        public_events = [_sanitized(event) for event in events]
        canonical_events, normalization_rejections = _canonical_public_events(registry, public_events)
        rows.append({"artifact_sha256": _sha(artifact), "history_sha256": row.get("history_sha256"),
                     "normalized_event_signature_sha256": canonical_digest(public_events),
                     "observed_public_signatures": [_public_signature(event) for event in public_events],
                     "canonical_public_signature_sha256": canonical_digest(canonical_events),
                     "normalization_rejections": normalization_rejections,
                     "candidate_paths": _paths(registry, canonical_events)})
    return {"run_label": run.name, "artifact_count": len(rows), "artifacts": rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--run", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    registry = _load(args.registry); verify_public_registry(registry)
    result = {"audit_version": "v5_2_registry_retrospective_audit_v1", "provider_calls": 0,
              "registry_sha256": registry["registry_sha256"],
              "registry_frozen_before_history_read": True, "runs": [_run(registry, path) for path in args.run]}
    result["audit_sha256"] = canonical_digest(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"registry_sha256": result["registry_sha256"], "runs": len(result["runs"]),
                      "audit_sha256": result["audit_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
