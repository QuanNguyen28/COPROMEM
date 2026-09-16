"""All registered boundary edits with fixed saved continuations; no model calls."""

from __future__ import annotations

import argparse
import json
import runpy
import time
from collections import defaultdict
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest
from copromem.stateful_adapter import (
    audit_prefix_runs,
    evaluate_worker_output,
    run_worker,
    verify_prefix_pair,
)
from copromem.stateful_effect import api_log_count, error_indices, origin_checkpoint
from copromem.stateful_stream import StreamWorker

IMAGE = "sha256:b5f9aaedde041e30fc4ff795ab46d47849cfc72701b9ffc8c8983fdefe36fcf6"
SCREEN_REPORT = "47ba12900b34835c813f99dd689b7d01b75c81be5e7ec559dfae3ea1b7778268"


def replacement_request(origin: dict, full: dict, program: str) -> dict:
    prefix, step = origin["prefix_request"], origin["step"]
    index = len(prefix["actions"])
    if (
        full["task_id"] != prefix["task_id"]
        or full["seed"] != prefix["seed"]
        or step["step"] != index
        or index >= len(full["actions"])
        or full["actions"][:index] != prefix["actions"]
        or full["actions"][index] != step["code"]
        or not isinstance(program, str)
        or not program.strip()
    ):
        raise IntegrityError("replacement is not the exact recorded target boundary")
    return {
        **full,
        "actions": [*full["actions"][:index], program, *full["actions"][index + 1 :]],
    }


def passes(
    frame: dict, score: dict, original_errors: tuple[int, ...], eligible: bool
) -> bool:
    return bool(
        eligible
        and score["native_success"]
        and frame["completion_flag"]
        and not frame["harness_only_state"]["namespace"]["unsupported"]
        and not (set(error_indices(frame)) - set(original_errors))
    )


