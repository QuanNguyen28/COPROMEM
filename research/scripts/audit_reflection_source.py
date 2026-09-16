"""Independently reconstruct source feedback, retry inputs, outcomes and costs."""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest
from copromem.reflection_source import retry_settings


def outcome_summary(sources: dict, episodes: list[dict]) -> dict:
    new_mixed, descriptive = [], []
    for episode in episodes:
        task = episode["task_id"]
        source = sources[task]
        prior = source["prior_eligible_outcomes"]
        if not prior or any(type(value) is not bool for value in prior):
            raise IntegrityError("invalid prior outcome evidence")
        after = episode["native_evaluation"]["native_success"]
        before = source["reflection_input"]["previous_native_success"]
        if type(after) is not bool or type(before) is not bool:
            raise IntegrityError("binary outcome required")
        had_success, had_failure = any(prior), not all(prior)
        if (
            episode["eligible_for_induction"]
            and not (had_success and had_failure)
            and ((after and had_failure) or (not after and had_success))
        ):
            new_mixed.append(task)
        descriptive.append(
            {
                "task_id": task,
                "source_replicate_success": before,
                "retry_success": after,
                "eligible": episode["eligible_for_induction"],
                "change": "same"
                if before == after
                else "bad_to_good"
                if after
                else "good_to_bad",
            }
        )
    return {
        "new_mixed_tasks": new_mixed,
        "primary_metric": len(new_mixed),
        "descriptive_outcome_changes_not_causal_flips": descriptive,
    }


def audit(root: Path) -> dict:
    store = RunStore(root)
    protocol = store.read("protocol", "preregistration")
    script_dir = Path(__file__).parent
    sources, selection = runpy.run_path(str(script_dir / "run_reflection_source.py"))[
        "gather_sources"
    ](protocol)
    if selection != store.read("dataset", "selection"):
        raise IntegrityError("retry dataset no longer matches frozen prior allocation")
    for task, source in sources.items():
        if store.read("reflection_sources", task) != source:
            raise IntegrityError(
                "reflection source no longer matches original public trace/outcome"
            )
    source_audit = runpy.run_path(str(script_dir / "audit_stateful_source.py"))[
        "audit"
    ](root, native_pair_audit=True)
    episodes = source_audit["episodes"]
    if not source_audit["complete_registered_sample"]:
        raise IntegrityError(
            "complete registered retry sample required for final audit"
        )
    report_paths = list((root / "reports").glob("*.json"))
    if len(report_paths) != 1:
        raise IntegrityError("one completed immutable report required")
    original = store.read("reports", report_paths[0].stem)
    if digest(original) != report_paths[0].stem or original[
        "protocol_digest"
    ] != digest(protocol):
        raise IntegrityError("source report digest mismatch")
    notes, action_calls = set(), set()
    for task in selection["build"]:
        note = retry_settings(protocol, store, task)["source_retry_note"]
        notes.add(note["reflection_call_id"])
    for path in (root / "source_steps").glob("*.json"):
        step = store.read("source_steps", path.stem)
        action_calls.update(
            (step["planner_generation_id"], step["executor_generation_id"])
        )
    all_calls = {path.stem for path in (root / "calls").glob("*.json")}
    if (
        notes & action_calls
        or notes | action_calls != all_calls
        or len(notes) != len(selection["build"])
    ):
        raise IntegrityError(
            "unaccounted, shared or missing reflection/action generation"
        )
    outcomes = outcome_summary(
        sources,
        sorted(episodes, key=lambda row: selection["build"].index(row["task_id"])),
    )
    for field in ("new_mixed_tasks", "primary_metric"):
        if original[field] != outcomes[field]:
            raise IntegrityError("source contrast metric does not regenerate")
    if (
        original["completed_calls"] != len(all_calls)
        or abs(original["settled_usd"] - source_audit["usage"]["usd"]) > 1e-9
        or abs(
            original["charged_or_reserved_usd"]
            - source_audit["charged_or_reserved_usd"]
        )
        > 1e-9
    ):
        raise IntegrityError(
            "reported source cost does not match archived calls/ledger"
        )
    partitioned_usage = {}
    for name, call_ids in (("reflection", notes), ("planner_executor", action_calls)):
        usages = [store.read("calls", key)["response"]["usage"] for key in call_ids]
        partitioned_usage[name] = {
            "calls": len(call_ids),
            **{
                field: sum(row.get(field, 0) for row in usages)
                for field in (
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "usd",
                    "latency_seconds",
                )
            },
        }
    record = {
        "audit": "binary-feedback-source-note-retry-integrity-v1",
        "protocol_digest": digest(protocol),
        "source_report_digest": report_paths[0].stem,
        "source_audit_digest": digest(source_audit),
        "selection_digest": digest(selection),
        "task_count": len(selection["build"]),
        "previously_unmixed_opportunities": sum(
            len(set(source["prior_eligible_outcomes"])) == 1
            for source in sources.values()
        ),
        "reflection_source_traces_and_binary_outcomes_regenerated": True,
        "all_note_and_boundary_call_bindings_verified": True,
        "all_completed_calls_accounted": True,
        "partitioned_usage": partitioned_usage,
        **outcomes,
        "model_calls_for_audit": 0,
        "limitation": "Source acquisition only. Changed outcomes are not randomized or shared-upstream-checkpoint causal treatment flips; no executable contract, admission or transfer result is inferred.",
    }
    store.write("source_audits", digest(source_audit), source_audit)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store",
        type=Path,
        default=Path("artifacts/research/cycle15_reflection_source"),
    )
    args = parser.parse_args()
    record = audit(args.store)
    key = digest(record)
    RunStore(args.store).write("reflection_audits", key, record)
    print(json.dumps({"audit_id": key, **record}, indent=2))


if __name__ == "__main__":
    main()
