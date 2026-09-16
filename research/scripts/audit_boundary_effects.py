"""Regenerate the complete saved-continuation intervention ledger without execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest
from copromem.stateful_adapter import (
    audit_prefix_runs,
    container_command,
    verify_prefix_pair,
)
from copromem.stateful_effect import api_log_count, error_indices, origin_checkpoint

RUN_PATH = Path(__file__).with_name("run_boundary_effects.py")
RUN = runpy.run_path(str(RUN_PATH))
FRAMES = runpy.run_path(
    str(Path(__file__).with_name("audit_official_source_replay.py"))
)["process_frames"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise IntegrityError(message)


def expected_scorer_command(
    image: str, data: Path, output: Path, run_id: str
) -> list[str]:
    command = container_command(
        image, data.parent, output, "copromem-c05-eval-" + run_id
    )
    data_index = next(
        i for i, value in enumerate(command) if "target=/sandbox/data," in value
    )
    command[data_index] = (
        f"type=bind,source={data.resolve()},target=/sandbox/data,readonly"
    )
    output_index = next(
        i for i, value in enumerate(command) if "target=/sandbox/experiments" in value
    )
    command[output_index] += ",readonly"
    command[-1:-1] = ["--entrypoint", "python"]
    command.append("/opt/copromem-evaluator.py")
    return command


def check_processes(
    store: RunStore, protocol: dict, key: str, request: dict, index: int
) -> tuple[set[str], set[str]]:
    root = Path(__file__).resolve().parents[2]
    bundle, data = root / protocol["public_bundle"], root / protocol["native_data"]
    expected_frames, expected_inputs = set(), set()
    for live, run_id in ((True, key + "-live"), (False, key + "-replay")):
        final = store.read("worker_results", run_id)
        require(
            store.read("worker_requests", run_id) == request,
            "changed source prefix or saved continuation",
        )
        require(
            final["request_id"] == digest(request)
            and final["action_limit"] == 50
            and final["task_id"] == request["task_id"],
            "native request/task/runtime identity mismatch",
        )
        expected_command = container_command(
            protocol["image_id"],
            bundle,
            store.root / "native" / run_id,
            "copromem-c05-" + run_id,
        ) + (["--stream"] if live else [])
        require(
            store.read("worker_commands", run_id)["command"] == expected_command,
            "worker image/isolation/mounts changed",
        )
        frames = FRAMES(
            store.read("worker_processes", run_id), "COPROMEM_WORKER_RESULT="
        )
        if live:
            done = FRAMES(
                store.read("worker_processes", run_id), "COPROMEM_WORKER_DONE="
            )
            require(
                len(frames) == len(request["actions"]) - index + 1
                and done == [final]
                and frames[-1] == final,
                "live raw frame/closure mismatch",
            )
            require(
                store.read("stream_initial_requests", run_id)
                == {**request, "actions": request["actions"][:index]},
                "live initialized from a different source prefix",
            )
            for offset, frame in enumerate(frames + done):
                length = min(index + offset, len(request["actions"]))
                prefix = {**request, "actions": request["actions"][:length]}
                frame_key = f"{run_id}-{offset:03d}"
                expected_frames.add(frame_key)
                require(
                    store.read("stream_frames", frame_key) == frame
                    and frame["request_id"] == digest(prefix)
                    and [item["program"] for item in frame["results"]]
                    == prefix["actions"]
                    and frame["state_digest"] == digest(frame["harness_only_state"]),
                    "raw boundary frame/prefix/state identity mismatch",
                )
            for length in range(index + 1, len(request["actions"]) + 1):
                input_key = f"{run_id}-{length:03d}"
                expected_inputs.add(input_key)
                require(
                    store.read("stream_inputs", input_key)
                    == {
                        "program": request["actions"][length - 1],
                        "prefix_id": digest(
                            {**request, "actions": request["actions"][:length]}
                        ),
                    },
                    "saved live input differs from registered action",
                )
        else:
            require(
                frames == [final], "fresh prefix result is not bound to raw process"
            )
        score = store.read("native_evaluation", run_id)
        require(
            FRAMES(
                store.read("evaluator_processes", run_id), "COPROMEM_EVALUATOR_RESULT="
            )
            == [score]
            and score["task_id"] == request["task_id"]
            and score["agent_visible"] is False,
            "native scorer/process/task boundary mismatch",
        )
        require(
            store.read("evaluator_commands", run_id)
            == {
                "command": expected_scorer_command(
                    protocol["image_id"], data, store.root / "native" / run_id, run_id
                ),
                "agent_actions_accepted": False,
            },
            "scorer code/isolation/read-only mounts changed",
        )
        dbs = (
            store.root
            / "native"
            / run_id
            / "outputs/canonical/tasks"
            / request["task_id"]
            / "dbs"
        )
        require(
            {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in dbs.iterdir()
                if path.is_file()
            }
            == final["harness_only_state"]["database_files"],
            "final database bytes changed after native scoring",
        )
    return expected_frames, expected_inputs


def audit(store: RunStore) -> dict:
    root = Path(__file__).resolve().parents[2]
    protocol = store.read("protocol", "preregistration")
    source = RunStore(root / "artifacts/research/cycle17_all_boundary_screen")
    coverage = runpy.run_path(
        str(Path(__file__).with_name("screen_all_boundaries.py"))
    )["screen"](source, audit_only=True)
    require(
        digest(coverage) == protocol["source_report"] == RUN["SCREEN_REPORT"],
        "complete source screen does not regenerate",
    )
    candidates = {
        path.stem: source.read("candidates", path.stem)
        for path in (source.root / "candidates").glob("*.json")
    }
    selected, controls = RUN["manifest"](candidates)
    require(
        selected == protocol["selected"]
        and controls == protocol["factual_controls"]
        and len(selected) == 26
        and len(candidates) == 34,
        "candidate deduplication/complete manifest changed",
    )
    snapshot = store.read("source_snapshots", protocol["source_snapshot"])
    require(
        digest(snapshot) == protocol["source_snapshot"],
        "effect source snapshot is corrupt",
    )
    current_equal = all(
        (root / path).read_text(encoding="utf-8") == text
        for path, text in snapshot.items()
    )
    bundle = root / protocol["public_bundle"]
    bundle_manifest = RunStore(bundle).read("manifest", "public_bundle")
    require(
        digest(bundle_manifest) == protocol["public_bundle_manifest"]
        and {
            path.relative_to(bundle).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in (bundle / "data").rglob("*")
            if path.is_file()
        }
        == bundle_manifest["files"],
        "canonical bundle file inventory changed",
    )
    report_paths = list((store.root / "reports").glob("*.json"))
    require(len(report_paths) == 1, "one complete effect report is required")
    report = store.read("reports", report_paths[0].stem)
    require(
        digest(report) == report_paths[0].stem
        and report["protocol_digest"] == digest(protocol),
        "effect report/protocol identity mismatch",
    )
    expected_cells, expected_runs, expected_frames, expected_inputs = (
        set(),
        set(),
        set(),
        set(),
    )
    rows, details = [], []
    for factual, registry in ((True, controls), (False, selected)):
        for offset, entry in enumerate(registry):
            key = f"c17b-{'control' if factual else 'edit'}-{offset:02d}"
            expected_cells.add(key)
            expected_runs.update((key + "-live", key + "-replay"))
            candidate = candidates[entry["representative"]]
            origin = candidate["origin"]
            original = RunStore(Path(candidate["origin_source"]["source_store"]))
            episode = origin["episode"]["episode_id"]
            full = original.read("worker_requests", episode)
            old_frame = original.read("worker_results", episode)
            old_score = original.read("native_evaluation", episode)
            require(
                original.read("source_episodes", episode) == origin["episode"]
                and not old_score["native_success"],
                "factual source identity/outcome changed",
            )
            program = (
                origin["step"]["code"] if factual else candidate["proposal"]["program"]
            )
            request = RUN["replacement_request"](origin, full, program)
            checkpoint = origin_checkpoint(origin)
            index = len(origin["prefix_request"]["actions"])
            binding = {
                "protocol_digest": digest(protocol),
                "candidate_id": digest(candidate),
                "factual": factual,
                "request_digest": digest(request),
                "checkpoint_digest": digest(checkpoint),
                "source_request_digest": digest(full),
            }
            row = store.read("effect_cells", key)
            require(
                row is not None
                and all(row.get(name) == value for name, value in binding.items())
                and store.read("bindings", key) == binding
                and store.read("intervention_checkpoints", digest(checkpoint))
                == checkpoint,
                "effect candidate/checkpoint/request binding mismatch",
            )
            frames, inputs = check_processes(store, protocol, key, request, index)
            expected_frames.update(frames)
            expected_inputs.update(inputs)
            first = store.read("stream_frames", key + "-live-000")
            precheck = store.read("pre_action_checks", key)
            verified = verify_prefix_pair(
                origin["frame"],
                first,
                expected_error_indices=error_indices(origin["frame"]),
            )
            require(
                precheck is not None
                and all(precheck.get(name) == value for name, value in binding.items())
                and precheck["verification"] == verified,
                "original planner/state pre-action check missing or changed",
            )
            final = store.read("worker_results", key + "-live")
            score = store.read("native_evaluation", key + "-live")
            paired, exclusion = None, None
            try:
                paired = audit_prefix_runs(
                    store,
                    [[key + "-live", key + "-replay"]],
                    expected_error_indices=error_indices(final),
                )
            except IntegrityError as exc:
                if str(exc) != "unsupported namespace state; checkpoint is unverified":
                    raise
                exclusion = str(exc)
            if factual:
                verify_prefix_pair(
                    old_frame, final, expected_error_indices=error_indices(old_frame)
                )
                require(
                    score == old_score and paired is not None,
                    "factual native outcome/state changed",
                )
            introduced = sorted(
                set(error_indices(final)) - set(error_indices(old_frame))
            )
            # Recompute the gate directly, rather than accepting the runner's label.
            passed = bool(
                not factual
                and paired is not None
                and score["native_success"]
                and final["completion_flag"]
                and not final["harness_only_state"]["namespace"]["unsupported"]
                and not introduced
            )
            regenerated = {
                "cell_id": key,
                "task_id": request["task_id"],
                "origin_episode": episode,
                "action_index": index,
                "actions": len(request["actions"]),
                "eligible": paired is not None,
                "exclusion": exclusion,
                "replay_audit_digest": digest(paired) if paired else None,
                "native_evaluation": score,
                "completion_flag": final["completion_flag"],
                "original_error_indices": list(error_indices(old_frame)),
                "observed_error_indices": list(error_indices(final)),
                "introduced_error_indices": introduced,
                "original_native_success": old_score["native_success"],
                "effect_gate_passed": passed,
                "native_api_log_entries_before": precheck[
                    "native_api_log_entries_before"
                ],
                "native_api_log_entries_total": api_log_count(
                    store, key + "-live", request["task_id"]
                ),
                "source_native_api_log_entries_total": api_log_count(
                    original, episode, request["task_id"]
                ),
                "model_calls": 0,
                "api_usd": 0,
            }
            require(
                all(row.get(name) == value for name, value in regenerated.items()),
                "effect outcomes/error/operation accounting do not regenerate",
            )
            require(
                isinstance(row["elapsed_seconds"], (int, float))
                and row["elapsed_seconds"] >= 0,
                "invalid measured local elapsed time",
            )
            rows.append(row)
            details.append(
                {
                    "cell_id": key,
                    "task_id": row["task_id"],
                    "origin_episode": episode,
                    "action_index": index,
                    "factual": factual,
                    "eligible": row["eligible"],
                    "native_success": score["native_success"],
                    "introduced_errors": introduced,
                    "effect_gate_passed": passed,
                    "tool_call_entries_delta": None
                    if row["native_api_log_entries_total"] is None
                    or row["source_native_api_log_entries_total"] is None
                    else row["native_api_log_entries_total"]
                    - row["source_native_api_log_entries_total"],
                }
            )
    require(report["rows"] == rows, "report omits/reorders/changes registered cells")
    for kind, expected in [
        *(
            (kind, expected_cells)
            for kind in ("effect_cells", "bindings", "pre_action_checks")
        ),
        *(
            (kind, expected_runs)
            for kind in (
                "worker_requests",
                "worker_results",
                "worker_processes",
                "worker_commands",
                "native_evaluation",
                "evaluator_processes",
                "evaluator_commands",
            )
        ),
        ("stream_frames", expected_frames),
        ("stream_inputs", expected_inputs),
    ]:
        require(
            {path.stem for path in (store.root / kind).glob("*.json")} == expected,
            "missing or extra effect artifact in " + kind,
        )
    require(
        not any(
            list((store.root / kind).glob("*.json"))
            for kind in (
                "calls",
                "reservations",
                "settlements",
                "transport_attempts",
                "effect_failures",
            )
        ),
        "unexpected API or unresolved failure records",
    )
    new_tasks = sorted(
        {
            row["task_id"]
            for row in rows
            if row["effect_gate_passed"]
            and row["task_id"] not in protocol["known_repair_tasks"]
        }
    )
    regenerated = {
        "complete_registered_sample": True,
        "factual_controls": len(controls),
        "distinct_interventions": len(selected),
        "eligible_interventions": sum(
            row["eligible"] for row in rows if not row["factual"]
        ),
        "passing_interventions": sum(row["effect_gate_passed"] for row in rows),
        "new_tasks_with_validated_local_repair": new_tasks,
        "primary_metric": len(new_tasks),
        "native_executions": len(expected_runs),
        "native_evaluations": len(expected_runs),
        "model_calls": 0,
        "api_usd": 0,
        "decision": "KEEP" if new_tasks else "REVISE",
    }
    require(
        all(report.get(name) == value for name, value in regenerated.items())
        and len(expected_runs)
        == protocol["expected_native_executions"]
        == protocol["expected_native_evaluations"]
        and len(rows) == protocol["expected_cells"],
        "primary decision or complete native counts do not regenerate",
    )
    return {
        "audit": "all-boundary-saved-continuation-native-process-prefix-scorer-v1",
        "protocol_digest": digest(protocol),
        "report_digest": digest(report),
        "source_coverage_report": digest(coverage),
        "frozen_source_snapshot": protocol["source_snapshot"],
        "current_sources_equal_frozen": current_equal,
        "raw_native_processes_bound": True,
        "live_frames": len(expected_frames),
        "live_action_inputs": len(expected_inputs),
        "cells": details,
        **regenerated,
        "audit_model_calls": 0,
        "audit_native_executions": 0,
        "limitation": report["limitation"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store",
        type=Path,
        default=Path("artifacts/research/cycle17_boundary_effects"),
    )
    store = RunStore(parser.parse_args().store)
    record = audit(store)
    store.write("effect_audits", digest(record), record)
    print(json.dumps({"audit_id": digest(record), **record}, indent=2))


if __name__ == "__main__":
    main()
