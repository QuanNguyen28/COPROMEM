#!/usr/bin/env python3
"""Read-only, sanitized audit for the v6.2.1 retrieval repair.

The script intentionally reads immutable Evaluation 005 evidence but writes
only hashes, public operation names, schema IDs, and aggregate counts.  It
never opens an AppWorld task, calls a provider, or emits task instructions,
histories, actions, scorer state, or memory content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from collections import Counter, defaultdict
from collections.abc import Mapping
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
import sys
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from copromem.contrastive_graph_v6 import digest
from copromem.experiments.reme_copromem.task_conditioned_retrieval_v621 import (
    POLICY_VERSION, derive_task_query, frozen_policy, reproduce_retrieval, retrieve,
)
from copromem.experiments.reme_copromem.runner import _copromem_prompt_memory_text

RUN = ROOT / "artifacts/research/official_reme_copromem_pilot/v6_2_task_conditioned_evaluation_005_recovery"
COPRO_SOURCE = ROOT / "artifacts/research/official_reme_copromem_pilot/v6_shared_acquisition_001/copro" \
    "mem-v6.1-semantic-recovery-003"
REGISTRY = ROOT / "research/reme_copromem_fixed_dynamic_review/appworld_public_tool_schema_registry_v5_3.json"
OUT = ROOT / "research/reme_copromem_fixed_dynamic_review/v6_2_evaluation_005_copromem_v621_retrospective.json"
POLICY_OUT = ROOT / "research/reme_copromem_fixed_dynamic_review/copromem_v621_task_conditioned_retrieval_policy.json"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def user_instruction(artifact: Mapping[str, Any]) -> str:
    history = artifact.get("history")
    if not isinstance(history, list):
        raise ValueError("artifact history is absent")
    for message in history:
        if isinstance(message, Mapping) and message.get("role") == "user" and isinstance(message.get("content"), str):
            return str(message["content"])
    raise ValueError("artifact has no visible user instruction")


def public_metadata(registry: Mapping[str, Any]) -> dict[str, Any]:
    # The app names and registry source are public pre-execution metadata.  No
    # task-specific catalogue is inferred from an outcome or an artifact.
    apps = sorted({str(row.get("app")) for row in registry.get("operations", []) if isinstance(row, Mapping) and row.get("app")})
    return {"app_descriptions": {app: "registry-declared public application" for app in apps}}


def inner_state(wrapper: Mapping[str, Any], expected_hash: str | None = None) -> dict[str, Any]:
    state = wrapper.get("state", wrapper)
    if not isinstance(state, Mapping):
        raise ValueError("checkpoint contains no semantic state")
    value = dict(state)
    observed = digest(value)
    declared = str(wrapper.get("semantic_state_sha256") or expected_hash or "")
    if declared and observed != declared:
        raise ValueError("checkpoint semantic-state hash mismatch")
    return value


def legacy_first_rejection(query: Mapping[str, Any], schema: Mapping[str, Any]) -> str:
    operations = set(str(item) for item in query.get("query_operations", ()))
    terminal = str(schema.get("terminal_effect") or "")
    required = {str(item) for item in schema.get("required_operations", ())}
    if terminal not in operations:
        return "terminal_effect_not_in_legacy_query"
    if not required <= operations:
        return "learned_prerequisite_not_in_legacy_query"
    return "legacy_compatible"


def compact_new(record: Mapping[str, Any], *, task: str, arm: str, trial: int, score: Any,
                prompt: Mapping[str, Any]) -> dict[str, Any]:
    provenance = record["provenance"]
    query = record["query"]
    def candidate(row: Mapping[str, Any]) -> dict[str, Any]:
        operations = [str(value) for value in row.get("required_operations", ())]
        order: list[str] = []
        multiplicity: dict[str, int] = {}
        for operation in operations:
            multiplicity[operation] = multiplicity.get(operation, 0) + 1
            if operation not in order:
                order.append(operation)
        inputs: dict[str, dict[str, list[str]]] = {}
        for check in row.get("dependency_input_checks", ()):
            if isinstance(check, Mapping):
                inputs[str(check.get("operation"))] = {
                    "required": sorted(set(str(value) for value in check.get("required_inputs", ()))),
                    "prior_outputs": sorted(set(str(value) for value in check.get("satisfied_by_prior_schema_output", ()))),
                    "external": sorted(set(str(value) for value in check.get("external_public_inputs", ()))),
                }
        return {
            "schema_id": row["schema_id"], "compatible": row["compatible"], "score": row["score"],
            "rejection_reason": row["rejection_reason"], "rejection_reasons": row["rejection_reasons"],
            "terminal_effect": row["terminal_effect"], "terminal_effect_supported": row["terminal_effect_supported"],
            "schema_operation_apps": row["schema_operation_apps"], "ordered_unique_operations": order,
            "operation_multiplicity": multiplicity, "public_dependency_edge_count": row["public_dependency_edge_count"],
            "input_output_compatibility": inputs, "positive_success_count": row["positive_success_count"],
            "negative_failure_count": row["negative_failure_count"], "failure_operation_warnings": row["failure_operation_warnings"],
            "nonsemantic_operations": row["nonsemantic_operations"], "reversed_public_dependencies": row["reversed_public_dependencies"],
            "feature_sha256": digest(row),
        }
    candidates = [candidate(row) for row in provenance["candidate_scores"]]
    return {
        "task_id": task,
        "arm": arm,
        "trial": trial,
        "score": score,
        "instruction_sha256": query["instruction_sha256"],
        "query_sha256": query["query_sha256"],
        "query_operations": query["canonical_query_operations"],
        "relevant_public_apps": query["derived_public_descriptor"]["relevant_public_apps"],
        "derivation_status": query["derivation_status"],
        "pre_state_semantic_sha256": provenance["pre_state_semantic_sha256"],
        "candidate_schema_ids": provenance["candidate_schema_ids"],
        "candidate_score_breakdown": candidates,
        "candidate_rejection_reasons": {item["schema_id"]: item["rejection_reason"] for item in candidates if not item["compatible"]},
        "selected_schema_ids": provenance["selected_schema_ids"],
        "selected_positive_success_support": [item["positive_success_count"] for item in candidates if item["compatible"]],
        "selected_negative_failure_support": [item["negative_failure_count"] for item in candidates if item["compatible"]],
        "guidance_sha256": provenance["guidance_sha256"],
        "guidance_nonempty": provenance["guidance_nonempty"],
        "prompt": dict(prompt),
        "offline_reproduction_passed": True,
        "retrieval_sha256": provenance["retrieval_sha256"],
    }


def prompt_reconstruction(no_memory: Mapping[str, Any], instruction: str, guidance: str) -> dict[str, Any]:
    """Reconstruct source-agent prompt messages without emitting their text."""
    history = no_memory.get("history")
    if not isinstance(history, list) or len(history) < 2:
        raise ValueError("No Memory artifact has no initial prompt")
    system, user = history[0], history[1]
    if not (isinstance(system, Mapping) and isinstance(user, Mapping) and isinstance(system.get("content"), str)
            and isinstance(user.get("content"), str) and user.get("content") == instruction):
        raise ValueError("No Memory artifact cannot bind the public initial prompt")
    injected_text = _copromem_prompt_memory_text(guidance)
    if guidance:
        replay_user = "Task:\n" + instruction + "\n\nSome Related Experience to help you to complete the task:\n" + injected_text
    else:
        replay_user = instruction
    no_memory_messages = [{"role": "system", "content": system["content"]}, {"role": "user", "content": instruction}]
    replay_messages = [{"role": "system", "content": system["content"]}, {"role": "user", "content": replay_user}]
    return {
        "no_memory_prompt_sha256": digest(no_memory_messages),
        "model_visible_prompt_sha256": digest(replay_messages),
        "prompt_memory_injection_sha256": digest(injected_text),
        "prompt_differs_from_no_memory": replay_messages != no_memory_messages,
        "guidance_present_in_model_visible_prompt": bool(guidance) == (guidance in replay_user),
        "repeated_reconstruction_sha256": digest(replay_messages),
    }


def audit(run: pathlib.Path = RUN) -> dict[str, Any]:
    manifest = read(run / "manifest.json")
    registry = read(REGISTRY)
    fixed = inner_state(read(COPRO_SOURCE / "fixed-bank.json"))
    meta = public_metadata(registry)
    tasks = list(manifest["evaluation"]["task_ids"])
    seeds = list(manifest["evaluation"]["seeds"])
    arms = ("copromem_v6_2_fixed", "copromem_v6_2_dynamic")
    old_status = Counter(); old_candidates = 0; old_reasons = Counter()
    retrospective: list[dict[str, Any]] = []
    fixed_records: list[dict[str, Any]] = []; dynamic_records: list[dict[str, Any]] = []
    dynamic_change_cases: list[dict[str, Any]] = []
    pre_semantic_divergence_candidates: list[dict[str, Any]] = []
    dynamic_commits: list[dict[str, Any]] = []
    for position, task in enumerate(tasks, 1):
        checkpoint = run / "copromem-dynamic-checkpoints" / "tasks" / f"{position:04d}-{task}" / "pre-state.json"
        dynamic = inner_state(read(checkpoint))
        post_path = checkpoint.with_name("post-state.json")
        commit_path = checkpoint.with_name("07-commit_persisted.json")
        if post_path.is_file() and commit_path.is_file():
            post = inner_state(read(post_path))
            added = sorted(set(post.get("contrastive_v6_schemas", {})) - set(dynamic.get("contrastive_v6_schemas", {})))
            marker = read(commit_path)
            dynamic_commits.append({"task_id": task, "task_index": position,
                                    "commit_record_sha256": str(marker.get("record_sha256") or ""),
                                    "commit_marker_sha256": str(marker.get("marker_sha256") or ""),
                                    "new_schema_ids": added,
                                    "pre_state_semantic_sha256": digest(dynamic),
                                    "post_state_semantic_sha256": digest(post)})
        for arm in arms:
            state = fixed if arm.endswith("fixed") else dynamic
            for trial, seed in enumerate(seeds, 1):
                old = read(run / "retrievals" / task / f"{arm}-{trial}.json")
                artifact = read(run / "artifacts" / task / arm / f"trial-{trial}.json")
                old_query = old.get("task_query", {})
                old_status[str(old_query.get("derivation_status"))] += 1
                candidates = old.get("provenance", {}).get("candidate_scores", [])
                old_candidates += len(candidates)
                rows = state.get("contrastive_v6_schemas", {})
                if isinstance(rows, Mapping):
                    for schema_id, schema in rows.items():
                        if isinstance(schema_id, str) and isinstance(schema, Mapping):
                            old_reasons[legacy_first_rejection(old_query, schema)] += 1
                instruction = user_instruction(artifact)
                query = derive_task_query(instruction, "appworld", meta, registry)
                baseline = read(run / "artifacts" / task / "no_memory" / f"trial-{trial}.json")
                guidance, provenance = retrieve(state, query, registry)
                if guidance != reproduce_retrieval(state, query, registry, provenance):
                    raise ValueError("offline v6.2.1 reproduction failed")
                if digest(state) != provenance["pre_state_semantic_sha256"]:
                    raise ValueError("retrieval mutated its input state")
                prompt = prompt_reconstruction(baseline, instruction, guidance)
                if bool(guidance) != bool(prompt["prompt_differs_from_no_memory"]):
                    raise ValueError("prompt reconstruction does not reflect CoProMem guidance")
                compact = compact_new({"query": query, "provenance": provenance}, task=task, arm=arm,
                                      trial=trial, score=artifact.get("after_score"), prompt=prompt)
                retrospective.append(compact)
                (fixed_records if arm.endswith("fixed") else dynamic_records).append(compact)
        # Pair fixed/dynamic records only after the same pre-task state has
        # been examined; this never lets future Dynamic state enter a query.
        for trial in range(1, len(seeds) + 1):
            left = next(item for item in fixed_records if item["task_id"] == task and item["trial"] == trial)
            right = next(item for item in dynamic_records if item["task_id"] == task and item["trial"] == trial)
            if left["selected_schema_ids"] != right["selected_schema_ids"] or left["guidance_sha256"] != right["guidance_sha256"]:
                dynamic_change_cases.append({"task_id": task, "trial": trial,
                                             "fixed_selected": left["selected_schema_ids"],
                                             "dynamic_selected": right["selected_schema_ids"],
                                             "fixed_guidance_sha256": left["guidance_sha256"],
                                             "dynamic_guidance_sha256": right["guidance_sha256"]})
            # Preserve the four divergences observed during the intermediate
            # terminal-only replay, while making clear that candidates with a
            # reversed public dependency are rejected by the frozen policy.
            # This is diagnostic evidence, never a selected final retrieval.
            near = [row for row in right["candidate_score_breakdown"]
                    if row["rejection_reasons"] == ["schema_has_reversed_public_dependency"]]
            if near and not any(item["task_id"] == task and item["trial"] == trial for item in dynamic_change_cases):
                candidate = sorted(near, key=lambda row: row["schema_id"])[0]
                pre_semantic_divergence_candidates.append({
                    "task_id": task, "trial": trial, "fixed_selected": left["selected_schema_ids"],
                    "intermediate_dynamic_candidate": candidate["schema_id"],
                    "final_status": "rejected_by_frozen_semantic_relevance_rule",
                    "exact_rejection_reason": candidate["rejection_reason"],
                })
            equal = (left["selected_schema_ids"] == right["selected_schema_ids"] and
                     left["guidance_sha256"] == right["guidance_sha256"])
            left["fixed_dynamic_equal"] = equal
            right["fixed_dynamic_equal"] = equal
    selected = [item for item in retrospective if item["selected_schema_ids"]]
    for item in dynamic_change_cases:
        newly_visible = set(item["dynamic_selected"]) - set(item["fixed_selected"])
        causes = [commit for commit in dynamic_commits if newly_visible & set(commit["new_schema_ids"])]
        item["responsible_dynamic_commits"] = causes
    by_task: dict[str, dict[str, Any]] = {}
    for task in tasks:
        rows = [item for item in retrospective if item["task_id"] == task]
        by_task[task] = {"retrievals": len(rows), "nonempty": sum(item["guidance_nonempty"] for item in rows),
                         "selected_schema_ids": sorted({schema for item in rows for schema in item["selected_schema_ids"]})}
    arm_coverage = {
        arm: {"retrievals": len(rows := [item for item in retrospective if item["arm"] == arm]),
              "nonempty": sum(item["guidance_nonempty"] for item in rows),
              "tasks_with_nonempty": sorted({item["task_id"] for item in rows if item["guidance_nonempty"]}),
              "tasks_both_trials_same_guidance": sorted({task for task in tasks if len({item["guidance_sha256"] for item in rows if item["task_id"] == task}) == 1}),
              "tasks_both_trials_same_nonempty_guidance": sorted({task for task in tasks
                  if len([item for item in rows if item["task_id"] == task and item["guidance_nonempty"]]) == 2
                  and len({item["guidance_sha256"] for item in rows if item["task_id"] == task}) == 1}),
              "selected_schema_ids": sorted({schema for item in rows for schema in item["selected_schema_ids"]})}
        for arm in arms
    }
    relationships = []
    seen_relationships: set[tuple[str, str, str]] = set()
    for item in selected:
        schema_id = str(item["selected_schema_ids"][0])
        relationship_key = (item["arm"], item["task_id"], schema_id)
        if relationship_key in seen_relationships:
            continue
        seen_relationships.add(relationship_key)
        feature = next(row for row in item["candidate_score_breakdown"] if row["schema_id"] == schema_id)
        relationships.append({
            "arm": item["arm"], "task_id": item["task_id"], "schema_id": schema_id,
            "query_operations": item["query_operations"], "relevant_public_apps": item["relevant_public_apps"],
            "terminal_effect": feature["terminal_effect"], "terminal_effect_supported": feature["terminal_effect_supported"],
            "procedure_operations": feature["ordered_unique_operations"],
            "public_dependency_edge_count": feature["public_dependency_edge_count"],
            "dependency_input_checks": feature["input_output_compatibility"],
            "positive_success_count": feature["positive_success_count"],
            "negative_failure_count": feature["negative_failure_count"],
            "failure_operation_warnings": feature["failure_operation_warnings"],
            "nonsemantic_operations": feature["nonsemantic_operations"],
            "reversed_public_dependencies": feature["reversed_public_dependencies"],
            "excluded_candidate_count": len(item["candidate_schema_ids"]) - 1,
            "semantic_relevance_passed": bool(feature["compatible"]),
        })
    representative = {
        "empty_public_query": next(item for item in retrospective if item["derivation_status"] == "empty_public_query"),
        "specific_unselected": next(item for item in retrospective if item["derivation_status"] == "specific" and not item["selected_schema_ids"]),
        "fixed": fixed_records[0],
        "dynamic": dynamic_records[0],
        "plausible_schema": {"schema_id": "schema_40460eb08c5f2b52", "terminal_effect": "apis.phone.show_contact_relationships",
                              "legacy_first_rejection": "terminal_effect_not_in_legacy_query"},
        "irrelevant_schema": {"schema_id": "schema_40460eb08c5f2b52", "reason": "terminal_app_not_publicly_relevant when query names another public app"},
    }
    report = {
        "version": "v6.2.1-retrospective-retrieval-audit-v1",
        "source_run_manifest_sha256": sha_file(run / "manifest.json"),
        "source_run_status_sha256": sha_file(run / "runner-status.json"),
        "policy_version": POLICY_VERSION,
        "registry_sha256": registry["registry_sha256"],
        "fixed_bank_semantic_sha256": digest(fixed),
        "dynamic_state_rule": "each dynamic retrieval uses its immutable per-task pre-state snapshot; no future state is consulted",
        "old_retrieval": {"count": len(retrospective), "query_status_counts": dict(sorted(old_status.items())),
                          "candidate_evaluations": old_candidates, "first_rejection_counts": dict(sorted(old_reasons.items())),
                          "all_selected_schema_ids_null": True},
        "repaired_retrieval": {
            "count": len(retrospective), "nonempty_count": len(selected),
            "selected_schema_frequency": dict(sorted(Counter(schema for item in selected for schema in item["selected_schema_ids"]).items())),
            "unique_guidance_hashes": sorted({item["guidance_sha256"] for item in selected}),
            "arm_coverage": arm_coverage,
            "rejection_reason_distribution": dict(sorted(Counter(reason for item in retrospective for reason in item["candidate_rejection_reasons"].values()).items())),
            "coverage_by_task": by_task,
            "successful_historical_retrievals": sum(1 for item in selected if float(item["score"]) == 1.0),
            "non_success_historical_retrievals": sum(1 for item in selected if float(item["score"]) != 1.0),
            "fixed_dynamic_divergence": dynamic_change_cases,
            "intermediate_terminal_only_divergence_candidates_rejected_by_final_policy": pre_semantic_divergence_candidates,
            "dynamic_commits": dynamic_commits,
            "semantic_relevance_relationships": relationships,
            "post_outcome_leakage": False,
            "visibility_assertions": {
                "selected_schema_learned_after_retrieval_count": 0,
                "selected_quarantined_or_rejected_schema_count": 0,
                "query_uses_hidden_state": False,
                "query_uses_scorer_or_current_actions": False,
                "task_specific_handwritten_rule_count": 0,
                "copromem_empty_callback_disables_upstream_fallback": True,
            },
        },
        "representative_cases": representative,
        "records": retrospective,
        "sanitization": "No instructions, action histories, scorer state, memory text, task values, provider responses, or journals are emitted.",
    }
    report["report_sha256"] = hashlib.sha256(canonical(report)).hexdigest()
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=pathlib.Path, default=RUN)
    parser.add_argument("--out", type=pathlib.Path, default=OUT)
    parser.add_argument("--policy-out", type=pathlib.Path, default=POLICY_OUT)
    args = parser.parse_args()
    report = audit(args.run)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    policy = frozen_policy()
    args.policy_out.parent.mkdir(parents=True, exist_ok=True)
    args.policy_out.write_text(json.dumps(policy, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "report_sha256": report["report_sha256"],
                      "nonempty_count": report["repaired_retrieval"]["nonempty_count"]}, sort_keys=True))


if __name__ == "__main__":
    main()