def manifest(candidates: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    grouped = defaultdict(list)
    for key, row in candidates.items():
        if digest(row) != key:
            raise IntegrityError("candidate provenance digest mismatch")
        triple = (
            row["origin_source"]["source_id"],
            row["target_action_index"],
            row["proposal"]["program_ast_digest"],
        )
        grouped[triple].append(key)
    selected = [
        {
            "episode_id": triple[0],
            "action_index": triple[1],
            "program_ast_digest": triple[2],
            "representative": sorted(ids)[0],
            "all_provenance_ids": sorted(ids),
        }
        for triple, ids in sorted(grouped.items())
    ]
    controls = []
    for episode in sorted({row["episode_id"] for row in selected}):
        first = min(
            (row for row in selected if row["episode_id"] == episode),
            key=lambda row: (row["action_index"], row["representative"]),
        )
        controls.append(
            {
                "episode_id": episode,
                "action_index": first["action_index"],
                "representative": first["representative"],
            }
        )
    return selected, controls


def run_cell(
    store: RunStore, protocol: dict, candidate: dict, key: str, *, factual: bool
) -> dict:
    root = Path(__file__).resolve().parents[2]
    source = RunStore(Path(candidate["origin_source"]["source_store"]))
    origin = candidate["origin"]
    episode = origin["episode"]["episode_id"]
    full = source.read("worker_requests", episode)
    old_frame = source.read("worker_results", episode)
    old_score = source.read("native_evaluation", episode)
    if (
        source.read("source_episodes", episode) != origin["episode"]
        or old_score["native_success"]
    ):
        raise IntegrityError("registered failed source origin changed")
    program = origin["step"]["code"] if factual else candidate["proposal"]["program"]
    request = replacement_request(origin, full, program)
    checkpoint = origin_checkpoint(origin)
    before = origin["frame"]
    index = len(origin["prefix_request"]["actions"])
    task = request["task_id"]
    bundle = root / protocol["public_bundle"]
    native_data = root / protocol["native_data"]
    binding = {
        "protocol_digest": digest(protocol),
        "candidate_id": digest(candidate),
        "factual": factual,
        "request_digest": digest(request),
        "checkpoint_digest": digest(checkpoint),
        "source_request_digest": digest(full),
    }
    store.write("bindings", key, binding)
    store.write("intervention_checkpoints", digest(checkpoint), checkpoint)
    existing = store.read("effect_cells", key)
    if existing is not None:
        if any(existing[name] != value for name, value in binding.items()):
            raise IntegrityError("completed effect cell belongs to a different binding")
        return existing
    start = time.monotonic()
    live_id, replay_id = key + "-live", key + "-replay"
    try:
        if store.read("worker_results", live_id) is None:
            with StreamWorker(
                IMAGE,
                bundle,
                store,
                live_id,
                task,
                request["seed"],
                actions=request["actions"][:index],
            ) as worker:
                verification = verify_prefix_pair(
                    before, worker.last, expected_error_indices=error_indices(before)
                )
                store.write(
                    "pre_action_checks",
                    key,
                    {
                        **binding,
                        "verification": verification,
                        "native_api_log_entries_before": api_log_count(
                            store, live_id, task
                        ),
                    },
                )
                for action in request["actions"][index:]:
                    worker.act(action)
        if store.read("worker_requests", live_id) != request:
            raise IntegrityError("live effect changed its saved continuation")
        precheck = store.read("pre_action_checks", key)
        if precheck is None or any(
            precheck[name] != value for name, value in binding.items()
        ):
            raise IntegrityError("effect lacks its exact pre-action identity check")
        if store.read("worker_results", replay_id) is None:
            result = run_worker(IMAGE, bundle, store, replay_id, request)
            if result.get("status") != "completed":
                raise IntegrityError("independent saved-continuation replay failed")
        for run_id in (live_id, replay_id):
            if store.read("native_evaluation", run_id) is None:
                evaluate_worker_output(IMAGE, native_data, store, run_id, task)
        final = store.read("worker_results", live_id)
        score = store.read("native_evaluation", live_id)
        paired, exclusion = None, None
        try:
            paired = audit_prefix_runs(
                store,
                [[live_id, replay_id]],
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
            if score != old_score or paired is None:
                raise IntegrityError("factual source state/output/native score changed")
        introduced = sorted(set(error_indices(final)) - set(error_indices(old_frame)))
        row = {
            "cell_id": key,
            **binding,
            "task_id": task,
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
            "effect_gate_passed": not factual
            and passes(final, score, error_indices(old_frame), paired is not None),
            "native_api_log_entries_before": precheck["native_api_log_entries_before"],
            "native_api_log_entries_total": api_log_count(store, live_id, task),
            "source_native_api_log_entries_total": api_log_count(source, episode, task),
            "elapsed_seconds": time.monotonic() - start,
            "model_calls": 0,
            "api_usd": 0,
        }
        store.write("effect_cells", key, row)
        return row
    except Exception as exc:
        store.write(
            "effect_failures",
            key,
            {
                **binding,
                "error_type": type(exc).__name__,
                "interpretation": "Stopped for explicit diagnosis; no silent partial-worker restart or candidate substitution.",
            },
        )
        raise


def run(store: RunStore, *, prepare_only: bool = False) -> dict:
    root = Path(__file__).resolve().parents[2]
    source = RunStore(root / "artifacts/research/cycle17_all_boundary_screen")
    print(
        json.dumps({"phase": "regenerating_complete_source_and_coverage_audits"}),
        flush=True,
    )
    audited = runpy.run_path(str(Path(__file__).with_name("screen_all_boundaries.py")))[
        "screen"
    ](source, audit_only=True)
    if digest(audited) != SCREEN_REPORT:
        raise IntegrityError("registered complete coverage screen changed")
    candidates = {
        path.stem: source.read("candidates", path.stem)
        for path in (source.root / "candidates").glob("*.json")
    }
    selected, controls = manifest(candidates)
    if len(selected) != 26 or len(selected) > 32 or len(candidates) != 34:
        raise IntegrityError("registered complete candidate count changed")
    paths = [
        *sorted((root / "src/copromem").glob("*.py")),
        Path(__file__).resolve(),
        root / "research/039_CYCLE17A_RESULT_AND_EFFECT_PREREGISTRATION.md",
        *sorted((root / "research/containers/appworld").glob("*.py")),
    ]
    texts = {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in paths
    }
    protocol = {
        "cycle_id": "cycle17b-all-distinct-boundary-edits-saved-continuation",
        "source_report": SCREEN_REPORT,
        "source_protocol": audited["protocol_digest"],
        "source_snapshot": digest(texts),
        "image_id": IMAGE,
        "selected": selected,
        "factual_controls": controls,
        "expected_cells": len(selected) + len(controls),
        "expected_native_executions": 2 * (len(selected) + len(controls)),
        "expected_native_evaluations": 2 * (len(selected) + len(controls)),
        "public_bundle": "artifacts/research/cycle15_reflection_source/public_bundle",
        "public_bundle_manifest": "e5f5a2dae7640d2a364ec82861ad58ac86f3d0d62adf9d18d3250be14c234255",
        "native_data": "artifacts/research/appworld_preflight_20260916/data",
        "model_calls": 0,
        "api_usd": 0,
        "known_repair_tasks": ["aa8502b_1"],
        "continuation": "unchanged saved future action strings; no model regeneration",
    }
    if (
        digest(
            RunStore(root / protocol["public_bundle"]).read("manifest", "public_bundle")
        )
        != protocol["public_bundle_manifest"]
    ):
        raise IntegrityError("canonical public bundle manifest changed")
    store.bind_provenance(
        {"protocol_digest": digest(protocol), "source_snapshot": digest(texts)}
    )
    store.write("protocol", "preregistration", protocol)
    store.write("source_snapshots", digest(texts), texts)
    print(
        json.dumps(
            {
                "protocol_digest": digest(protocol),
                "candidates": len(selected),
                "factual_controls": len(controls),
                "expected_native_executions": protocol["expected_native_executions"],
                "model_calls": 0,
            }
        ),
        flush=True,
    )
    if prepare_only:
        return protocol
    rows = []
    for factual, registry in ((True, controls), (False, selected)):
        for index, selected_row in enumerate(registry):
            key = f"c17b-{'control' if factual else 'edit'}-{index:02d}"
            candidate = candidates[selected_row["representative"]]
            row = run_cell(store, protocol, candidate, key, factual=factual)
            rows.append(row)
            print(
                json.dumps(
                    {
                        "cell_id": key,
                        "task_id": row["task_id"],
                        "origin_episode": row["origin_episode"],
                        "action_index": row["action_index"],
                        "native_success": row["native_evaluation"]["native_success"],
                        "eligible": row["eligible"],
                        "introduced_errors": row["introduced_error_indices"],
                        "effect_gate_passed": row["effect_gate_passed"],
                    }
                ),
                flush=True,
            )
    new_tasks = sorted(
        {
            row["task_id"]
            for row in rows
            if row["effect_gate_passed"]
            and row["task_id"] not in protocol["known_repair_tasks"]
        }
    )
    report = {
        "protocol_digest": digest(protocol),
        "rows": rows,
        "complete_registered_sample": len(rows) == protocol["expected_cells"],
        "factual_controls": len(controls),
        "distinct_interventions": len(selected),
        "eligible_interventions": sum(
            row["eligible"] for row in rows if not row["factual"]
        ),
        "passing_interventions": sum(row["effect_gate_passed"] for row in rows),
        "new_tasks_with_validated_local_repair": new_tasks,
        "primary_metric": len(new_tasks),
        "native_executions": len(list((store.root / "worker_results").glob("*.json"))),
        "native_evaluations": len(
            list((store.root / "native_evaluation").glob("*.json"))
        ),
        "model_calls": 0,
        "api_usd": 0,
        "decision": "KEEP"
        if new_tasks and len(rows) == protocol["expected_cells"]
        else "REVISE",
        "limitation": "Build-only open-loop local program effects; no learned verifier/scope, successful-origin harmful-flip rate, independent same-rule support, contract admission or held-out method advantage.",
    }
    if (
        report["native_executions"] != protocol["expected_native_executions"]
        or report["native_evaluations"] != protocol["expected_native_evaluations"]
    ):
        raise IntegrityError("registered native execution/scoring count mismatch")
    store.write("reports", digest(report), report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store",
        type=Path,
        default=Path("artifacts/research/cycle17_boundary_effects"),
    )
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    report = run(RunStore(args.store), prepare_only=args.prepare_only)
    print(
        json.dumps(
            {
                "record_id": digest(report),
                **{
                    key: value
                    for key, value in report.items()
                    if key not in ("rows", "selected", "factual_controls")
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
