"""Descriptive final-action proposal coverage, not native effect validation."""

from __future__ import annotations

import argparse
import json
import runpy
from collections import defaultdict
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest
from copromem.procedural_diff import VERSION, propose_transplants


def screen_programs(failed: str, successful: str) -> dict:
    try:
        proposals, rejected = propose_transplants(failed, successful)
    except (SyntaxError, ValueError) as exc:
        return {
            "status": "unsupported_source_syntax",
            "reason": str(exc),
            "proposals": [],
            "rejected_anchors": [],
        }
    return {
        "status": "proposals_available" if proposals else "no_proposal",
        "proposals": [item.record() for item in proposals],
        "rejected_anchors": rejected,
    }


def screen(source: RunStore, source_audit: dict) -> dict:
    if not source_audit["complete_registered_sample"]:
        raise IntegrityError("screen requires the complete registered sample")
    protocol = source.read("protocol", "preregistration")
    selection = source.read("dataset", "selection")
    if source_audit["cycle_id"] != protocol["cycle_id"]:
        raise IntegrityError("source audit belongs to another cycle")
    grouped = defaultdict(list)
    for episode in source_audit["episodes"]:
        if (
            episode["task_id"] not in selection["build"]
            or source.read("source_episodes", episode["episode_id"]) != episode
        ):
            raise IntegrityError("episode outside the audited build corpus")
        grouped[episode["task_id"]].append(episode)
    tasks, pairs = [], []
    for task_id in selection["build"]:
        rows = sorted(grouped[task_id], key=lambda row: row["episode_id"])
        if len(rows) != protocol["replicates"]:
            raise IntegrityError("registered task replicate count mismatch")
        positive = [
            row
            for row in rows
            if row["eligible_for_induction"]
            and row["native_evaluation"]["native_success"]
        ]
        negative = [
            row
            for row in rows
            if row["eligible_for_induction"]
            and not row["native_evaluation"]["native_success"]
        ]
        tasks.append(
            {
                "task_id": task_id,
                "episodes": len(rows),
                "eligible_successes": len(positive),
                "eligible_failures": len(negative),
                "ineligible_episodes": sum(
                    not row["eligible_for_induction"] for row in rows
                ),
                "outcome_pairs": len(positive) * len(negative),
            }
        )
        for failed in negative:
            for successful in positive:
                pair = {
                    "task_id": task_id,
                    "failed_episode": failed["episode_id"],
                    "successful_episode": successful["episode_id"],
                }
                if not all(
                    row["completion_flag"] and row["steps"] > 0
                    for row in (failed, successful)
                ):
                    pairs.append(
                        {
                            **pair,
                            "status": "not_completed_final_action_pair",
                            "proposals": [],
                            "rejected_anchors": [],
                        }
                    )
                    continue
                steps = [
                    source.read(
                        "source_steps", f"{row['episode_id']}-{row['steps'] - 1:02d}"
                    )
                    for row in (failed, successful)
                ]
                if any(step is None for step in steps):
                    raise IntegrityError("missing final source action")
                pair.update(
                    failed_step_digest=digest(steps[0]),
                    successful_step_digest=digest(steps[1]),
                )
                pairs.append(
                    {**pair, **screen_programs(steps[0]["code"], steps[1]["code"])}
                )
    return {
        "screen": "all-audited-build-pairs-final-action-v1",
        "source_protocol_digest": digest(protocol),
        "source_audit_digest": digest(source_audit),
        "selection_digest": digest(selection),
        "operator": VERSION,
        "tasks": tasks,
        "pairs": pairs,
        "outcome_pairs": len(pairs),
        "pairs_with_proposals": sum(bool(row["proposals"]) for row in pairs),
        "proposals": sum(len(row["proposals"]) for row in pairs),
        "model_calls": 0,
        "native_executions": 0,
        "admitted_contracts": 0,
        "limitation": "Last-action alignment is a restricted diagnostic; no effect, scope, transfer, global repair coverage or superiority is established. Non-completed and unsupported pairs are retained, not replaced by hand-picked earlier actions.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    args = parser.parse_args()
    audit_module = Path(__file__).with_name("audit_stateful_source.py")
    audited = runpy.run_path(str(audit_module))["audit"](
        args.store, native_pair_audit=True
    )
    source = RunStore(args.store)
    result = screen(source, audited)
    result["screen_source_digest"] = digest(Path(__file__).read_text(encoding="utf-8"))
    source.write("source_audits", digest(audited), audited)
    source.write("proposal_screens", digest(result), result)
    print(
        json.dumps(
            {
                "screen_id": digest(result),
                **{key: value for key, value in result.items() if key != "pairs"},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
