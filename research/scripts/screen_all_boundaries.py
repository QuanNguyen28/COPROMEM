"""Registered exhaustive action-pair coverage, not semantic effect or admission."""

from __future__ import annotations

import argparse
import json
import runpy
import subprocess
from collections import Counter
from itertools import product
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest
from copromem.procedural_diff import VERSION
from copromem.stateful_effect import origin_checkpoint

SOURCE_PATH = Path(__file__).with_name("screen_archived_source_repairs.py")
SOURCE_MODULE = runpy.run_path(str(SOURCE_PATH))
SCREEN_PROGRAMS = SOURCE_MODULE["SCREEN_PROGRAMS"]


def load_sequence(view: dict) -> list[dict]:
    store = RunStore(Path(view["source_store"]))
    row = store.read(view["source_kind"], view["source_id"])
    if digest(row) != view["source_digest"]:
        raise IntegrityError("source row changed after corpus audit")
    archived = view["source_kind"] == "replayed_sources"
    run_id = row["live_run"] if archived else row["episode_id"]
    request = store.read("worker_requests", run_id)
    final = store.read("worker_results", run_id)
    if digest(request) != view["native_request_digest"]:
        raise IntegrityError("source request changed after corpus audit")
    actions = []
    for index, code in enumerate(request["actions"]):
        before = store.read("stream_frames", f"{run_id}-{index:03d}")
        after = store.read("stream_frames", f"{run_id}-{index + 1:03d}")
        prefix = {**request, "actions": request["actions"][:index]}
        observed = final["results"][index]
        if (
            before is None
            or after is None
            or before["request_id"] != digest(prefix)
            or [item["program"] for item in before["results"]] != prefix["actions"]
            or after["results"][-1] != observed
            or observed["program"] != code
        ):
            raise IntegrityError("action/prefix/public-observation identity mismatch")
        action = {
            "source_store": view["source_store"],
            "source_kind": view["source_kind"],
            "source_id": view["source_id"],
            "source_digest": view["source_digest"],
            "task_id": view["task_id"],
            "action_index": index,
            "code": code,
            "code_digest": digest(code),
            "output_digest": digest(observed["output"]),
            "action_error": observed["output"].startswith("Execution failed."),
            "before_frame_digest": digest(before),
            "after_frame_digest": digest(after),
            "boundary_status": "archive_not_fixed_team_target"
            if archived
            else "unvalidated",
            "target_checkpoint": None,
        }
        if not archived:
            step = store.read("source_steps", f"{run_id}-{index:02d}")
            if step is None or step["code"] != code or step["step"] != index:
                raise IntegrityError("fixed-team source action/step mismatch")
            origin = {
                "episode": row,
                "prefix_request": prefix,
                "frame": before,
                "step": step,
                "planner_call": store.read("calls", step["planner_generation_id"]),
                "public_checkpoint": store.read(
                    "public_handoffs", step["public_checkpoint_id"]
                ),
            }
            action["step_digest"] = digest(step)
            if before["completion_flag"]:
                action["boundary_status"] = "already_completed_target"
            else:
                try:
                    action["target_checkpoint"] = origin_checkpoint(origin)
                    action["boundary_status"] = "valid_fixed_team_target"
                except IntegrityError as exc:
                    if (
                        str(exc)
                        != "unsupported namespace state; checkpoint is unverified"
                    ):
                        raise
                    action["boundary_status"] = "unsupported_target_namespace"
            action["origin"] = origin
        actions.append(action)
    return actions


def screen_action_pair(target: dict, donor: dict) -> dict:
    if target["task_id"] != donor["task_id"]:
        raise IntegrityError("cross-task action pairing is not registered")
    if target["boundary_status"] != "valid_fixed_team_target":
        return {
            "status": target["boundary_status"],
            "proposals": [],
            "rejected_anchors": [],
        }
    if donor["action_error"]:
        return {"status": "donor_action_error", "proposals": [], "rejected_anchors": []}
    return SCREEN_PROGRAMS(target["code"], donor["code"])


