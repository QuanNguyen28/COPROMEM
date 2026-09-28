"""V6 task-batch lifecycle; intentionally never imports the v5.3 planner."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Mapping
from ...benchmarks.appworld.execution_evidence import journal_records
from ...contrastive_graph_v6 import build_graph, commit, digest, plan_task_batch, reproduce_retrieval, retrieve, validate_plan

STATE_FORMAT = "copromem-v6-contrastive-state-v1"

def fresh_state() -> dict[str, Any]:
    return {"state_format": STATE_FORMAT, "contrastive_v6_schemas": {}}

def plan_task_batch_from_artifacts(*, artifacts: list[Mapping[str, Any]], registry: Mapping[str, Any], pre_state: Mapping[str, Any], evidence_paths: list[str | Path]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the pure v6 plan from durable, scored public evidence only."""
    if len(artifacts) != len(evidence_paths) or any("after_score" not in item for item in artifacts):
        raise ValueError("complete scored batch and evidence paths required")
    graphs = [build_graph(journal_records(path), registry) for path in evidence_paths]
    success = [graph for graph, item in zip(graphs, artifacts) if float(item["after_score"]) == 1.0]
    failed = [graph for graph, item in zip(graphs, artifacts) if float(item["after_score"]) != 1.0]
    plan = plan_task_batch(success, failed, pre_state)
    audit = {"state_format": STATE_FORMAT, "pre_state_sha256": digest(pre_state),
             "graph_hashes": [graph.sha256 for graph in graphs], "plan_sha256": plan["plan_sha256"],
             "success_count": len(success), "failure_count": len(failed)}
    return plan, audit


def validate_task_batch(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Pure validation kept separate so the dispatcher can durably journal it."""
    return validate_plan(plan)


def commit_task_batch(pre_state: Mapping[str, Any], plan: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pure idempotent transactional commit of a previously persisted plan."""
    return commit(pre_state, plan)


def task_batch_update(*, artifacts: list[Mapping[str, Any]], registry: Mapping[str, Any], pre_state: Mapping[str, Any], evidence_paths: list[str | Path]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Compatibility wrapper for callers that do not need dispatcher checkpoints."""
    plan, audit = plan_task_batch_from_artifacts(artifacts=artifacts, registry=registry, pre_state=pre_state, evidence_paths=evidence_paths)
    post, marker = commit_task_batch(pre_state, plan)
    return post, marker, {**audit, "post_state_sha256": digest(post), "marker": marker}

def retrieval_record(*, state: Mapping[str, Any], query_operations: list[str], registry_sha256: str) -> tuple[str, dict[str, Any]]:
    guidance, provenance = retrieve(state, query_operations, registry_sha256)
    if guidance != reproduce_retrieval(state, query_operations, provenance):
        raise ValueError("v6 guidance is not reproducible")
    return guidance, provenance
