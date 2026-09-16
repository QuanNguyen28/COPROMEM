"""Exact-origin native program effect tests, separate from contract admission."""

from __future__ import annotations

from pathlib import Path

from .checkpoints import IntegrityError, RunStore, canonical, digest
from .stateful_adapter import (
    audit_prefix_runs,
    evaluate_worker_output,
    run_worker,
    verify_prefix_pair,
)
from .stateful_source import parse_plan
from .stateful_stream import StreamWorker


def error_indices(frame: dict) -> tuple[int, ...]:
    return tuple(
        index
        for index, row in enumerate(frame["results"])
        if row["output"].startswith("Execution failed.")
    )


def origin_checkpoint(origin: dict) -> dict:
    prefix, frame, step = origin["prefix_request"], origin["frame"], origin["step"]
    planner, public = origin["planner_call"], origin["public_checkpoint"]
    if (
        frame["completion_flag"]
        or digest(prefix) != frame["request_id"]
        or step["environment_prefix_id"] != frame["request_id"]
        or digest(public) != step["public_checkpoint_id"]
        or digest(planner["request"]) != step["planner_generation_id"]
        or digest(planner["response"]) != planner["response_sha256"]
        or planner["request"]["user"] != canonical(public["public_context"])
        or parse_plan(planner["response"]["text"])[0] != step["plan"]
    ):
        raise IntegrityError("origin environment/planner binding is corrupt")
    verify_prefix_pair(frame, frame, expected_error_indices=error_indices(frame))
    return {
        "origin_endpoint_digest": digest(origin),
        "environment_request_id": frame["request_id"],
        "state_digest": frame["state_digest"],
        "planner_generation_id": step["planner_generation_id"],
        "planner_artifact": step["plan"],
        "public_checkpoint_id": step["public_checkpoint_id"],
    }


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


def effect_passes(frame: dict, evaluation: dict) -> bool:
    return bool(
        evaluation["native_success"]
        and frame["completion_flag"]
        and not frame["harness_only_state"]["namespace"]["unsupported"]
        and not frame["results"][-1]["output"].startswith("Execution failed.")
    )


def run_effect_cell(
    *,
    image: str,
    bundle: Path,
    native_data: Path,
    store: RunStore,
    cell_id: str,
    origin: dict,
    program: str,
) -> dict:
    """Run one fixed program twice, with a verified exact pre-action origin."""
    prefix, frame = origin["prefix_request"], origin["frame"]
    task_id = prefix["task_id"]
    checkpoint = origin_checkpoint(origin)
    checkpoint_id = digest(checkpoint)
    store.write("intervention_checkpoints", checkpoint_id, checkpoint)
    binding = {
        "checkpoint_id": checkpoint_id,
        "program_digest": digest(program),
        "image_id": image,
    }
    store.write("effect_bindings", cell_id, binding)
    live_id, replay_id = cell_id + "-live", cell_id + "-replay"
    request = {**prefix, "actions": [*prefix["actions"], program]}
    try:
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
                    frame, worker.last, expected_error_indices=error_indices(frame)
                )
                before_calls = api_log_count(store, live_id, task_id)
                store.write(
                    "pre_action_checks",
                    cell_id,
                    {
                        **binding,
                        "verification": verified,
                        "native_api_log_entries_before": before_calls,
                    },
                )
                worker.act(program)
        precheck = store.read("pre_action_checks", cell_id)
        if precheck is None or any(
            precheck.get(key) != value for key, value in binding.items()
        ):
            raise IntegrityError("missing or mixed pre-action check")
        if store.read("worker_requests", live_id) != request:
            raise IntegrityError("effect changed the origin action prefix")
        if store.read("worker_results", replay_id) is None:
            result = run_worker(image, bundle, store, replay_id, request)
            if result.get("status") != "completed":
                raise IntegrityError("independent effect replay worker failed")
        for run_id in (live_id, replay_id):
            if store.read("native_evaluation", run_id) is None:
                evaluate_worker_output(image, native_data, store, run_id, task_id)
        observed = store.read("worker_results", live_id)
        if observed is None:
            raise IntegrityError("live effect worker has no completed result")
        paired = audit_prefix_runs(
            store,
            [[live_id, replay_id]],
            expected_error_indices=error_indices(observed),
        )
        evaluation = paired["pairs"][0]["native_evaluation"]
        total_calls = api_log_count(store, live_id, task_id)
        before_calls = precheck["native_api_log_entries_before"]
        row = {
            "cell_id": cell_id,
            "origin_episode": origin["episode"]["episode_id"],
            **binding,
            "program_characters": len(program),
            "native_evaluation": evaluation,
            "completion_flag": observed["completion_flag"],
            "new_uncaught_action_error": observed["results"][-1]["output"].startswith(
                "Execution failed."
            ),
            "final_public_output": observed["results"][-1]["output"],
            "replay_audit_id": digest(paired),
            "native_api_log_entries_total": total_calls,
            "native_api_log_entries_final_action_delta": None
            if before_calls is None or total_calls is None
            else total_calls - before_calls,
            "effect_gate_passed": effect_passes(observed, evaluation),
            "model_calls": 0,
        }
        store.write("effect_cells", cell_id, row)
        return row
    except Exception as exc:
        store.write(
            "effect_failures",
            cell_id,
            {
                **binding,
                "error_type": type(exc).__name__,
                "interpretation": "Stopped for explicit diagnosis; no automatic partial-worker restart or admission.",
            },
        )
        raise