def screen(store: RunStore, *, audit_only: bool = False) -> dict:
    root = Path(__file__).resolve().parents[2]
    if (
        subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=root, text=True
        ).strip()
        != "codex/copromem-research-loop"
    ):
        raise IntegrityError("wrong research continuation branch")
    source = RunStore(root / "artifacts/research/cycle16_official_source_replay")
    audited, grouped = SOURCE_MODULE["load_sources"](source)
    snapshot_paths = [
        *sorted((root / "src/copromem").glob("*.py")),
        Path(__file__).resolve(),
        SOURCE_PATH,
        Path(__file__).with_name("screen_source_repairs.py"),
        Path(__file__).with_name("audit_official_source_replay.py"),
        root / "research/038_CYCLE17_ALL_BOUNDARY_SCREEN_PREREGISTRATION.md",
    ]
    texts = {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in snapshot_paths
    }
    protocol = {
        "cycle_id": "cycle17a-all-boundary-source-screen",
        "source_replay_audit": digest(audited),
        "source_views": grouped,
        "source_snapshot": digest(texts),
        "operator": VERSION,
        "known_proposal_tasks": ["aa8502b_1"],
        "model_calls": 0,
        "native_executions": 0,
        "enumeration": "task allocation order; all eligible failed fixed-team x successful sources; ascending target x donor action indices",
    }
    if audit_only:
        if (
            store.read("protocol", "preregistration") != protocol
            or store.read("source_snapshots", digest(texts)) != texts
        ):
            raise IntegrityError("frozen screen source/protocol no longer regenerates")
    else:
        store.bind_provenance(
            {"protocol_digest": digest(protocol), "source_snapshot": digest(texts)}
        )
        store.write("protocol", "preregistration", protocol)
        store.write("source_snapshots", digest(texts), texts)
    cache, pair_records, task_records, registry_ids, candidate_ids = (
        {},
        [],
        [],
        set(),
        set(),
    )
    for task, views in grouped.items():
        task_pairs = []
        failed = [
            view
            for view in views
            if view["eligible"]
            and not view["success"]
            and view["source_kind"] == "source_episodes"
        ]
        successful = [view for view in views if view["eligible"] and view["success"]]
        for target_view, donor_view in product(failed, successful):
            sequences = []
            for view in (target_view, donor_view):
                key = (view["source_store"], view["source_kind"], view["source_id"])
                if key not in cache:
                    cache[key] = load_sequence(view)
                sequences.append(cache[key])
            action_pairs = []
            for target, donor in product(*sequences):
                result = screen_action_pair(target, donor)
                record = {
                    "protocol_digest": digest(protocol),
                    "task_id": task,
                    "target": {
                        key: value for key, value in target.items() if key != "origin"
                    },
                    "donor": {
                        key: value for key, value in donor.items() if key != "origin"
                    },
                    **result,
                }
                record_id = digest(record)
                registry_ids.add(record_id)
                if audit_only:
                    if store.read("action_pairs", record_id) != record:
                        raise IntegrityError("recorded action pair does not regenerate")
                else:
                    store.write("action_pairs", record_id, record)
                proposals = []
                for proposal in result["proposals"]:
                    candidate = {
                        "protocol_digest": digest(protocol),
                        "action_pair_id": record_id,
                        "task_id": task,
                        "origin": target["origin"],
                        "origin_source": target_view,
                        "target_action_index": target["action_index"],
                        "donor_source": donor_view,
                        "donor_action_index": donor["action_index"],
                        "proposal": proposal,
                        "status": "unvalidated syntax-only proposal; no admission",
                    }
                    candidate_id = digest(candidate)
                    candidate_ids.add(candidate_id)
                    if audit_only:
                        if store.read("candidates", candidate_id) != candidate:
                            raise IntegrityError(
                                "recorded candidate does not regenerate"
                            )
                    else:
                        store.write("candidates", candidate_id, candidate)
                    proposals.append(
                        {
                            "candidate_id": candidate_id,
                            "program_ast_digest": proposal["program_ast_digest"],
                        }
                    )
                action_pairs.append(
                    {
                        "record_id": record_id,
                        "target_action_index": target["action_index"],
                        "donor_action_index": donor["action_index"],
                        "status": result["status"],
                        "proposals": proposals,
                    }
                )
            pair = {
                "task_id": task,
                "target_source": target_view,
                "donor_source": donor_view,
                "action_pairs": action_pairs,
                "action_pair_count": len(action_pairs),
                "proposals": sum(len(row["proposals"]) for row in action_pairs),
            }
            pair_records.append(pair)
            task_pairs.append(pair)
        task_records.append(
            {
                "task_id": task,
                "source_records": len(views),
                "ineligible_sources": sum(not view["eligible"] for view in views),
                "outcome_pairs": len(task_pairs),
                "action_pairs": sum(pair["action_pair_count"] for pair in task_pairs),
                "proposals": sum(pair["proposals"] for pair in task_pairs),
            }
        )
    all_action_pairs = [row for pair in pair_records for row in pair["action_pairs"]]
    new_tasks = [
        row["task_id"]
        for row in task_records
        if row["proposals"] and row["task_id"] not in protocol["known_proposal_tasks"]
    ]
    unique = {
        (
            pair["target_source"]["source_id"],
            row["target_action_index"],
            proposal["program_ast_digest"],
        )
        for pair in pair_records
        for row in pair["action_pairs"]
        for proposal in row["proposals"]
    }
    record = {
        "protocol_digest": digest(protocol),
        "tasks": task_records,
        "pairs": pair_records,
        "source_records": sum(row["source_records"] for row in task_records),
        "outcome_pairs": len(pair_records),
        "action_pairs": len(all_action_pairs),
        "action_pair_statuses": dict(
            sorted(Counter(row["status"] for row in all_action_pairs).items())
        ),
        "candidate_provenance_records": len(candidate_ids),
        "unique_target_boundary_programs": len(unique),
        "duplicate_candidate_programs_on_same_boundary": len(candidate_ids)
        - len(unique),
        "new_tasks_with_syntactic_coverage": new_tasks,
        "primary_metric": len(new_tasks),
        "decision": "KEEP" if new_tasks else "REVISE",
        "model_calls": 0,
        "native_executions": 0,
        "admitted_contracts": 0,
        "limitation": "Expanded retrospective syntax coverage only; donor state, semantic effect, learned verifier/scope, independent same-rule support and held-out gain remain unestablished.",
    }
    if audit_only:
        if store.read("reports", digest(record)) != record:
            raise IntegrityError("coverage report does not regenerate")
        for kind, expected in (
            ("action_pairs", registry_ids),
            ("candidates", candidate_ids),
            ("reports", {digest(record)}),
        ):
            if {path.stem for path in (store.root / kind).glob("*.json")} != expected:
                raise IntegrityError("missing or extra screen artifact in " + kind)
    else:
        store.write("reports", digest(record), record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store",
        type=Path,
        default=Path("artifacts/research/cycle17_all_boundary_screen"),
    )
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    record = screen(RunStore(args.store), audit_only=args.audit_only)
    print(
        json.dumps(
            {
                "report_id": digest(record),
                "regenerated_audit": args.audit_only,
                **{key: value for key, value in record.items() if key != "pairs"},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
