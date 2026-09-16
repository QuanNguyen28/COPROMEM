"""All-eight fixed archived-program local replay, not policy/model reproduction."""

from __future__ import annotations

import hashlib
import json
import runpy
import time
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest
from copromem.official_source import audit_extracted_source
from copromem.stateful_adapter import (
    audit_prefix_runs,
    evaluate_worker_output,
    run_worker,
)
from copromem.stateful_stream import StreamWorker

IMAGE = "sha256:fe315fb9624642ea25abd1687dc0694b4868dde3066a71ada0ab4d69911d4c33"
EXTRACTION = "bfc1c31b1818cfa088308ae2bd041b4546177db6a202c91517671fd19ae56bc8"
SOURCE_AUDIT = "29b1bfd114f107f3b27de4f44d3119db3fb63891109b86bb43e0c1b5ec9cf192"
PRIOR_AUDIT = "4bc8f45e9fc021448005eb9ba259a5b09eaf3e7ff3173e74d7a81f8cebc5c90b"
GATE = "979dbc65ed13d98da57168e3af68df0d33999ebe93606a12778e2dbab55cccfb"


def new_mixed_tasks(prior: dict[str, list[bool]], rows: list[dict]) -> list[str]:
    if len({row["task_id"] for row in rows}) != len(rows) or any(
        row["task_id"] not in prior for row in rows
    ):
        raise IntegrityError("duplicate or unregistered source task outcome")
    mixed = []
    for row in rows:
        task = row["task_id"]
        outcomes = prior[task]
        if not outcomes or any(type(value) is not bool for value in outcomes):
            raise IntegrityError("prior outcomes must be nonempty binary evidence")
        if row["eligible_for_local_source"]:
            after = row["native_evaluation"]["native_success"]
            if type(after) is not bool:
                raise IntegrityError("local source outcome is not binary")
            if set(outcomes) != {False, True} and set(outcomes + [after]) == {
                False,
                True,
            }:
                mixed.append(task)
    return mixed


