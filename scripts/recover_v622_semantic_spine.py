#!/usr/bin/env python3
"""Zero-provider v6.2.2 bank rebuild from immutable acquisition evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from copromem.benchmarks.appworld.execution_evidence import (journal_records,
    partition_v6_graph_evidence, runtime_context_fields)
from copromem.contrastive_graph_v6 import digest
from copromem.experiments.reme_copromem.contrastive_v6_runner import fresh_state
from copromem.semantic_graph_v61 import build_semantic_graph
from copromem.semantic_spine_v622 import commit, plan, validate


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def rebuild(*, source: Path, source_manifest_sha256: str, registry_path: Path,
            output: Path) -> dict[str, Any]:
    if _sha(source / "manifest.json") != source_manifest_sha256:
        raise RuntimeError("immutable acquisition manifest mismatch")
    pool_path = source / "shared-pool.json"
    pool = json.loads(pool_path.read_text(encoding="utf-8"))["trajectories"]
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in pool:
        by_task[str(row["task_id"])].append(row)
    state = fresh_state(); batches: list[dict[str, Any]] = []
    for task_id in sorted(by_task):
        rows = sorted(by_task[task_id], key=lambda row: row["acquisition_identity"])
        graphs = []; audits = []
        for row in rows:
            partition, ingestion = partition_v6_graph_evidence(
                journal_records(row["execution_evidence_path"]), registry["registry_sha256"],
                runtime_context_fields=runtime_context_fields(registry))
            graph, audit = build_semantic_graph(partition, registry)
            audit["ingestion_audit_sha256"] = digest(ingestion)
            graphs.append(graph); audits.append(audit)
        success = [graph for graph, row in zip(graphs, rows) if float(row["after_score"]) == 1.0]
        failed = [graph for graph, row in zip(graphs, rows) if float(row["after_score"]) != 1.0]
        planned = plan(success, failed, state, audits)
        validation = validate(planned, registry)
        post, marker = commit(state, planned, validation)
        duplicate, duplicate_marker = commit(post, planned, validation)
        item = {"task_id": task_id, "family": rows[0]["family"],
                "source_trajectory_ids": [row["acquisition_identity"] for row in rows],
                "source_history_sha256s": [row["history_sha256"] for row in rows],
                "semantic_graph_sha256s": [graph.sha256 for graph in graphs],
                "plan": planned, "validation": validation, "marker": marker,
                "duplicate_commit_idempotent": (duplicate == post and
                    duplicate_marker.get("winner_schema_id") == marker.get("winner_schema_id")),
                "pre_state_sha256": digest(state), "post_state_sha256": digest(post)}
        _write(output / "task-batches" / f"{task_id}.json", item)
        batches.append(item)
        if marker["state"] == "committed":
            state = post
    committed = [item for item in batches if item["marker"]["state"] == "committed"]
    gate = {"version": "copromem-v6.2.2-bank-admission-v1", "provider_calls": 0,
            "source_manifest_sha256": source_manifest_sha256, "source_pool_sha256": _sha(pool_path),
            "registry_sha256": registry["registry_sha256"], "state_sha256": digest(state),
            "committed_schema_count": len(committed),
            "committed_families": sorted({item["family"] for item in committed}),
            "all_semantic_validations_passed": all(item["validation"]["passed"] for item in committed),
            "all_occurrence_contracts_present": all(item["plan"]["schema"].get("schema_contract_version") == "copromem-occurrence-dataflow-schema-v1" for item in committed),
            "all_terminal_occurrences_explicit": all(bool(item["plan"]["schema"].get("terminal_occurrence_id")) for item in committed),
            "all_duplicate_commits_idempotent": all(item["duplicate_commit_idempotent"] for item in batches)}
    gate["passed"] = bool(len(committed) >= 3 and len(gate["committed_families"]) >= 3
                          and gate["all_semantic_validations_passed"]
                          and gate["all_occurrence_contracts_present"]
                          and gate["all_terminal_occurrences_explicit"]
                          and gate["all_duplicate_commits_idempotent"])
    report = {"method": "copromem-v6.2.2-attested-semantic-spine-v1", "gate": gate,
              "batch_inventory_sha256": digest(batches), "state_sha256": digest(state)}
    report["report_sha256"] = digest(report)
    _write(output / "fixed-bank.json", state); _write(output / "dynamic-bank.json", state)
    _write(output / "semantic-admission-gate.json", gate); _write(output / "recovery-report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--source-manifest-sha256", required=True)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = rebuild(source=args.source.resolve(), source_manifest_sha256=args.source_manifest_sha256,
                     registry_path=args.registry.resolve(), output=args.output.resolve())
    print(json.dumps({"passed": report["gate"]["passed"],
                      "schemas": report["gate"]["committed_schema_count"],
                      "provider_calls": 0, "report_sha256": report["report_sha256"]}, sort_keys=True))
    return 0 if report["gate"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
