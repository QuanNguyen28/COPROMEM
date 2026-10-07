"""V6 task-batch lifecycle; intentionally never imports the v5.3 planner."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Mapping
from ...benchmarks.appworld.execution_evidence import journal_records, partition_v6_graph_evidence, runtime_context_fields
from ...contrastive_graph_v6 import build_graph, commit, digest, plan_task_batch, reproduce_retrieval, retrieve, validate_plan
from ...semantic_graph_v61 import (POLICY_VERSION as SEMANTIC_POLICY_VERSION, build_semantic_graph,
                                   semantic_plan, validate_semantic_plan)
from ...semantic_spine_v622 import (POLICY_VERSION as SEMANTIC_SPINE_POLICY_VERSION,
                                    SCHEMA_CONTRACT_VERSION as SEMANTIC_SPINE_SCHEMA_CONTRACT_VERSION,
                                    commit as commit_semantic_spine,
                                    plan as plan_semantic_spine,
                                    validate as validate_semantic_spine)
from .evidence_contract import SCORER, validate as validate_execution_evidence

STATE_FORMAT = "copromem-v6-contrastive-state-v1"
SEMANTIC_STATE_FORMAT = "copromem-v6.1-semantic-state-v1"


class SemanticBatchEvidenceError(ValueError):
    """A scored artifact lacks the evidence identity required for batch state."""


def scorer_evidence_sha256(artifact: Mapping[str, Any]) -> str:
    """Return the one canonical scorer-evidence identity for a scored artifact.

    Ordinary trajectories use the standard scorer binding.  A genuine
    zero-action termination instead has the stricter, versioned zero-action
    attestation, which carries its own scorer hash.  This is an explicit
    schema normalization, not a fabricated default: any other shape fails
    before a semantic plan or checkpoint is written.
    """
    ordinary = artifact.get(SCORER)
    if isinstance(ordinary, Mapping) and isinstance(ordinary.get("sha256"), str) and ordinary["sha256"]:
        return str(ordinary["sha256"])
    zero = artifact.get("zero_action_evidence")
    if (int(artifact.get("actions", -1)) == 0 and isinstance(zero, Mapping)
            and zero.get("version") == "canonical-zero-action-evidence-v1"
            and isinstance(zero.get("scorer_evidence_sha256"), str)
            and zero["scorer_evidence_sha256"]):
        return str(zero["scorer_evidence_sha256"])
    raise SemanticBatchEvidenceError("semantic batch requires ordinary or canonical zero-action scorer evidence")

def fresh_state() -> dict[str, Any]:
    return {"state_format": STATE_FORMAT, "contrastive_v6_schemas": {}}


def semantic_state_compatibility(state: Mapping[str, Any]) -> str | None:
    """Return the accepted semantic-bank representation, or ``None``.

    The immutable v6.1 recovery wrote semantic-projection schemas into the
    original v6 container format.  That representation is semantically
    equivalent to the later explicit v6.1 state format, but an arbitrary raw
    v6 state is not.  Accept only that narrow, content-proven legacy form so
    a runner cannot silently feed an ordinary raw v6 bank to the semantic
    lifecycle.
    """
    state_format = state.get("state_format")
    if state_format in {None, SEMANTIC_STATE_FORMAT}:
        return "explicit_semantic"
    if state_format != STATE_FORMAT:
        return None
    schemas = state.get("contrastive_v6_schemas")
    if not isinstance(schemas, Mapping) or not schemas:
        return None
    if all(isinstance(schema, Mapping)
           and schema.get("policy_version") == SEMANTIC_POLICY_VERSION
           and isinstance(schema.get("semantic_projection_hashes"), list)
           and isinstance(schema.get("semantic_provenance_hashes"), list)
           for schema in schemas.values()):
        return "legacy_v61_semantic_content"
    return None


def semantic_spine_state_compatibility(state: Mapping[str, Any]) -> str | None:
    """Recognize only an admitted v6.2.2 semantic-spine bank.

    v6.2.2 intentionally keeps the legacy ``contrastive_v6_schemas``
    container so its fixed bank has a stable, content-addressed format.  That
    does *not* make an arbitrary raw-v6 state eligible for the v6.2.2 update
    lifecycle.  The distinguishing evidence is that every persisted schema
    carries the v6.2.2 occurrence/dataflow contract.

    Keep this predicate separate from :func:`semantic_state_compatibility`:
    accepting a v6.2.2 state in the v6.1 lifecycle would silently mix two
    methods, while rejecting it here prevents the admitted fixed bank from
    ever receiving its first Dynamic update.
    """
    state_format = state.get("state_format")
    if state_format not in {STATE_FORMAT, SEMANTIC_STATE_FORMAT}:
        return None
    schemas = state.get("contrastive_v6_schemas")
    if not isinstance(schemas, Mapping) or not schemas:
        return None
    def spine(schema: Any) -> bool:
        return (isinstance(schema, Mapping)
                and schema.get("policy_version") == SEMANTIC_SPINE_POLICY_VERSION
                and schema.get("schema_contract_version") == SEMANTIC_SPINE_SCHEMA_CONTRACT_VERSION
                and isinstance(schema.get("occurrences"), list)
                and bool(schema["occurrences"])
                and isinstance(schema.get("terminal_occurrence_ids"), list)
                and bool(schema["terminal_occurrence_ids"]))

    def legacy_semantic(schema: Any) -> bool:
        return (isinstance(schema, Mapping)
                and schema.get("policy_version") == SEMANTIC_POLICY_VERSION
                and isinstance(schema.get("semantic_projection_hashes"), list)
                and isinstance(schema.get("semantic_provenance_hashes"), list))

    values = list(schemas.values())
    if all(spine(schema) for schema in values):
        return "v622_semantic_spine_content"
    # The v6.1 schemas are immutable prefix history.  Only a bank that also
    # contains at least one attested v6.2.2 schema may continue through the
    # v6.2.2 lifecycle; raw and v6.1-only banks remain rejected.
    if any(spine(schema) for schema in values) and all(spine(schema) or legacy_semantic(schema) for schema in values):
        return "v622_spine_with_legacy_v61_prefix"
    return None
def plan_task_batch_from_artifacts(*, artifacts: list[Mapping[str, Any]], registry: Mapping[str, Any], pre_state: Mapping[str, Any], evidence_paths: list[str | Path]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the pure v6 plan from durable, scored public evidence only."""
    if len(artifacts) != len(evidence_paths) or any("after_score" not in item for item in artifacts):
        raise ValueError("complete scored batch and evidence paths required")
    partitions = [partition_v6_graph_evidence(journal_records(path), str(registry["registry_sha256"]),
                                               runtime_context_fields=runtime_context_fields(registry)) for path in evidence_paths]
    graphs = [build_graph(rows, registry) for rows, _ in partitions]
    success = [graph for graph, item in zip(graphs, artifacts) if float(item["after_score"]) == 1.0]
    failed = [graph for graph, item in zip(graphs, artifacts) if float(item["after_score"]) != 1.0]
    plan = plan_task_batch(success, failed, pre_state)
    audit = {"state_format": STATE_FORMAT, "pre_state_sha256": digest(pre_state),
             "graph_hashes": [graph.sha256 for graph in graphs], "plan_sha256": plan["plan_sha256"],
             "success_count": len(success), "failure_count": len(failed), "ingestion_audits": [audit for _, audit in partitions]}
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


