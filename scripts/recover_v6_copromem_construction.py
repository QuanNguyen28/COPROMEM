#!/usr/bin/env python3
"""Zero-provider reconstruction of the v6 CoProMem bank from a frozen pool.

The source journal and acquisition artifacts are read-only inputs.  This tool
creates a separately named derived construction record; it never replays an
executor, scorer, decomposition, embedding, or lifecycle request.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from copromem.benchmarks.appworld.execution_evidence import journal_records
from copromem.contrastive_graph_v6 import digest
from copromem.experiments.reme_copromem.contrastive_v6_runner import (
    commit_task_batch,
    fresh_state,
    plan_task_batch_from_artifacts,
    validate_task_batch,
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def rebuild(source_run: Path, output: Path, expected_manifest_sha256: str) -> dict[str, Any]:
    manifest = source_run / "manifest.json"
    if sha256_file(manifest) != expected_manifest_sha256:
        raise RuntimeError("frozen source manifest hash mismatch")
    pool_path = source_run / "shared-pool.json"
    pool = json.loads(pool_path.read_text(encoding="utf-8"))
    records = pool.get("trajectories")
    if not isinstance(records, list) or len(records) != 24:
        raise RuntimeError("frozen shared acquisition pool is incomplete")
    registry_path = ROOT / "research/reme_copromem_fixed_dynamic_review/appworld_public_tool_schema_registry_v5_3.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(registry.get("registry_sha256"), str):
        raise RuntimeError("frozen public callable registry is malformed")

    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    input_rows: list[dict[str, str]] = []
    for record in records:
        artifact = Path(str(record["source_artifact"]))
        evidence = Path(str(record["execution_evidence_path"]))
        if not artifact.is_file() or sha256_file(artifact) != str(record["source_artifact_sha256"]):
            raise RuntimeError("immutable acquisition artifact hash mismatch")
        durable = journal_records(evidence)
        if not durable:
            raise RuntimeError("immutable execution-evidence journal is absent")
        by_task[str(record["task_id"])].append(record)
        input_rows.append({"acquisition_identity": str(record["acquisition_identity"]),
                           "source_artifact_sha256": str(record["source_artifact_sha256"]),
                           "history_sha256": str(record["history_sha256"]),
                           "telemetry_sha256": sha256_file(evidence)})
    if len(by_task) != 12 or any(len(rows) != 2 for rows in by_task.values()):
        raise RuntimeError("frozen pool must contain two trajectories for each of twelve tasks")

    state = fresh_state()
    commits: list[dict[str, Any]] = []
    for task_id in sorted(by_task):
        rows = sorted(by_task[task_id], key=lambda row: str(row["acquisition_identity"]))
        plan, audit = plan_task_batch_from_artifacts(
            artifacts=rows, registry=registry, pre_state=state,
            evidence_paths=[str(row["execution_evidence_path"]) for row in rows],
        )
        validation = validate_task_batch(plan)
        post, marker = commit_task_batch(state, plan)
        item = {
            "task_id": task_id,
            "family": rows[0]["family"],
            "pre_state_sha256": digest(state),
            "plan": plan,
            "plan_sha256": plan["plan_sha256"],
            "audit": audit,
            "validation": validation,
            "marker": marker,
            "post_state_sha256": digest(post),
        }
        write_json(output / "task-batches" / f"{task_id}.json", item)
        if marker["state"] == "committed":
            state = post
            commits.append(item)

    gate = {
        "promoted_schema_count": len(commits),
        "families": sorted({item["family"] for item in commits}),
        "state_sha256": digest(state),
        "passed": len(commits) >= 3 and len({item["family"] for item in commits}) >= 3,
    }
    recovery = {
        "recovery_version": "v6-copromem-construction-recovery-v1",
        "provider_calls": 0,
        "source_manifest_sha256": expected_manifest_sha256,
        "source_shared_pool_sha256": sha256_file(pool_path),
        "registry_sha256": registry["registry_sha256"],
        "registry_file_sha256": sha256_file(registry_path),
        "input_trajectory_count": len(input_rows),
        "input_identity_sha256": digest(sorted(input_rows, key=lambda row: row["acquisition_identity"])),
        "gate": gate,
    }
    recovery["recovery_sha256"] = digest(recovery)
    write_json(output / "initial-bank.json", state)
    write_json(output / "fixed-bank.json", state)
    write_json(output / "dynamic-bank.json", state)
    write_json(output / "gate.json", gate)
    write_json(output / "recovery.json", recovery)
    return recovery


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    result = rebuild(args.source_run, args.output, args.manifest_sha256)
    print(json.dumps({"provider_calls": 0, "recovery_sha256": result["recovery_sha256"], "passed": result["gate"]["passed"],
                      "promoted_schema_count": result["gate"]["promoted_schema_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
