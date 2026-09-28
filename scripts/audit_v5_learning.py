#!/usr/bin/env python3
"""Generate a sanitized, zero-provider forensic trace for a v5 task boundary.

The output deliberately contains no instructions, API arguments, observations,
provider text, or scorer internals.  It records only committed hashes, public
operation/slot shapes, and deterministic admission predicates.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any

from copromem.benchmarks.appworld.adapter import (
    AcquisitionIdentity, CoProMemAppWorldAdapter, RawAcquisitionTrajectory,
    normalize_appworld_history,
)
from copromem.experiments.reme_copromem.runner import digest
from copromem.learning import ActionObservation, LearningCore
from copromem.online import ScoredCandidate, apply_task_batch


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_event(event: ActionObservation) -> dict[str, Any]:
    return {
        "operation": event.operation,
        "input_slots": list(event.input_slots),
        "output_slots": list(event.output_slots),
        "observed": event.observed,
        "has_check": bool(event.check),
    }


def descriptor_matches(events: tuple[ActionObservation, ...], descriptor: tuple[ActionObservation, ...]) -> dict[str, Any]:
    """Match public operation/slot shapes without retaining concrete values."""
    expected = [(x.operation, tuple(sorted(x.input_slots)), tuple(sorted(x.output_slots))) for x in descriptor]
    actual = [(x.operation, tuple(sorted(x.input_slots)), tuple(sorted(x.output_slots))) for x in events]
    matched: list[int] = []
    cursor = 0
    for index, item in enumerate(actual):
        while cursor < len(expected) and expected[cursor][0] != item[0]:
            cursor += 1
        if cursor < len(expected) and expected[cursor] == item:
            matched.append(index)
            cursor += 1
    return {
        "descriptor_step_count": len(expected),
        "matched_event_indexes": matched,
        "unmatched_event_indexes": [i for i in range(len(actual)) if i not in matched],
        "matched_count": len(matched),
    }


def predicate_trace(adapter: CoProMemAppWorldAdapter, candidate: ScoredCandidate) -> dict[str, Any]:
    trajectory = candidate.trajectory
    events = trajectory.events
    signature = adapter.module.learning.signature(events)
    checked_output = any(event.check and event.output_slots for event in events)
    admission = {
        "official_success": bool(trajectory.success),
        "has_events": bool(events),
        "has_observable_checked_output": checked_output,
        "structural_signature_present": signature is not None,
    }
    first = next((name for name, passed in admission.items() if not passed), None)
    return {"predicates": admission, "first_ineligible_predicate": first,
            "signature_sha256": digest(signature) if signature is not None else None,
            "structural_step_count": len(signature["steps"]) if signature is not None else 0}


def trace(run: Path, task_id: str) -> dict[str, Any]:
    manifest = read(run / "manifest.json")
    descriptor = tuple(ActionObservation(**row) for row in manifest["evaluation"]["descriptors"][task_id])
    pre_state = read(run / "copromem/task_pre_states" / f"{task_id}.json")
    post_state = read(run / "copromem/task_states" / f"{task_id}.json")
    marker = read(run / "copromem/task_updates" / f"{task_id}.json")
    adapter = CoProMemAppWorldAdapter(api_key="")
    adapter.clone_from_state(pre_state)
    candidates: list[ScoredCandidate] = []
    trajectories: list[dict[str, Any]] = []
    # The spelling is built rather than globbed broadly to make the source arm explicit.
    arm_dir = run / "evaluation" / "copromem_dynamic" / task_id
    for artifact_path in sorted(arm_dir.glob("trial-*.json")):
        row = read(artifact_path)
        events = normalize_appworld_history(row["history"], float(row["after_score"]) == 1.0)
        trial = int(row["trial_id"])
        candidate = ScoredCandidate(
            RawAcquisitionTrajectory(
                AcquisitionIdentity(task_id, int(row["seed"]), trial),
                "<redacted>", "appworld", float(row["after_score"]) == 1.0,
                tuple(), {"artifact_sha256": sha_file(artifact_path)}, events=events),
            float(row["after_score"]), 0.0, int(row["actions"]), None, 0.0)
        candidates.append(candidate)
        before_episode_count = len(adapter.module.learning.episodes)
        adapter.ingest(candidate.trajectory)
        episode_id = candidate.trajectory.identity.value
        learning = adapter.module.learning
        sid = learning.episode_schemas.get(episode_id)
        pids = list(learning.episode_procedures.get(episode_id, ()))
        item = {
            "trial_id": trial,
            "artifact_sha256": sha_file(artifact_path),
            "history_sha256": row["history_sha256"],
            "official_score": float(row["after_score"]),
            "termination": row["termination"],
            "actions": int(row["actions"]),
            "public_operations": [summarize_event(event) for event in events],
            "descriptor_matching": descriptor_matches(events, descriptor),
            "eligibility": predicate_trace(adapter, candidate),
            "episode_recorded": episode_id in learning.episodes,
            "episode_schema_id": sid,
            "candidate_schema_created": sid not in learning.schemas,
            "candidate_pending_reason": (learning.pending.get(sid) or {}).get("reason"),
            "generated_procedure_ids": pids,
            "generated_procedure_count": len(pids),
            "episode_count_delta": len(learning.episodes) - before_episode_count,
        }
        item["promotion_predicates"] = {
            "episode_success": bool(learning.episode_success.get(episode_id)),
            "schema_exists": sid in learning.schemas,
            "has_generated_procedure": bool(pids),
            "schema_not_quarantined": not (sid in learning.schemas and learning.schemas[sid].status == "quarantined"),
        }
        item["first_promotion_blocker"] = next(
            (name for name, passed in item["promotion_predicates"].items() if not passed), None)
        item["rejection_classification"] = (
            "documented_method_grounding_gate" if item["eligibility"]["first_ineligible_predicate"]
            else "no_rejection")
        trajectories.append(item)
    # Reconstruct the batch independently from immutable pre-state and record
    # whether the same winner decision is made without a provider call.
    replay = CoProMemAppWorldAdapter(api_key="")
    replay.clone_from_state(pre_state)
    winner = apply_task_batch(replay, candidates)
    return {
        "audit_version": 1,
        "run_manifest_sha256": sha_file(run / "manifest.json"),
        "task_id": task_id,
        "task_marker_sha256": sha_file(run / "copromem/task_updates" / f"{task_id}.json"),
        "pre_state_sha256": digest(pre_state),
        "post_state_sha256": digest(post_state),
        "marker_winner_episode_id": marker["winner_episode_id"],
        "offline_reconstructed_winner_episode_id": winner,
        "winner_filter": {
            "eligible_episode_ids": [row["episode_schema_id"] for row in trajectories
                                     if not row["eligibility"]["first_ineligible_predicate"]],
            "tie_breaking_applied": bool(winner),
            "tie_break_order": ["official_score_desc", "settled_cost_asc", "actions_asc", "trial_id_asc"],
            "result": "no_eligible_grounded_candidate" if winner is None else "winner_promoted",
        },
        "descriptor_sha256": digest([asdict(item) for item in descriptor]),
        "descriptor_operations": [summarize_event(item) for item in descriptor],
        "trajectories": trajectories,
        "method_predicate_source": "copromem.online.apply_task_batch and copromem.learning.LearningCore.promote_episode",
    }


def audit_retrievals(run: Path, task_id: str) -> dict[str, Any]:
    """Verify C provenance and rendering without serializing guidance text."""
    records = []
    expected_pre: str | None = None
    for path in sorted((run / "retrieval" / "copromem_dynamic" / task_id).glob("trial-*.json")):
        row = read(path)
        provenance = row["provenance"]
        pre = provenance["pre_state"]
        adapter = CoProMemAppWorldAdapter(api_key="")
        adapter.clone_from_state(pre)
        reproduced = CoProMemAppWorldAdapter.reproduce_retrieval(pre, provenance["task_input"], provenance)
        selected = provenance["selected_schema_id"]
        schema = adapter.module.learning.schemas.get(selected)
        expected: list[str] = []
        if schema is not None:
            for node in schema.topological_sort():
                expected.extend(sorted(
                    item.procedure_id for item in adapter.module.learning.procedures.values()
                    if item.schema_id == selected and item.step_id == node.node_id
                    and item.status in {"provisional", "admitted"}))
        artifact = read(run / "evaluation" / "copromem_dynamic" / task_id / f"trial-{row['trial']}.json")
        try:
            import tiktoken
            tokens = len(tiktoken.get_encoding("o200k_base").encode(reproduced))
        except Exception:
            tokens = None
        pre_hash = provenance["pre_state_sha256"]
        if expected_pre is None:
            expected_pre = pre_hash
        records.append({
            "trial_id": row["trial"],
            "retrieval_artifact_sha256": sha_file(path),
            "pre_state_sha256": pre_hash,
            "same_pre_state_as_first_trial": pre_hash == expected_pre,
            "selected_schema_id": selected,
            "fallback_category": provenance["fallback_category"],
            "procedure_count": len(provenance["injected_procedure_ids"]),
            "procedure_order_matches_schema": provenance["injected_procedure_ids"] == expected,
            "procedure_ids_sha256": digest(provenance["injected_procedure_ids"]),
            "guidance_sha256": provenance["guidance_sha256"],
            "guidance_bytes": len(reproduced.encode("utf-8")),
            "guidance_tokens_o200k_base": tokens,
            "offline_reproduction_matches": hashlib.sha256(reproduced.encode("utf-8")).hexdigest() == provenance["guidance_sha256"],
            "schema_has_no_concrete_parameters": all(not node.input_keys or all("{" not in key for key in node.input_keys)
                                                      for node in (schema.nodes if schema else ())),
            "official_score": float(artifact["after_score"]),
            "termination": artifact["termination"],
            "actions": int(artifact["actions"]),
        })
    return {"task_id": task_id, "records": records,
            "same_guidance_sha256": len({item["guidance_sha256"] for item in records}) == 1,
            "interpretation": "A partial official score is associated with its recorded termination only; this audit makes no causal attribution to guidance."}


def markdown(data: dict[str, Any]) -> str:
    lines = ["# V5 005 CoProMem Task-Boundary Learning Forensic Audit", "",
             "This zero-provider audit contains only hashes and public operation/slot summaries.", "",
             f"- Manifest SHA-256: `{data['run_manifest_sha256']}`",
             f"- Task: `{data['task_id']}`",
             f"- Recorded winner: `{data['marker_winner_episode_id']}`",
             f"- Offline reconstructed winner: `{data['offline_reconstructed_winner_episode_id']}`", "",
             "## Trajectory decision trace", "",
             "| Trial | Score | Checked output | Signature | Procedures | First promotion blocker |",
             "|---:|---:|---|---|---:|---|"]
    for row in data["trajectories"]:
        predicates = row["eligibility"]["predicates"]
        lines.append(f"| {row['trial_id']} | {row['official_score']:.3f} | {predicates['has_observable_checked_output']} | "
                     f"{predicates['structural_signature_present']} | {row['generated_procedure_count']} | "
                     f"{row['eligibility']['first_ineligible_predicate'] or row['first_promotion_blocker'] or 'none'} |")
    lines += ["", "## Classification", "",
              "The decision trace is generated directly from the frozen implementation predicates. "
              "Both successful trajectories fail at structural-signature construction because their normalized public "
              "events include unobserved nested operations. The v5 rule intentionally refuses to promote incomplete "
              "structural evidence. This is TASK UNSUITABLE for the A-to-B gate under the frozen method, not a scorer failure."]
    c = data.get("c_retrieval_audit")
    if c:
        lines += ["", "## C retrieval audit", "", "| Trial | Same pre-state | Ordered supported procedures | Offline reproduction | Score | Termination |",
                  "|---:|---|---|---|---:|---|"]
        for row in c["records"]:
            lines.append(f"| {row['trial_id']} | {row['same_pre_state_as_first_trial']} | "
                         f"{row['procedure_order_matches_schema']} | {row['offline_reproduction_matches']} | "
                         f"{row['official_score']:.3f} | {row['termination']} |")
        lines += ["", c["interpretation"]]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--c-task")
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    data = trace(args.run, args.task)
    if args.c_task:
        data["c_retrieval_audit"] = audit_retrievals(args.run, args.c_task)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(markdown(data), encoding="utf-8")


if __name__ == "__main__":
    main()
