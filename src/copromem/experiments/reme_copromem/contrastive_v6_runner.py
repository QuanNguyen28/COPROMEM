"""V6 task-batch lifecycle; intentionally never imports the v5.3 planner."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Mapping
from ...benchmarks.appworld.execution_evidence import journal_records
from ...contrastive_graph_v6 import build_graph, commit, digest, plan_task_batch, reproduce_retrieval, retrieve

STATE_FORMAT = "copromem-v6-contrastive-state-v1"

def fresh_state() -> dict[str, Any]:
    return {"state_format": STATE_FORMAT, "contrastive_v6_schemas": {}}

def task_batch_update(*, artifacts: list[Mapping[str, Any]], registry: Mapping[str, Any], pre_state: Mapping[str, Any], evidence_paths: list[str | Path]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if len(artifacts) != len(evidence_paths) or any("after_score" not in item for item in artifacts):
        raise ValueError("complete scored batch and evidence paths required")
    graphs = [build_graph(journal_records(path), registry) for path in evidence_paths]
    success = [graph for graph, item in zip(graphs, artifacts) if float(item["after_score"]) == 1.0]
    failed = [graph for graph, item in zip(graphs, artifacts) if float(item["after_score"]) != 1.0]
    plan = plan_task_batch(success, failed, pre_state)
    post, marker = commit(pre_state, plan)
    audit = {"state_format": STATE_FORMAT, "pre_state_sha256": digest(pre_state), "post_state_sha256": digest(post),
             "graph_hashes": [graph.sha256 for graph in graphs], "plan_sha256": plan["plan_sha256"], "marker": marker}
    return post, marker, audit

def retrieval_record(*, state: Mapping[str, Any], query_operations: list[str], registry_sha256: str) -> tuple[str, dict[str, Any]]:
    guidance, provenance = retrieve(state, query_operations, registry_sha256)
    if guidance != reproduce_retrieval(state, query_operations, provenance):
        raise ValueError("v6 guidance is not reproducible")
    return guidance, provenance