def main():
    root = Path(__file__).resolve().parents[2]
    store = RunStore(root / "artifacts/research/cycle16_official_source_replay")
    official = RunStore(
        root / "artifacts/research/official_appworld_train_source_20260916_v013"
    )
    source_audit = audit_extracted_source(official, EXTRACTION)
    if digest(source_audit) != SOURCE_AUDIT:
        raise IntegrityError("extracted source audit changed")
    gate_store = RunStore(root / "artifacts/research/cycle16_runtime_gate")
    gate = gate_store.read("runtime_gate_reports", GATE)
    if gate is None or digest(gate) != GATE or gate["decision"] != "KEEP":
        raise IntegrityError("100-action native gate has not passed")
    prior_store = RunStore(root / "artifacts/research/cycle15_reflection_source")
    prior_audit = runpy.run_path(
        str(Path(__file__).with_name("audit_reflection_source.py"))
    )["audit"](prior_store.root)
    if digest(prior_audit) != PRIOR_AUDIT:
        raise IntegrityError("prior complete source corpus changed")
    selection = prior_store.read("dataset", "selection")
    if source_audit["tasks"] != selection["build"]:
        raise IntegrityError("official and original build tasks differ")
    bundle = prior_store.root / "public_bundle"
    manifest = RunStore(bundle).read("manifest", "public_bundle")
    if (
        digest(manifest)
        != "e5f5a2dae7640d2a364ec82861ad58ac86f3d0d62adf9d18d3250be14c234255"
    ):
        raise IntegrityError("canonical public bundle manifest changed")
    actual = {
        path.relative_to(bundle).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in (bundle / "data").rglob("*")
        if path.is_file()
    }
    if actual != manifest["files"]:
        raise IntegrityError("canonical public bundle files changed")
    parsed, prior_outcomes = {}, {}
    for task in selection["build"]:
        record = json.loads(
            (
                official.root
                / "selected_public"
                / EXTRACTION
                / "parsed"
                / (task + ".json")
            ).read_text(encoding="utf-8")
        )
        if digest(record) != source_audit["parsed_digests"][task]:
            raise IntegrityError("source parsed record changed after audit")
        parsed[task] = record
        previous = prior_store.read("reflection_sources", task)[
            "prior_eligible_outcomes"
        ]
        retry = prior_store.read("source_episodes", f"c15-{task}-r2")
        prior_outcomes[task] = list(previous) + (
            [retry["native_evaluation"]["native_success"]]
            if retry["eligible_for_induction"]
            else []
        )
    protocol = {
        "cycle": "cycle16-official-source-local-replay",
        "image_id": IMAGE,
        "runtime_gate": GATE,
        "source_audit": SOURCE_AUDIT,
        "source_extraction": EXTRACTION,
        "prior_audit": PRIOR_AUDIT,
        "selection": selection,
        "parsed_digests": source_audit["parsed_digests"],
        "public_bundle_manifest": digest(manifest),
        "prior_eligible_outcomes": prior_outcomes,
        "environment_seed": 100,
        "source_actions": {
            task: [row["code"] for row in record["interactions"]]
            for task, record in parsed.items()
        },
        "preregistration": "research/036_CYCLE16A_RESULT_AND_OFFICIAL_REPLAY_PREREGISTRATION.md",
        "model_calls": 0,
    }
    texts = {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in [
            Path(__file__),
            root / protocol["preregistration"],
            *sorted((root / "src/copromem").glob("*.py")),
            *sorted((root / "research/containers/appworld").glob("*.py")),
            root / "research/containers/appworld/Dockerfile.longsource",
            root / "research/containers/appworld/requirements-linux-amd64.lock",
        ]
    }
    store.bind_provenance(
        {
            "protocol_digest": digest(protocol),
            "source_hashes": {path: digest(value) for path, value in texts.items()},
        }
    )
    store.write("protocol", "preregistration", protocol)
    store.write("source_snapshots", digest(texts), texts)
    rows = []
    native_data = root / "artifacts/research/appworld_preflight_20260916/data"
    for task in selection["build"]:
        previous = store.read("replayed_sources", task)
        if previous is not None:
            if previous["protocol_digest"] != digest(protocol):
                raise IntegrityError("cached local source provenance mismatch")
            rows.append(previous)
            continue
        request = {
            "task_id": task,
            "seed": 100,
            "actions": protocol["source_actions"][task],
        }
        live_id, replay_id = f"c16b-{task}-live", f"c16b-{task}-replay"
        started = time.perf_counter()
        # Existing partial directories are deliberately rejected by the shared
        # runner; no implicit re-generation or alternate source is attempted.
        if store.read("worker_results", live_id) is None:
            with StreamWorker(IMAGE, bundle, store, live_id, task, 100) as worker:
                for index, code in enumerate(request["actions"]):
                    worker.act(code)
                    if (index + 1) % 20 == 0:
                        print(
                            json.dumps(
                                {"task_id": task, "actions_completed": index + 1}
                            ),
                            flush=True,
                        )
        if store.read("worker_results", replay_id) is None:
            run_worker(IMAGE, bundle, store, replay_id, request)
        for key in (live_id, replay_id):
            if store.read("native_evaluation", key) is None:
                evaluate_worker_output(IMAGE, native_data, store, key, task)
        frame = store.read("worker_results", live_id)
        errors = tuple(
            index
            for index, item in enumerate(frame["results"])
            if item["output"].startswith("Execution failed.")
        )
        paired, exclusion = None, None
        try:
            paired = audit_prefix_runs(
                store, [[live_id, replay_id]], expected_error_indices=errors
            )
        except IntegrityError as exc:
            exclusion = str(exc)
        if (
            store.read("worker_requests", live_id) != request
            or store.read("worker_requests", replay_id) != request
            or len(frame["results"]) != len(request["actions"])
        ):
            raise IntegrityError(
                "executed source differs from the exact archive sequence"
            )
        frames = [
            store.read("stream_frames", f"{live_id}-{index:03d}")
            for index in range(len(request["actions"]) + 1)
        ]
        if any(item is None for item in frames):
            raise IntegrityError("missing local source boundary")
        differences = [
            index
            for index, (old, new) in enumerate(
                zip(parsed[task]["interactions"], frame["results"], strict=True)
            )
            if old["output"] != new["output"]
        ]
        row = {
            "task_id": task,
            "protocol_digest": digest(protocol),
            "source_parsed_digest": source_audit["parsed_digests"][task],
            "request_digest": digest(request),
            "live_run": live_id,
            "replay_run": replay_id,
            "actions": len(request["actions"]),
            "completion_flag": frame["completion_flag"],
            "native_evaluation": store.read("native_evaluation", live_id),
            "eligible_for_local_source": paired is not None,
            "exclusion": exclusion,
            "paired_audit_digest": digest(paired) if paired is not None else None,
            "action_error_indices": list(errors),
            "unsupported_boundary_indices": [
                index
                for index, item in enumerate(frames)
                if item["harness_only_state"]["namespace"]["unsupported"]
            ],
            "archived_output_difference_indices": differences,
            "exact_archived_output_match": not differences,
            "local_elapsed_seconds": time.perf_counter() - started,
            "model_calls": 0,
        }
        store.write("replayed_sources", task, row)
        rows.append(row)
        print(
            json.dumps(
                {
                    "task_id": task,
                    "native_success": row["native_evaluation"]["native_success"],
                    "eligible": row["eligible_for_local_source"],
                    "actions": row["actions"],
                    "local_action_errors": len(errors),
                    "archived_output_differences": len(differences),
                    "exclusion": exclusion,
                }
            ),
            flush=True,
        )
    new_mixed = new_mixed_tasks(prior_outcomes, rows)
    report = {
        "protocol_digest": digest(protocol),
        "rows": rows,
        "complete_registered_sample": len(rows) == len(selection["build"]),
        "new_mixed_tasks": new_mixed,
        "primary_metric": len(new_mixed),
        "previously_unmixed_opportunities": sum(
            len(set(values)) == 1 for values in prior_outcomes.values()
        ),
        "native_successes": sum(
            row["native_evaluation"]["native_success"] for row in rows
        ),
        "eligible_sources": sum(row["eligible_for_local_source"] for row in rows),
        "model_calls": 0,
        "api_usd": 0,
        "native_executions": len(list((store.root / "worker_results").glob("*.json"))),
        "native_evaluations": len(
            list((store.root / "native_evaluation").glob("*.json"))
        ),
        "decision": "KEEP"
        if new_mixed
        and len(rows) == len(selection["build"])
        and all(
            row["exclusion"] is None
            or row["exclusion"]
            == "unsupported namespace state; checkpoint is unverified"
            for row in rows
        )
        else "REVISE",
        "status": "locally_replayed_archived_program_source_only_not_original_agent_reproduction_or_contract_admission",
    }
    store.write("reports", digest(report), report)
    print(
        json.dumps(
            {
                "report_id": digest(report),
                **{key: value for key, value in report.items() if key != "rows"},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
