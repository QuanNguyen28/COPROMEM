"""Retain every audited old/new outcome pair; screen final-action AST edits only."""

from __future__ import annotations

import argparse
import json
import runpy
from itertools import product
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest

SCREEN_MODULE = Path(__file__).with_name("screen_source_repairs.py")
SCREEN_PROGRAMS = runpy.run_path(str(SCREEN_MODULE))["screen_programs"]


def screen_task(
    task_id: str, members: list[tuple[RunStore, dict]], retry_id: str
) -> dict:
    """No candidate ranking, manual repair, earlier-action search or effect claim."""
    if len({episode["episode_id"] for _, episode in members}) != len(members):
        raise IntegrityError("duplicate episode in combined source corpus")
    if sum(episode["episode_id"] == retry_id for _, episode in members) != 1:
        raise IntegrityError("one registered retry required")
    for source, episode in members:
        if (
            episode["task_id"] != task_id
            or source.read("source_episodes", episode["episode_id"]) != episode
        ):
            raise IntegrityError("combined source episode identity mismatch")
    eligible = [(store, row) for store, row in members if row["eligible_for_induction"]]
    positives = [
        (store, row)
        for store, row in eligible
        if row["native_evaluation"]["native_success"]
    ]
    negatives = [
        (store, row)
        for store, row in eligible
        if not row["native_evaluation"]["native_success"]
    ]
    pairs = []
    for (failed_store, failed), (success_store, successful) in product(
        negatives, positives
    ):
        pair = {
            "task_id": task_id,
            "failed_store": str(failed_store.root),
            "successful_store": str(success_store.root),
            "failed_episode": failed["episode_id"],
            "successful_episode": successful["episode_id"],
            "failed_episode_digest": digest(failed),
            "successful_episode_digest": digest(successful),
            "includes_new_retry": retry_id
            in (failed["episode_id"], successful["episode_id"]),
        }
        if not all(
            row["completion_flag"] and row["steps"] > 0 for row in (failed, successful)
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
            source.read("source_steps", f"{row['episode_id']}-{row['steps'] - 1:02d}")
            for source, row in ((failed_store, failed), (success_store, successful))
        ]
        if any(step is None for step in steps):
            raise IntegrityError("missing final source action")
        pairs.append(
            {
                **pair,
                "failed_step_digest": digest(steps[0]),
                "successful_step_digest": digest(steps[1]),
                **SCREEN_PROGRAMS(steps[0]["code"], steps[1]["code"]),
            }
        )
    old_outcomes = {
        row["native_evaluation"]["native_success"]
        for _, row in eligible
        if row["episode_id"] != retry_id
    }
    return {
        "task_id": task_id,
        "episodes": len(members),
        "eligible_successes": len(positives),
        "eligible_failures": len(negatives),
        "ineligible_episodes": len(members) - len(eligible),
        "previously_mixed": old_outcomes == {False, True},
        "newly_mixed": bool(positives and negatives and old_outcomes != {False, True}),
        "outcome_pairs": len(pairs),
        "pairs": pairs,
    }


def screen(root: Path) -> dict:
    store = RunStore(root)
    protocol = store.read("protocol", "preregistration")
    audited = runpy.run_path(
        str(Path(__file__).with_name("audit_reflection_source.py"))
    )["audit"](root)
    store.write("reflection_audits", digest(audited), audited)
    selection = store.read("dataset", "selection")
    tasks, original_audits = [], {}
    for task in selection["build"]:
        evidence = store.read("reflection_sources", task)
        original_store = RunStore(Path(evidence["prior_store"]))
        original_audit = original_store.read(
            "source_audits", evidence["prior_audit_id"]
        )
        # The reflection audit independently regenerated each original corpus.
        if (
            original_audit is None
            or digest(original_audit) != evidence["prior_audit_id"]
        ):
            raise IntegrityError("original source audit missing or corrupted")
        original_protocol = original_store.read("protocol", "preregistration")
        old_rows = [row for row in original_audit["episodes"] if row["task_id"] == task]
        if len(old_rows) != original_protocol["replicates"]:
            raise IntegrityError("original task replicate count mismatch")
        retry_rows = [
            store.read("source_episodes", path.stem)
            for path in (root / "source_episodes").glob("*.json")
            if store.read("source_episodes", path.stem)["task_id"] == task
        ]
        if len(retry_rows) != 1:
            raise IntegrityError("retry task replicate count mismatch")
        original_audits[str(original_store.root)] = digest(original_audit)
        tasks.append(
            screen_task(
                task,
                [(original_store, row) for row in old_rows] + [(store, retry_rows[0])],
                retry_rows[0]["episode_id"],
            )
        )
    if [task["task_id"] for task in tasks if task["newly_mixed"]] != audited[
        "new_mixed_tasks"
    ]:
        raise IntegrityError(
            "combined pair availability disagrees with independent primary audit"
        )
    pairs = [pair for task in tasks for pair in task["pairs"]]
    return {
        "screen": "all-original-and-reflection-retry-final-action-pairs-v1",
        "protocol_digest": digest(protocol),
        "reflection_audit_digest": digest(audited),
        "original_audit_digests": original_audits,
        "script_digest": digest(Path(__file__).read_text(encoding="utf-8")),
        "program_screen_digest": digest(SCREEN_MODULE.read_text(encoding="utf-8")),
        "tasks": tasks,
        "outcome_pairs": len(pairs),
        "pairs_including_new_retry": sum(pair["includes_new_retry"] for pair in pairs),
        "pairs_with_proposals": sum(bool(pair["proposals"]) for pair in pairs),
        "proposals": sum(len(pair["proposals"]) for pair in pairs),
        "independent_tasks_with_proposals": sum(
            any(pair["proposals"] for pair in task["pairs"]) for task in tasks
        ),
        "model_calls": 0,
        "native_executions": 0,
        "admitted_contracts": 0,
        "limitation": "Retrospective exhaustive source-code screen under the existing restricted final-action operator, not new outcome collection, effect validation, scope, transfer or superiority. All same-task contrasts retained; repeated donors on one task do not create independent support.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store",
        type=Path,
        default=Path("artifacts/research/cycle15_reflection_source"),
    )
    args = parser.parse_args()
    record = screen(args.store)
    RunStore(args.store).write("combined_proposal_screens", digest(record), record)
    summary = {key: value for key, value in record.items() if key != "tasks"}
    summary["tasks"] = [
        {key: value for key, value in task.items() if key != "pairs"}
        for task in record["tasks"]
    ]
    print(json.dumps({"screen_id": digest(record), **summary}, indent=2))


if __name__ == "__main__":
    main()
