"""Registered build-only final-program cross-over; no model generation."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, canonical, digest
from copromem.stateful_adapter import (
    audit_prefix_runs,
    evaluate_worker_output,
    run_worker,
    verify_prefix_pair,
)
from copromem.stateful_source import parse_plan
from copromem.stateful_stream import StreamWorker

AUDIT_ID = "533d57244a03fbd412ee658d313596131fbb4d3c2743f3825afa16e6a5ce6f76"


def source_endpoint(source: RunStore, episode: dict) -> dict:
    episode_id = episode["episode_id"]
    if not episode["eligible_for_induction"] or not episode["completion_flag"]:
        raise IntegrityError("cross-over requires a supported completed source episode")
    index = episode["steps"] - 1
    step = source.read("source_steps", f"{episode_id}-{index:02d}")
    frame = source.read("stream_frames", f"{episode_id}-{index:03d}")
    request = source.read("worker_requests", episode_id)
    planner = source.read("calls", step["planner_generation_id"])
    public = source.read("public_handoffs", step["public_checkpoint_id"])
    prefix = {**request, "actions": request["actions"][:-1]}
    if (
        len(request["actions"]) != episode["steps"]
        or request["task_id"] != episode["task_id"]
        or step["code"] != request["actions"][-1]
        or frame["completion_flag"]
        or digest(prefix) != frame["request_id"]
        or step["environment_prefix_id"] != frame["request_id"]
        or digest(public) != step["public_checkpoint_id"]
        or digest(planner["request"]) != step["planner_generation_id"]
        or digest(planner["response"]) != planner["response_sha256"]
        or planner["request"]["user"] != canonical(public["public_context"])
        or parse_plan(planner["response"]["text"])[0] != step["plan"]
    ):
        raise IntegrityError("source endpoint/checkpoint/planner identity mismatch")
    return {
        "episode": episode,
        "step": step,
        "frame": frame,
        "prefix_request": prefix,
        "planner_call": planner,
        "public_checkpoint": public,
    }


def error_indices(frame: dict) -> tuple[int, ...]:
    return tuple(
        index
        for index, row in enumerate(frame["results"])
        if row["output"].startswith("Execution failed.")
    )


def api_log_count(store: RunStore, run_id: str, task_id: str) -> int | None:
    path = (
        store.root
        / "native"
        / run_id
        / "outputs/canonical/tasks"
        / task_id
        / "logs/api_calls.jsonl"
    )
    if not path.exists():
        return None
    return sum(
        bool(line.strip()) for line in path.read_text(encoding="utf-8").splitlines()
    )


def main():
    root = Path(__file__).resolve().parents[2]
    source = RunStore(root / "artifacts/research/cycle11_appworld_source")
    store = RunStore(root / "artifacts/research/cycle12_action_crossover")
    audit = source.read("source_audits", AUDIT_ID)
    if (
        audit is None
        or digest(audit) != AUDIT_ID
        or not audit["complete_registered_sample"]
    ):
        raise IntegrityError("registered complete source audit is missing or corrupted")
    source_protocol = source.read("protocol", "preregistration")
    image = source_protocol["image_id"]
    grouped = defaultdict(list)
    for episode in audit["episodes"]:
        if (
            episode["scenario_id"] in audit["mixed_outcome_scenarios"]
            and episode["eligible_for_induction"]
        ):
            grouped[episode["scenario_id"]].append(source_endpoint(source, episode))
    pairs = []
    for scenario in sorted(grouped):
        rows = grouped[scenario]
        if len(rows) != 2 or {
            row["episode"]["native_evaluation"]["native_success"] for row in rows
        } != {False, True}:
            raise IntegrityError("registered two-replicate mixed pair is incomplete")
        if (
            len(
                {
                    (row["episode"]["task_id"], row["prefix_request"]["seed"])
                    for row in rows
                }
            )
            != 1
        ):
            raise IntegrityError(
                "donor must share the origin task and environment seed"
            )
        pairs.append(sorted(rows, key=lambda row: row["episode"]["episode_id"]))
    if not pairs:
        raise IntegrityError("no eligible mixed source pair")
    protocol = {
        "cycle": "cycle12-action-crossover",
        "source_audit_id": AUDIT_ID,
        "source_protocol": source_protocol,
        "pairs": pairs,
        "image_id": image,
        "model_calls": 0,
        "preregistration": "research/022_CYCLE11_RESULTS_AND_CROSSOVER_PREREGISTRATION.md",
        "treatment": "Whole saved final program swap at fixed origin environment/planner checkpoint; no generated or manually revised action.",
    }
    texts = {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in [
            *sorted((root / "src/copromem").glob("*.py")),
            root / "research/containers/appworld/worker.py",
            Path(__file__).resolve(),
            root / protocol["preregistration"],
        ]
    }
    store.bind_provenance(
        {
            "protocol_digest": digest(protocol),
            "source_hashes": {name: digest(text) for name, text in texts.items()},
        }
    )
    store.write("protocol", "preregistration", protocol)
    store.write("source_snapshots", digest(texts), texts)
    bundle = source.root / "public_bundle"
    native_data = root / source_protocol["native_data"]
    cells = []
    for pair_index, endpoints in enumerate(pairs):
        for origin_index, origin in enumerate(endpoints):
            for donor_index, donor in enumerate(endpoints):
                cell_id = f"c12-p{pair_index}-o{origin_index}-d{donor_index}"
                live_id, replay_id = cell_id + "-live", cell_id + "-replay"
                prefix, frame = origin["prefix_request"], origin["frame"]
                program = donor["step"]["code"]
                task_id = prefix["task_id"]
                checkpoint = {
                    "origin_endpoint_digest": digest(origin),
                    "environment_request_id": frame["request_id"],
                    "state_digest": frame["state_digest"],
                    "planner_generation_id": origin["step"]["planner_generation_id"],
                    "planner_artifact": origin["step"]["plan"],
                    "public_checkpoint_id": origin["step"]["public_checkpoint_id"],
                }
                store.write("intervention_checkpoints", digest(checkpoint), checkpoint)
                if store.read("worker_results", live_id) is None:
                    with StreamWorker(
                        image,
                        bundle,
                        store,
                        live_id,
                        task_id,
                        prefix["seed"],
                        actions=prefix["actions"],
                    ) as worker:
                        verified = verify_prefix_pair(
                            frame,
                            worker.last,
                            expected_error_indices=error_indices(frame),
                        )
                        before_calls = api_log_count(store, live_id, task_id)
                        store.write(
                            "pre_action_checks",
                            cell_id,
                            {
                                "checkpoint_id": digest(checkpoint),
                                "verification": verified,
                                "native_api_log_entries_before": before_calls,
                            },
                        )
                        worker.act(program)
                precheck = store.read("pre_action_checks", cell_id)
                if precheck is None or precheck["checkpoint_id"] != digest(checkpoint):
                    raise IntegrityError(
                        "missing or mismatched pre-action verification"
                    )
                request = {**prefix, "actions": [*prefix["actions"], program]}
                if store.read("worker_requests", live_id) != request:
                    raise IntegrityError(
                        "intervention changed more than the final program"
                    )
                if store.read("worker_results", replay_id) is None:
                    run_worker(image, bundle, store, replay_id, request)
                for run_id in (live_id, replay_id):
                    if store.read("native_evaluation", run_id) is None:
                        evaluate_worker_output(
                            image, native_data, store, run_id, task_id
                        )
                observed = store.read("worker_results", live_id)
                paired = audit_prefix_runs(
                    store,
                    [[live_id, replay_id]],
                    expected_error_indices=error_indices(observed),
                )
                evaluation = paired["pairs"][0]["native_evaluation"]
                if origin_index == donor_index:
                    if evaluation != origin["episode"]["native_evaluation"]:
                        raise IntegrityError(
                            "original-action native outcome did not reproduce"
                        )
                    verify_prefix_pair(
                        source.read("worker_results", origin["episode"]["episode_id"]),
                        observed,
                        expected_error_indices=error_indices(observed),
                    )
                total_calls = api_log_count(store, live_id, task_id)
                before_calls = precheck["native_api_log_entries_before"]
                row = {
                    "cell_id": cell_id,
                    "origin_episode": origin["episode"]["episode_id"],
                    "donor_episode": donor["episode"]["episode_id"],
                    "origin_native_success": origin["episode"]["native_evaluation"][
                        "native_success"
                    ],
                    "original_program": origin_index == donor_index,
                    "checkpoint_id": digest(checkpoint),
                    "donor_step_digest": digest(donor["step"]),
                    "donor_executor_generation_id": donor["step"][
                        "executor_generation_id"
                    ],
                    "program_characters": len(program),
                    "native_evaluation": evaluation,
                    "replay_audit_id": digest(paired),
                    "native_api_log_entries_total": total_calls,
                    "native_api_log_entries_final_action_delta": None
                    if before_calls is None or total_calls is None
                    else total_calls - before_calls,
                    "model_calls": 0,
                }
                store.write("cells", cell_id, row)
                cells.append(row)
                print(json.dumps(row), flush=True)
    swapped = [row for row in cells if not row["original_program"]]
    benefits = sum(
        not row["origin_native_success"] and row["native_evaluation"]["native_success"]
        for row in swapped
    )
    harms = sum(
        row["origin_native_success"] and not row["native_evaluation"]["native_success"]
        for row in swapped
    )
    report = {
        "protocol_digest": digest(protocol),
        "cells": cells,
        "beneficial_swaps": benefits,
        "harmful_swaps": harms,
        "decision": "KEEP" if benefits + harms else "REVISE",
        "scope": "Local whole-program effect only; one build task, no minimum edit, admitted verifier, learned advantage or transfer claim.",
        "model_calls": 0,
        "api_cost_note": "Native API log totals/deltas include any native harness bookkeeping; programs can execute different numbers of API calls. Not equal-compute efficiency evidence.",
    }
    key = digest(report)
    store.write("reports", key, report)
    print(
        json.dumps(
            {"report_id": key, "beneficial_swaps": benefits, "harmful_swaps": harms}
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
