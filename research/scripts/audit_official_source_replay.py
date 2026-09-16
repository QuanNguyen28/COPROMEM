"""Regenerate local archived-source outcomes and verify exact prefix/process records."""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest
from copromem.official_source import audit_extracted_source
from copromem.stateful_adapter import audit_prefix_runs, container_command


def process_frames(record: dict, prefix: str) -> list[dict]:
    if record["exit_code"] != 0 or record.get("closure_error_type"):
        raise IntegrityError("native process was unsuccessful or uncleanly closed")
    return [
        json.loads(line[len(prefix) :])
        for line in record["stdout"].splitlines()
        if line.startswith(prefix)
    ]


def audit(store: RunStore) -> dict:
    root = Path(__file__).resolve().parents[2]
    protocol = store.read("protocol", "preregistration")
    script = runpy.run_path(
        str(Path(__file__).with_name("run_official_source_replay.py"))
    )
    official = RunStore(
        root / "artifacts/research/official_appworld_train_source_20260916_v013"
    )
    source_audit = audit_extracted_source(official, protocol["source_extraction"])
    if digest(source_audit) != protocol["source_audit"]:
        raise IntegrityError("official extraction audit no longer matches")
    prior = RunStore(root / "artifacts/research/cycle15_reflection_source")
    prior_audit = runpy.run_path(
        str(Path(__file__).with_name("audit_reflection_source.py"))
    )["audit"](prior.root)
    if (
        digest(prior_audit) != protocol["prior_audit"]
        or prior.read("dataset", "selection") != protocol["selection"]
    ):
        raise IntegrityError("prior complete source evidence or allocation changed")
    snapshot_paths = list((store.root / "source_snapshots").glob("*.json"))
    if len(snapshot_paths) != 1:
        raise IntegrityError("one frozen replay source snapshot required")
    snapshot = store.read("source_snapshots", snapshot_paths[0].stem)
    if digest(snapshot) != snapshot_paths[0].stem:
        raise IntegrityError("frozen replay source snapshot digest changed")
    # Current text equality is a dated check; the frozen code remains authority
    # after a deliberate future implementation change.
    current_source_equal = all(
        (root / name).read_text(encoding="utf-8") == value
        for name, value in snapshot.items()
    )
    reports = list((store.root / "reports").glob("*.json"))
    if len(reports) != 1:
        raise IntegrityError("exactly one completed source report required")
    report = store.read("reports", reports[0].stem)
    if digest(report) != reports[0].stem or report["protocol_digest"] != digest(
        protocol
    ):
        raise IntegrityError("completed source report digest mismatch")
    tasks = protocol["selection"]["build"]
    rows = [store.read("replayed_sources", task) for task in tasks]
    if any(row is None for row in rows) or report["rows"] != rows:
        raise IntegrityError("complete all-eight source rows required")
    if {p.stem for p in (store.root / "replayed_sources").glob("*.json")} != set(tasks):
        raise IntegrityError("unregistered source task record")
    bundle = prior.root / "public_bundle"
    bundle_manifest = RunStore(bundle).read("manifest", "public_bundle")
    if (
        digest(bundle_manifest) != protocol["public_bundle_manifest"]
        or {
            p.relative_to(bundle).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (bundle / "data").rglob("*")
            if p.is_file()
        }
        != bundle_manifest["files"]
    ):
        raise IntegrityError("canonical public bundle changed")
    regenerated_prior, details, expected_runs, expected_frames = {}, [], set(), set()
    for row in rows:
        task = row["task_id"]
        old = prior.read("reflection_sources", task)["prior_eligible_outcomes"]
        retry = prior.read("source_episodes", f"c15-{task}-r2")
        regenerated_prior[task] = old + (
            [retry["native_evaluation"]["native_success"]]
            if retry["eligible_for_induction"]
            else []
        )
        parsed = json.loads(
            (
                official.root
                / "selected_public"
                / protocol["source_extraction"]
                / "parsed"
                / (task + ".json")
            ).read_text(encoding="utf-8")
        )
        actions = [item["code"] for item in parsed["interactions"]]
        request = {
            "task_id": task,
            "seed": protocol["environment_seed"],
            "actions": actions,
        }
        if (
            digest(parsed) != row["source_parsed_digest"]
            or protocol["source_actions"][task] != actions
            or row["request_digest"] != digest(request)
            or row["protocol_digest"] != digest(protocol)
        ):
            raise IntegrityError(
                "recorded source/actions/request are not archive-bound"
            )
        ids = [f"c16b-{task}-live", f"c16b-{task}-replay"]
        if [row["live_run"], row["replay_run"]] != ids:
            raise IntegrityError("unregistered native run ID")
        frames = None
        for index, key in enumerate(ids):
            expected_runs.add(key)
            final = store.read("worker_results", key)
            raw = store.read("worker_processes", key)
            if (
                final is None
                or raw is None
                or store.read("worker_requests", key) != request
            ):
                raise IntegrityError("missing native source process/request/result")
            if (
                final["task_id"] != task
                or final["request_id"] != digest(request)
                or final["action_limit"] != 100
                or digest(final["harness_only_state"]) != final["state_digest"]
            ):
                raise IntegrityError(
                    "final native identity/capacity/state digest mismatch"
                )
            expected_command = container_command(
                protocol["image_id"],
                bundle,
                store.root / "native" / key,
                "copromem-c05-" + key,
            ) + (["--stream"] if index == 0 else [])
            if store.read("worker_commands", key)["command"] != expected_command:
                raise IntegrityError("worker isolation/image/mount command changed")
            if index == 0:
                frames = process_frames(raw, "COPROMEM_WORKER_RESULT=")
                done = process_frames(raw, "COPROMEM_WORKER_DONE=")
                if (
                    len(frames) != len(actions) + 1
                    or done != [final]
                    or frames[-1] != final
                ):
                    raise IntegrityError(
                        "live process frames or closing frame mismatch"
                    )
                for offset, frame in enumerate(frames + done):
                    frame_key = f"{key}-{offset:03d}"
                    expected_frames.add(frame_key)
                    prefix = {
                        **request,
                        "actions": actions[: min(offset, len(actions))],
                    }
                    if (
                        store.read("stream_frames", frame_key) != frame
                        or frame["request_id"] != digest(prefix)
                        or [item["program"] for item in frame["results"]]
                        != prefix["actions"]
                        or frame["state_digest"] != digest(frame["harness_only_state"])
                    ):
                        raise IntegrityError(
                            "live boundary is not the exact source prefix"
                        )
            elif process_frames(raw, "COPROMEM_WORKER_RESULT=") != [final]:
                raise IntegrityError(
                    "fresh replay result is not bound to raw process output"
                )
            scorer = store.read("native_evaluation", key)
            if (
                process_frames(
                    store.read("evaluator_processes", key), "COPROMEM_EVALUATOR_RESULT="
                )
                != [scorer]
                or scorer["task_id"] != task
                or scorer["agent_visible"]
            ):
                raise IntegrityError("native score/process/task binding mismatch")
            command = store.read("evaluator_commands", key)["command"]
            if (
                protocol["image_id"] not in command
                or command[-1] != "/opt/copromem-evaluator.py"
                or not any(
                    "target=/sandbox/data,readonly" in value for value in command
                )
                or not any(
                    "target=/sandbox/experiments,readonly" in value for value in command
                )
            ):
                raise IntegrityError(
                    "native scorer image/read-only input boundary changed"
                )
            dbs = store.root / "native" / key / "outputs/canonical/tasks" / task / "dbs"
            if {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in dbs.iterdir()
                if p.is_file()
            } != final["harness_only_state"]["database_files"]:
                raise IntegrityError("native final database changed after scoring")
        first = store.read("worker_results", ids[0])
        errors = [
            i
            for i, item in enumerate(first["results"])
            if item["output"].startswith("Execution failed.")
        ]
        paired, exclusion = None, None
        try:
            paired = audit_prefix_runs(
                store, [ids], expected_error_indices=tuple(errors)
            )
        except IntegrityError as exc:
            exclusion = str(exc)
        if (
            row["eligible_for_local_source"] != (paired is not None)
            or row["exclusion"] != exclusion
            or row["paired_audit_digest"]
            != (digest(paired) if paired is not None else None)
        ):
            raise IntegrityError(
                "local source eligibility or exclusion does not regenerate"
            )
        differences = [
            i
            for i, (old, new) in enumerate(
                zip(parsed["interactions"], first["results"], strict=True)
            )
            if old["output"] != new["output"]
        ]
        unsupported = [
            i
            for i, frame in enumerate(frames)
            if frame["harness_only_state"]["namespace"]["unsupported"]
        ]
        if (
            row["actions"] != len(actions)
            or row["action_error_indices"] != errors
            or row["archived_output_difference_indices"] != differences
            or row["exact_archived_output_match"] != (not differences)
            or row["unsupported_boundary_indices"] != unsupported
            or row["native_evaluation"] != store.read("native_evaluation", ids[0])
            or row["completion_flag"] != first["completion_flag"]
            or row["model_calls"] != 0
        ):
            raise IntegrityError("descriptive source outcome fields do not regenerate")
        details.append(
            {
                "task_id": task,
                "actions": len(actions),
                "native_success": row["native_evaluation"]["native_success"],
                "eligible": paired is not None,
                "action_errors": len(errors),
                "unsupported_boundaries": unsupported,
                "archived_output_differences": len(differences),
                "exclusion": exclusion,
            }
        )
    if regenerated_prior != protocol["prior_eligible_outcomes"]:
        raise IntegrityError("prior mixed-task reference changed")
    for kind in (
        "worker_requests",
        "worker_results",
        "native_evaluation",
        "worker_processes",
        "evaluator_processes",
    ):
        if {p.stem for p in (store.root / kind).glob("*.json")} != expected_runs:
            raise IntegrityError("missing or extra native artifact in " + kind)
    if {
        p.stem for p in (store.root / "stream_frames").glob("*.json")
    } != expected_frames:
        raise IntegrityError("extra or missing live boundary/closing frames")
    if any(
        list((store.root / kind).glob("*.json"))
        for kind in ("calls", "reservations", "settlements", "transport_attempts")
    ):
        raise IntegrityError("unexpected model/provider records in zero-call replay")
    mixed = script["new_mixed_tasks"](regenerated_prior, rows)
    regenerated = {
        "complete_registered_sample": True,
        "new_mixed_tasks": mixed,
        "primary_metric": len(mixed),
        "previously_unmixed_opportunities": sum(
            len(set(values)) == 1 for values in regenerated_prior.values()
        ),
        "native_successes": sum(
            row["native_evaluation"]["native_success"] for row in rows
        ),
        "eligible_sources": sum(row["eligible_for_local_source"] for row in rows),
        "native_executions": len(expected_runs),
        "native_evaluations": len(expected_runs),
        "model_calls": 0,
        "api_usd": 0,
    }
    if any(report[key] != value for key, value in regenerated.items()):
        raise IntegrityError(
            "completed primary/secondary/accounting metrics do not regenerate"
        )
    expected_decision = (
        "KEEP"
        if mixed
        and all(
            row["exclusion"]
            in (None, "unsupported namespace state; checkpoint is unverified")
            for row in rows
        )
        else "REVISE"
    )
    if report["decision"] != expected_decision:
        raise IntegrityError("preregistered source-route decision does not regenerate")
    return {
        "audit": "official-archive-to-local-native-prefix-process-and-outcome-v1",
        "protocol_digest": digest(protocol),
        "source_report_digest": reports[0].stem,
        "extraction_audit": digest(source_audit),
        "frozen_source_snapshot": snapshot_paths[0].stem,
        "current_sources_equal_frozen": current_source_equal,
        "all_native_processes_and_live_frames_bound": True,
        "live_boundary_and_closing_frames": len(expected_frames),
        "tasks": details,
        **regenerated,
        "audit_model_calls": 0,
        "audit_native_executions": 0,
        "limitation": "Local archived-program replay only; original policy/demonstration behavior, historical acquisition cost, learned verifier/scope, causal effect or held-out advantage are not established.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store",
        type=Path,
        default=Path("artifacts/research/cycle16_official_source_replay"),
    )
    args = parser.parse_args()
    store = RunStore(args.store)
    record = audit(store)
    store.write("source_replay_audits", digest(record), record)
    print(json.dumps({"audit_id": digest(record), **record}, indent=2))


if __name__ == "__main__":
    main()