def semantic_task_batch_update(*, artifacts: list[Mapping[str, Any]], registry: Mapping[str, Any],
                               pre_state: Mapping[str, Any], evidence_paths: list[str | Path],
                               run_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """v6.1 semantic contrastive update over fully scorer-bound artifacts only."""
    if len(artifacts) != len(evidence_paths) or len(artifacts) < 2:
        raise ValueError("complete same-task semantic batch required")
    compatibility = semantic_state_compatibility(pre_state)
    if compatibility is None:
        raise ValueError("raw v6 state cannot enter a v6.1 semantic bank")
    semantic_graphs=[]; audits=[]
    for artifact, evidence_path in zip(artifacts, evidence_paths):
        scorer_evidence_sha256(artifact)
        validate_execution_evidence(artifact, run_root=run_root, expected_registry_sha256=str(registry["registry_sha256"]))
        records = journal_records(evidence_path)
        partition, ingestion = partition_v6_graph_evidence(records, str(registry["registry_sha256"]),
            runtime_context_fields=runtime_context_fields(registry))
        graph, projection = build_semantic_graph(partition, registry)
        semantic_graphs.append((graph, float(artifact["after_score"]) == 1.0))
        audits.append({"artifact_trajectory_id":artifact.get("trajectory_id"), "original_graph_sha256": projection["original_graph_sha256"],
                       "semantic_projection_sha256":projection["semantic_projection_sha256"], "projection":projection,
                       "ingestion":ingestion})
    success=[graph for graph, good in semantic_graphs if good]; failed=[graph for graph, good in semantic_graphs if not good]
    plan=semantic_plan(success, failed, pre_state, [item["projection"] for item in audits])
    validation=validate_semantic_plan(plan, registry)
    post, marker=commit(pre_state, plan)
    if marker["state"] == "committed":
        post={**post,"state_format":SEMANTIC_STATE_FORMAT}
        marker={**marker,"post_state_sha256":digest(post),"semantic_policy_version":SEMANTIC_POLICY_VERSION}
    audit={"state_format":SEMANTIC_STATE_FORMAT,"semantic_policy_version":SEMANTIC_POLICY_VERSION,
           "pre_state_format":pre_state.get("state_format"), "pre_state_compatibility":compatibility,
           "pre_state_sha256":digest(pre_state),"semantic_graph_audits":audits,"plan":plan,"validation":validation,
           "marker":marker,"post_state_sha256":digest(post)}
    if marker["state"] == "rejected" and post != dict(pre_state):
        raise ValueError("semantic rejection mutated state")
    return post, marker, audit


def semantic_spine_task_batch_update(*, artifacts: list[Mapping[str, Any]], registry: Mapping[str, Any],
                                     pre_state: Mapping[str, Any], evidence_paths: list[str | Path],
                                     run_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """v6.2.2 update whose commit is gated by occurrence-level semantics."""
    if len(artifacts) != len(evidence_paths) or len(artifacts) < 2:
        raise ValueError("complete same-task semantic-spine batch required")
    compatibility = semantic_spine_state_compatibility(pre_state)
    if compatibility is None:
        raise ValueError("raw v6 state cannot enter a semantic-spine bank")
    semantic_graphs: list[tuple[Any, bool]] = []
    audits: list[dict[str, Any]] = []
    for artifact, evidence_path in zip(artifacts, evidence_paths):
        scorer_evidence_sha256(artifact)
        validate_execution_evidence(artifact, run_root=run_root,
                                    expected_registry_sha256=str(registry["registry_sha256"]))
        partition, ingestion = partition_v6_graph_evidence(
            journal_records(evidence_path), str(registry["registry_sha256"]),
            runtime_context_fields=runtime_context_fields(registry))
        graph, projection = build_semantic_graph(partition, registry)
        semantic_graphs.append((graph, float(artifact["after_score"]) == 1.0))
        audits.append({"artifact_trajectory_id": artifact.get("trajectory_id"),
                       "original_graph_sha256": projection["original_graph_sha256"],
                       "semantic_projection_sha256": projection["semantic_projection_sha256"],
                       "projection": projection, "ingestion": ingestion})
    success = [graph for graph, good in semantic_graphs if good]
    failed = [graph for graph, good in semantic_graphs if not good]
    plan_record = plan_semantic_spine(success, failed, pre_state,
                                     [item["projection"] for item in audits])
    validation = validate_semantic_spine(plan_record, registry)
    post, marker = commit_semantic_spine(pre_state, plan_record, validation)
    if marker["state"] == "committed":
        post = {**post, "state_format": SEMANTIC_STATE_FORMAT}
        marker = {**marker, "post_state_sha256": digest(post)}
    if marker["state"] == "rejected" and post != dict(pre_state):
        raise ValueError("semantic-spine rejection mutated state")
    audit = {"state_format": SEMANTIC_STATE_FORMAT,
             "semantic_policy_version": SEMANTIC_SPINE_POLICY_VERSION,
             "pre_state_format": pre_state.get("state_format"),
             "pre_state_compatibility": compatibility,
             "pre_state_sha256": digest(pre_state), "semantic_graph_audits": audits,
             "plan": plan_record, "validation": validation, "marker": marker,
             "post_state_sha256": digest(post)}
    return post, marker, audit

def retrieval_record(*, state: Mapping[str, Any], query_operations: list[str], registry_sha256: str,
                     task_query: Mapping[str, Any] | None = None,
                     callable_registry: Mapping[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    """Return the legacy v6 retrieval record.

    ``callable_registry`` is deliberately accepted as a no-op compatibility
    seam.  Versioned runners can use the same call boundary while selecting a
    stricter, separately registered retrieval implementation; the legacy v6
    predicate continues to depend only on its frozen registry digest.
    """
    del callable_registry
    guidance, provenance = retrieve(state, query_operations, registry_sha256)
    if guidance != reproduce_retrieval(state, query_operations, provenance):
        raise ValueError("v6 guidance is not reproducible")
    if task_query is not None:
        if task_query.get("callable_registry_sha256") != registry_sha256 or list(task_query.get("query_operations", [])) != list(query_operations):
            raise ValueError("retrieval query does not match task-query record")
        provenance = {**provenance, "task_query": dict(task_query),
                      "task_query_sha256": str(task_query.get("query_sha256") or "")}
    return guidance, provenance
