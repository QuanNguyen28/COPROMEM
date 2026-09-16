"""Frozen 100-action boundary and exact historical-state regression; no models."""

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

IMAGE = "sha256:fe315fb9624642ea25abd1687dc0694b4868dde3066a71ada0ab4d69911d4c33"
BUILD = "87cb10352263dfa00554fc8cf7707512ef94168650a5bedf8626c275051268d3"


def main():
    root = Path(__file__).resolve().parents[2]
    store = RunStore(root / "artifacts/research/cycle16_runtime_gate")
    old = RunStore(root / "artifacts/research/cycle11_appworld_source")
    native = root / "artifacts/research/appworld_preflight_20260916/data"
    build = store.read("builds", BUILD)
    if build is None or build.get("image_id") != IMAGE or build["exit_code"] != 0:
        raise IntegrityError("pinned long-source build is missing")
    old_id = "c11-aa8502b_1-r1"
    old_request = old.read("worker_requests", old_id)
    old_frame = old.read("worker_results", old_id)
    old_score = old.read("native_evaluation", old_id)
    source_audit = old.read(
        "source_audits",
        "533d57244a03fbd412ee658d313596131fbb4d3c2743f3825afa16e6a5ce6f76",
    )
    if (
        source_audit is None
        or digest(source_audit)
        != "533d57244a03fbd412ee658d313596131fbb4d3c2743f3825afa16e6a5ce6f76"
        or old_request is None
        or old_frame is None
        or not old_score["native_success"]
    ):
        raise IntegrityError("historical registered success evidence is missing")
    if old_frame["request_id"] != digest(old_request):
        raise IntegrityError("historical request/frame mismatch")
    historic_errors = tuple(
        i
        for i, item in enumerate(old_frame["results"])
        if item["output"].startswith("Execution failed.")
    )
    cases = [
        (
            "boundary100",
            {
                "task_id": "27e1026_1",
                "seed": 100,
                "actions": ["counter = 0\nprint(counter)"]
                + ["counter += 1\nprint(counter)"] * 99,
            },
            (),
        ),
        ("historical_success", old_request, historic_errors),
    ]
    protocol = {
        "image_id": IMAGE,
        "build_source_id": BUILD,
        "preregistration": "research/035_CYCLE16_LONG_SOURCE_RUNTIME_GATE.md",
        "cases": [
            {"name": name, "request": request, "expected_errors": errors}
            for name, request, errors in cases
        ],
        "old_frame_digest": digest(old_frame),
        "old_score_digest": digest(old_score),
        "source_audit_digest": digest(source_audit),
        "model_calls": 0,
    }
    texts = {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in [
            Path(__file__),
            root / protocol["preregistration"],
            root / "research/containers/appworld/worker.py",
            root / "research/containers/appworld/worker_long_source.py",
            root / "research/containers/appworld/Dockerfile.longsource",
            root / "src/copromem/checkpoints.py",
            root / "src/copromem/stateful_adapter.py",
            root / "src/copromem/stateful_stream.py",
        ]
    }
    store.bind_provenance(
        {
            "protocol_digest": digest(protocol),
            "source_hashes": {path: digest(value) for path, value in texts.items()},
        }
    )
    store.write("protocol", "runtime_gate", protocol)
    store.write("source_snapshots", digest(texts), texts)
    reports = []
    for name, request, errors in cases:
        ids = ["c16a-" + name + "-live", "c16a-" + name + "-replay"]
        if store.read("worker_results", ids[0]) is None:
            with StreamWorker(
                IMAGE,
                old.root / "public_bundle",
                store,
                ids[0],
                request["task_id"],
                request["seed"],
            ) as worker:
                for index, code in enumerate(request["actions"]):
                    worker.act(code)
                    if (index + 1) % 20 == 0:
                        print(
                            json.dumps({"case": name, "actions_completed": index + 1}),
                            flush=True,
                        )
        if store.read("worker_results", ids[1]) is None:
            run_worker(IMAGE, old.root / "public_bundle", store, ids[1], request)
        for key in ids:
            if store.read("native_evaluation", key) is None:
                evaluate_worker_output(IMAGE, native, store, key, request["task_id"])
        audit = audit_prefix_runs(store, [ids], expected_error_indices=errors)
        frame = store.read("worker_results", ids[0])
        if frame["action_limit"] != 100 or len(frame["results"]) != len(
            request["actions"]
        ):
            raise IntegrityError("wrong native action capacity or incomplete sequence")
        if name == "boundary100":
            if frame["harness_only_state"]["namespace"]["serializable"]["counter"] != [
                "int",
                99,
            ]:
                raise IntegrityError("100-action boundary lost counter updates")
        elif (
            public_observation(frame) != public_observation(old_frame)
            or frame["state_digest"] != old_frame["state_digest"]
            or frame["initial_database_files"] != old_frame["initial_database_files"]
            or store.read("native_evaluation", ids[0]) != old_score
        ):
            raise IntegrityError(
                "historical public, full supported state, initial DB or native score changed"
            )
        reports.append(
            {
                "case": name,
                "audit_digest": digest(audit),
                "actions": len(request["actions"]),
                "historical_state_unchanged": name == "historical_success",
            }
        )
        print(
            json.dumps(
                {"case": name, "passed": True, "actions": len(request["actions"])}
            ),
            flush=True,
        )
    record = {
        "protocol_digest": digest(protocol),
        "cases": reports,
        "decision": "KEEP",
        "model_calls": 0,
        "native_executions": 4,
        "native_evaluations": 4,
        "limitation": "Two bounded engineering cases only, not arbitrary Python equivalence, new source outcomes, memory, scope or transfer.",
    }
    store.write("runtime_gate_reports", digest(record), record)
    print(json.dumps({"report_id": digest(record), **record}, indent=2))


if __name__ == "__main__":
    main()
