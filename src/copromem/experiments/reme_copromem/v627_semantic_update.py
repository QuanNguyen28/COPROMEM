"""v6.2.7-only scalable semantic-spine task update.

This keeps the v6.1/v6.2.2 executable common core immutable.  The output
contract is the ordinary semantic-spine update; only projection edge indexing
differs, so dense response-attested evidence remains feasible to validate.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ...benchmarks.appworld.execution_evidence import (
    journal_records,
    partition_v6_graph_evidence,
    runtime_context_fields,
)
from ...semantic_graph_v627 import build_semantic_graph
from ...semantic_spine_v622 import commit, plan, validate
from .contrastive_v6_runner import (
    SEMANTIC_STATE_FORMAT,
    scorer_evidence_sha256,
    semantic_spine_state_compatibility,
)


def semantic_spine_task_batch_update_v627(*, artifacts: list[Mapping[str, Any]],
                                           registry: Mapping[str, Any],
                                           pre_state: Mapping[str, Any],
                                           evidence_paths: list[str | Path],
                                           run_root: Path,
                                           discard_schema_invalid_reads: bool = False,
                                           discard_schema_invalid_unsuccessful_calls: bool = False,
                                           ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Produce the standard semantic-spine state/audit with scalable projection."""
    if len(artifacts) != len(evidence_paths) or len(artifacts) < 2:
        raise ValueError("complete same-task semantic-spine batch required")
    compatibility = semantic_spine_state_compatibility(pre_state)
    if compatibility is None:
        raise ValueError("raw v6 state cannot enter a semantic-spine bank")
    semantic_graphs: list[tuple[Any, bool]] = []
    audits: list[dict[str, Any]] = []
    for artifact, evidence_path in zip(artifacts, evidence_paths):
        scorer_evidence_sha256(artifact)
        from .evidence_contract import validate as validate_execution_evidence
        validate_execution_evidence(artifact, run_root=run_root,
                                    expected_registry_sha256=str(registry["registry_sha256"]))
        partition, ingestion = partition_v6_graph_evidence(
            journal_records(evidence_path), str(registry["registry_sha256"]),
            runtime_context_fields=runtime_context_fields(registry),
            discard_schema_invalid_reads=discard_schema_invalid_reads,
            discard_schema_invalid_unsuccessful_calls=discard_schema_invalid_unsuccessful_calls,
        )
        graph, projection = build_semantic_graph(partition, registry)
        semantic_graphs.append((graph, float(artifact["after_score"]) == 1.0))
        audits.append({"artifact_trajectory_id": artifact.get("trajectory_id"),
                       "original_graph_sha256": projection["original_graph_sha256"],
                       "semantic_projection_sha256": projection["semantic_projection_sha256"],
                       "projection": projection, "ingestion": ingestion})
    success = [graph for graph, good in semantic_graphs if good]
    failed = [graph for graph, good in semantic_graphs if not good]
    plan_record = plan(success, failed, pre_state, [item["projection"] for item in audits])
    validation = validate(plan_record, registry)
    post, marker = commit(pre_state, plan_record, validation)
    if marker["state"] == "committed":
        post = {**post, "state_format": SEMANTIC_STATE_FORMAT}
        from ...contrastive_graph_v6 import digest
        marker = {**marker, "post_state_sha256": digest(post)}
    if marker["state"] == "rejected" and post != dict(pre_state):
        raise ValueError("semantic-spine rejection mutated state")
    from ...contrastive_graph_v6 import digest
    audit = {
        "state_format": SEMANTIC_STATE_FORMAT,
        "semantic_policy_version": "copromem-v6.2.2-attested-semantic-spine-v1",
        "pre_state_format": pre_state.get("state_format"),
        "pre_state_compatibility": compatibility,
        "pre_state_sha256": digest(pre_state),
        "semantic_graph_audits": audits,
        "plan": plan_record,
        "validation": validation,
        "marker": marker,
        "post_state_sha256": digest(post),
    }
    return post, marker, audit
