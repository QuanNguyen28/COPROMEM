"""Independent complete audit of cycle-18 bound-program native effects."""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest
from copromem.stateful_adapter import audit_prefix_runs, verify_prefix_pair
from copromem.stateful_effect import api_log_count, error_indices, origin_checkpoint

RUN = runpy.run_path(str(Path(__file__).with_name("run_bound_effects.py")))
ENGINE = RUN["ENGINE"]
AUDIT = runpy.run_path(str(Path(__file__).with_name("audit_boundary_effects.py")))
require = AUDIT["require"]


def audit(store: RunStore) -> dict:
    root = Path(__file__).resolve().parents[2]
    protocol = store.read("protocol", "preregistration")
    binding = RunStore(root / "artifacts/research/cycle18_public_binding")
    old_source = RunStore(root / "artifacts/research/cycle17_all_boundary_screen")
    construction = runpy.run_path(
        str(Path(__file__).with_name("screen_public_bindings.py"))
    )["screen"](binding, audit_only=True)
    require(
        digest(construction) == protocol["binding_report"] == RUN["BINDING_REPORT"],
        "public construction source changed",
    )
    candidates = {}
    for row in construction["rows"]:
        if row["construction"]["status"] == "accepted_changed":
            candidate = RUN["effect_candidate"](
                row, old_source.read("candidates", row["source_candidate_id"])
            )
            candidates[digest(candidate)] = candidate
    selected, controls = ENGINE["manifest"](candidates)
    require(
        len(candidates) == 5
        and len(selected) == 5
        and len(controls) == 3
        and selected == protocol["selected"]
        and controls == protocol["factual_controls"]
        and sorted(candidates) == protocol["effect_candidate_ids"],
        "complete bound-candidate selection does not regenerate",
    )
    require(
        {path.stem for path in (store.root / "effect_candidates").glob("*.json")}
        == set(candidates)
        and all(
            store.read("effect_candidates", key) == value
            for key, value in candidates.items()
        ),
        "bound candidates lost source identity or were replaced",
    )
    snapshot = store.read("source_snapshots", protocol["source_snapshot"])
    require(
        digest(snapshot) == protocol["source_snapshot"],
        "frozen source snapshot corrupted",
    )
    current_equal = all(
        (root / path).read_text(encoding="utf-8") == text
        for path, text in snapshot.items()
    )
    bundle = root / protocol["public_bundle"]
    manifest = RunStore(bundle).read("manifest", "public_bundle")
    require(
        digest(manifest) == protocol["public_bundle_manifest"]
        and {
            path.relative_to(bundle).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in (bundle / "data").rglob("*")
            if path.is_file()
        }
        == manifest["files"],
        "canonical public bundle changed",
    )
    reports = list((store.root / "reports").glob("*.json"))
    require(len(reports) == 1, "complete bound-effect report required")
    report = store.read("reports", reports[0].stem)
    require(
        digest(report) == reports[0].stem
        and report["protocol_digest"] == digest(protocol),
        "completed report identity mismatch",
    )
    cells, runs, frames, inputs = set(), set(), set(), set()
    rows, details = [], []
    for factual, registry in ((True, controls), (False, selected)):
        for offset, item in enumerate(registry):
            key = f"c18b-{'control' if factual else 'edit'}-{offset:02d}"
            cells.add(key)
            runs.update((key + "-live", key + "-replay"))
            candidate = candidates[item["representative"]]
            origin = candidate["origin"]
            episode = origin["episode"]["episode_id"]
            original = RunStore(Path(candidate["origin_source"]["source_store"]))
            full = original.read("worker_requests", episode)
            old_frame = original.read("worker_results", episode)
            old_score = original.read("native_evaluation", episode)
            require(
                original.read("source_episodes", episode) == origin["episode"]
                and not old_score["native_success"],
                "factual source binding changed",
            )
            program = (
                origin["step"]["code"] if factual else candidate["proposal"]["program"]
            )
            request = ENGINE["replacement_request"](origin, full, program)
            checkpoint = origin_checkpoint(origin)
            index = len(origin["prefix_request"]["actions"])
            expected_binding = {
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
                and all(
                    row.get(name) == value for name, value in expected_binding.items()
                )
                and store.read("bindings", key) == expected_binding
                and store.read("intervention_checkpoints", digest(checkpoint))
                == checkpoint,
                "effect/checkpoint/program identity mismatch",
            )
            cell_frames, cell_inputs = AUDIT["check_processes"](
                store, protocol, key, request, index
            )
            frames.update(cell_frames)
            inputs.update(cell_inputs)
            first = store.read("stream_frames", key + "-live-000")
            precheck = store.read("pre_action_checks", key)
            verified = verify_prefix_pair(
                origin["frame"],
                first,
                expected_error_indices=error_indices(origin["frame"]),
            )
            require(
                precheck is not None
                and all(
                    precheck.get(name) == value
                    for name, value in expected_binding.items()
                )
                and precheck["verification"] == verified,
                "fixed planner/state checkpoint was not re-established",
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
                    "factual full sequence differs from source",
                )
            introduced = sorted(
                set(error_indices(final)) - set(error_indices(old_frame))
            )
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
                "effect outcome/error/tool accounting mismatch",
            )
            require(
                isinstance(row["elapsed_seconds"], (int, float))
                and row["elapsed_seconds"] >= 0,
                "invalid measured elapsed time",
            )
            rows.append(row)
            details.append(
                {
                    "cell_id": key,
                    "origin_episode": episode,
                    "action_index": index,
                    "factual": factual,
                    "native_success": score["native_success"],
                    "eligible": row["eligible"],
                    "introduced_errors": introduced,
                    "effect_gate_passed": passed,
                    "tool_call_entries_delta": row["native_api_log_entries_total"]
                    - row["source_native_api_log_entries_total"]
                    if row["native_api_log_entries_total"] is not None
                    and row["source_native_api_log_entries_total"] is not None
                    else None,
                }
            )
    require(rows == report["rows"], "registered cells omitted/reordered/changed")
    for kind, expected in [
        *((name, cells) for name in ("effect_cells", "bindings", "pre_action_checks")),
        *(
            (name, runs)
            for name in (
                "worker_requests",
                "worker_results",
                "worker_commands",
                "worker_processes",
                "native_evaluation",
                "evaluator_processes",
                "evaluator_commands",
            )
        ),
        ("stream_frames", frames),
        ("stream_inputs", inputs),
    ]:
        require(
            {path.stem for path in (store.root / kind).glob("*.json")} == expected,
            "missing or extra native effect record in " + kind,
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
        "unexpected model or unresolved failure records",
    )
    new_tasks = sorted(
        {
            row["task_id"]
            for row in rows
            if row["effect_gate_passed"]
            and row["task_id"] not in protocol["known_repair_tasks"]
        }
    )
    totals = {
        "complete_registered_sample": True,
        "factual_controls": 3,
        "distinct_interventions": 5,
        "eligible_interventions": sum(
            row["eligible"] for row in rows if not row["factual"]
        ),
        "passing_interventions": sum(row["effect_gate_passed"] for row in rows),
        "new_tasks_with_validated_local_repair": new_tasks,
        "primary_metric": len(new_tasks),
        "native_executions": len(runs),
        "native_evaluations": len(runs),
        "model_calls": 0,
        "api_usd": 0,
        "decision": "KEEP" if new_tasks else "REVISE",
    }
    require(
        all(report.get(name) == value for name, value in totals.items())
        and len(cells) == protocol["expected_cells"] == 8
        and len(runs)
        == protocol["expected_native_executions"]
        == protocol["expected_native_evaluations"]
        == 16,
        "primary decision/complete accounting did not regenerate",
    )
    return {
        "audit": "public-bound-source-to-fixed-native-continuation-v1",
        "protocol_digest": digest(protocol),
        "report_digest": digest(report),
        "construction_report": digest(construction),
        "frozen_source_snapshot": protocol["source_snapshot"],
        "current_sources_equal_frozen": current_equal,
        "raw_native_processes_bound": True,
        "live_frames": len(frames),
        "live_action_inputs": len(inputs),
        "cells": details,
        **totals,
        "audit_model_calls": 0,
        "audit_native_executions": 0,
        "limitation": report["limitation"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store", type=Path, default=Path("artifacts/research/cycle18_bound_effects")
    )
    store = RunStore(parser.parse_args().store)
    record = audit(store)
    store.write("effect_audits", digest(record), record)
    print(json.dumps({"audit_id": digest(record), **record}, indent=2))


if __name__ == "__main__":
    main()
