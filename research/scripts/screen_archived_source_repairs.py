"""All same-task final-action contrasts, preserving the two source schemas."""

from __future__ import annotations

import argparse
import json
import runpy
from itertools import product
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest
from copromem.procedural_diff import VERSION

SCREEN_PATH = Path(__file__).with_name("screen_source_repairs.py")
SCREEN_PROGRAMS = runpy.run_path(str(SCREEN_PATH))["screen_programs"]


def source_view(store: RunStore, kind: str, key: str) -> dict:
    row = store.read(kind, key)
    if row is None or kind not in ("source_episodes", "replayed_sources"):
        raise IntegrityError("missing or unsupported source schema")
    archived = kind == "replayed_sources"
    run_id = row["live_run"] if archived else row["episode_id"]
    request = store.read("worker_requests", run_id)
    result = store.read("worker_results", run_id)
    count = row["actions"] if archived else row["steps"]
    if (
        request["task_id"] != row["task_id"]
        or len(request["actions"]) != count
        or [item["program"] for item in result["results"]] != request["actions"]
        or result["request_id"] != digest(request)
    ):
        raise IntegrityError("source programs are not bound to native request/result")
    step = None
    if count and not archived:
        step = store.read("source_steps", f"{key}-{count - 1:02d}")
        if step is None or step["code"] != request["actions"][-1]:
            raise IntegrityError(
                "fixed-workflow final step differs from native program"
            )
    return {
        "task_id": row["task_id"],
        "source_store": str(store.root),
        "source_kind": kind,
        "source_id": key,
        "source_digest": digest(row),
        "native_request_digest": digest(request),
        "final_step_digest": digest(step) if step else None,
        "has_recorded_fixed_team_handoff": not archived,
        "eligible": row[
            "eligible_for_local_source" if archived else "eligible_for_induction"
        ],
        "success": row["native_evaluation"]["native_success"],
        "completion_flag": row["completion_flag"],
        "actions": count,
        "final_action": request["actions"][-1] if count else None,
    }


def screen_task(task: str, sources: list[dict]) -> dict:
    identities = [
        (row["source_store"], row["source_kind"], row["source_id"]) for row in sources
    ]
    if len(set(identities)) != len(sources) or any(
        row["task_id"] != task for row in sources
    ):
        raise IntegrityError("duplicate or foreign source in same-task screen")
    if any(
        type(row["success"]) is not bool or type(row["eligible"]) is not bool
        for row in sources
    ):
        raise IntegrityError("source eligibility and native outcomes must be binary")
    eligible = [row for row in sources if row["eligible"]]
    positive = [row for row in eligible if row["success"]]
    negative = [row for row in eligible if not row["success"]]
    pairs = []
    for failed, successful in product(negative, positive):
        pair = {
            "failed": {
                key: value for key, value in failed.items() if key != "final_action"
            },
            "successful": {
                key: value for key, value in successful.items() if key != "final_action"
            },
            "includes_archived_source": any(
                row["source_kind"] == "replayed_sources" for row in (failed, successful)
            ),
        }
        if not all(
            row["completion_flag"] and row["actions"] > 0
            for row in (failed, successful)
        ):
            screened = {
                "status": "not_completed_final_action_pair",
                "proposals": [],
                "rejected_anchors": [],
            }
        else:
            screened = SCREEN_PROGRAMS(
                failed["final_action"], successful["final_action"]
            )
        pairs.append({**pair, **screened})
    return {
        "task_id": task,
        "sources": len(sources),
        "eligible_successes": len(positive),
        "eligible_failures": len(negative),
        "ineligible_sources": len(sources) - len(eligible),
        "outcome_pairs": len(pairs),
        "pairs": pairs,
    }


def load_sources(store: RunStore) -> tuple[dict, dict[str, list[dict]]]:
    """Audits are intentionally serial: a RunStore may materialize audit records."""
    audit_path = Path(__file__).with_name("audit_official_source_replay.py")
    audited = runpy.run_path(str(audit_path))["audit"](store)
    store.write("source_replay_audits", digest(audited), audited)
    root = Path(__file__).resolve().parents[2]
    prior = RunStore(root / "artifacts/research/cycle15_reflection_source")
    grouped = {}
    for task in store.read("protocol", "preregistration")["selection"]["build"]:
        reflection = prior.read("reflection_sources", task)
        original = RunStore(Path(reflection["prior_store"]))
        original_audit = original.read("source_audits", reflection["prior_audit_id"])
        rows = [row for row in original_audit["episodes"] if row["task_id"] == task]
        if len(rows) != 2:
            raise IntegrityError("two original source replicates required")
        grouped[task] = [
            source_view(original, "source_episodes", row["episode_id"]) for row in rows
        ]
        grouped[task].append(source_view(prior, "source_episodes", f"c15-{task}-r2"))
        grouped[task].append(source_view(store, "replayed_sources", task))
    return audited, grouped


def screen(store: RunStore) -> dict:
    audited, grouped = load_sources(store)
    tasks = [screen_task(task, rows) for task, rows in grouped.items()]
    pairs = [pair for task in tasks for pair in task["pairs"]]
    return {
        "screen": "all-fixed-team-and-locally-replayed-archive-final-actions-v1",
        "source_replay_audit": digest(audited),
        "script_digest": digest(Path(__file__).read_text(encoding="utf-8")),
        "program_screen_digest": digest(SCREEN_PATH.read_text(encoding="utf-8")),
        "operator": VERSION,
        "tasks": tasks,
        "sources": sum(task["sources"] for task in tasks),
        "outcome_pairs": len(pairs),
        "pairs_including_archived_source": sum(
            pair["includes_archived_source"] for pair in pairs
        ),
        "pairs_with_proposals": sum(bool(pair["proposals"]) for pair in pairs),
        "proposals": sum(len(pair["proposals"]) for pair in pairs),
        "archived_source_proposals": sum(
            len(pair["proposals"]) for pair in pairs if pair["includes_archived_source"]
        ),
        "independent_tasks_with_proposals": sum(
            any(pair["proposals"] for pair in task["pairs"]) for task in tasks
        ),
        "model_calls": 0,
        "native_executions": 0,
        "admitted_contracts": 0,
        "limitation": "Retrospective exhaustive final-action coverage only. Archived programs are not fixed-team planner handoffs; no earlier-action search, effect validation, scope, transfer or superiority is established.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store",
        type=Path,
        default=Path("artifacts/research/cycle16_official_source_replay"),
    )
    store = RunStore(parser.parse_args().store)
    record = screen(store)
    store.write("combined_proposal_screens", digest(record), record)
    summary = {key: value for key, value in record.items() if key != "tasks"}
    summary["tasks"] = [
        {key: value for key, value in task.items() if key != "pairs"}
        for task in record["tasks"]
    ]
    print(json.dumps({"screen_id": digest(record), **summary}, indent=2))


if __name__ == "__main__":
    main()
