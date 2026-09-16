"""Zero-model-call long-prefix and previously unsupported-state regressions."""

from __future__ import annotations

import json
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest
from copromem.stateful_adapter import (
    audit_prefix_runs,
    evaluate_worker_output,
    public_observation,
    run_worker,
)
from copromem.stateful_stream import StreamWorker

IMAGE = "sha256:b5f9aaedde041e30fc4ff795ab46d47849cfc72701b9ffc8c8983fdefe36fcf6"


def main():
    root = Path(__file__).resolve().parents[2]
    store = RunStore(root / "artifacts/research/cycle10_runtime_gate")
    source = RunStore(root / "artifacts/research/cycle09_appworld_source")
    native_data = root / "artifacts/research/appworld_preflight_20260916/data"
    historic_id = "c09-27e1026_1-r1"
    fixture = json.loads(
        (root / "research/configs/cycle10_runtime_probe.json").read_text()
    )
    historic = source.read("worker_requests", historic_id)
    if historic is None:
        raise IntegrityError("registered historical regression prefix is missing")
    cases = [
        (
            "long",
            fixture,
            root / "artifacts/research/cycle05_stateful/public_bundle",
            (3,),
        ),
        (
            "historic",
            historic,
            source.root / "public_bundle",
            tuple(
                index
                for index, result in enumerate(
                    source.read("worker_results", historic_id)["results"]
                )
                if result["output"].startswith("Execution failed.")
            ),
        ),
    ]
    protocol = {
        "image_id": IMAGE,
        "model_calls": 0,
        "cases": [
            {"name": name, "request": req, "expected_errors": errors}
            for name, req, _, errors in cases
        ],
        "note": "Engineering regression only; old source ineligibility and native task outcomes are not revised.",
    }
    store.write("protocol", "local_runtime_gate", protocol)
    source_texts = {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in [
            root / "src/copromem/stateful_adapter.py",
            root / "src/copromem/stateful_stream.py",
            root / "src/copromem/checkpoints.py",
            root / "research/containers/appworld/worker.py",
            Path(__file__).resolve(),
        ]
    }
    store.bind_provenance(
        {
            "image_id": IMAGE,
            "source_hashes": {
                key: digest(value) for key, value in source_texts.items()
            },
        }
    )
    store.write("source_snapshots", digest(source_texts), source_texts)
    reports = []
    for name, request, bundle, errors in cases:
        live_id, replay_id = "c10-" + name + "-live", "c10-" + name + "-replay"
        if store.read("worker_results", live_id) is None:
            with StreamWorker(
                IMAGE, bundle, store, live_id, request["task_id"], request["seed"]
            ) as worker:
                for program in request["actions"]:
                    worker.act(program)
        if store.read("worker_results", replay_id) is None:
            run_worker(IMAGE, bundle, store, replay_id, request)
        for run_id in (live_id, replay_id):
            if store.read("native_evaluation", run_id) is None:
                evaluate_worker_output(
                    IMAGE, native_data, store, run_id, request["task_id"]
                )
        paired = audit_prefix_runs(
            store, [[live_id, replay_id]], expected_error_indices=errors
        )
        observed = store.read("worker_results", live_id)
        if observed["action_limit"] != 50:
            raise IntegrityError(
                "runtime did not advertise its registered action capacity"
            )
        if name == "long":
            state = observed["harness_only_state"]["namespace"]["serializable"]
            if (
                len(observed["results"]),
                state["counter"],
                state["upper_bound"],
                state["lower_bound"],
            ) != (
                25,
                ["int", 19],
                ["float_infinity", "+"],
                ["float_infinity", "-"],
            ):
                raise IntegrityError("long-prefix numeric state differs from fixture")
        else:
            old = source.read("worker_results", historic_id)
            if public_observation(old) != public_observation(observed):
                raise IntegrityError("historical public action effects changed")
            if source.read("native_evaluation", historic_id) != store.read(
                "native_evaluation", live_id
            ):
                raise IntegrityError("historical native score changed")
            if (
                old["harness_only_state"]["database_files"]
                != observed["harness_only_state"]["database_files"]
            ):
                raise IntegrityError("historical database state changed")
        reports.append({"case": name, "paired_audit": paired, "model_calls": 0})
        print(
            json.dumps(
                {"case": name, "paired": True, "steps": len(observed["results"])}
            ),
            flush=True,
        )
    report = {
        "cases": reports,
        "model_calls": 0,
        "decision": "KEEP",
        "claim": "Bounded runtime regression only; no learned efficacy or source success.",
    }
    store.write("reports", digest(report), report)
    print(
        json.dumps(
            {
                "report_id": digest(report),
                "passed_cases": len(reports),
                "model_calls": 0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
