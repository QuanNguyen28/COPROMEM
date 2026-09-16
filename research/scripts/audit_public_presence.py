"""Independently bind cycle-21 public observations to raw native executions."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import runpy
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest
from copromem.stateful_adapter import audit_prefix_runs, verify_prefix_pair
from copromem.stateful_effect import api_log_count, error_indices, origin_checkpoint

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUN = runpy.run_path(str(HERE / "run_public_presence.py"))
RAW = runpy.run_path(str(HERE / "audit_boundary_effects.py"))
PUBLIC = runpy.run_path(str(HERE / "public_presence.py"))
require = RAW["require"]


def verify_log_prefix(raw: bytes, prefix: dict) -> None:
    require(
        set(prefix) == {"bytes", "sha256", "entries"},
        "invalid API prefix evidence schema",
    )
    size = prefix["bytes"]
    require(
        type(size) is int and 0 <= size <= len(raw), "invalid API prefix byte count"
    )
    value = raw[:size]
    require(not value or value.endswith(b"\n"), "API prefix cuts a native record")
    require(
        hashlib.sha256(value).hexdigest() == prefix["sha256"]
        and sum(bool(line.strip()) for line in value.splitlines()) == prefix["entries"],
        "native API prefix hash/entry count mismatch",
    )


def audit(store: RunStore) -> dict:
    protocol = store.read("protocol", "preregistration")
    snapshot = store.read("source_snapshots", protocol["source_snapshot"])
    require(
        digest(snapshot) == protocol["source_snapshot"],
        "frozen presence source snapshot corrupt",
    )
    require(
        all(
            (ROOT / name).read_text(encoding="utf-8") == value
            for name, value in snapshot.items()
        ),
        "current source differs from frozen presence experiment",
    )
    boundaries, source_audits = RUN["source_boundaries"]()
    require(
        [digest(b) for b in boundaries] == protocol["boundary_ids"],
        "registered three boundaries/queries changed",
    )
    require(
        {k: digest(v) for k, v in source_audits.items()} == protocol["source_audits"],
        "source effect audit changed",
    )
    bundle = ROOT / protocol["public_bundle"]
    manifest = RunStore(bundle).read("manifest", "public_bundle")
    require(
        digest(manifest) == protocol["public_bundle_manifest"],
        "public manifest changed",
    )
    actual = {
        p.relative_to(bundle).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((bundle / "data").rglob("*"))
        if p.is_file()
    }
    require(
        actual == manifest["files"] and len(actual) == 150,
        "public bundle files changed",
    )
    report_paths = list((store.root / "reports").glob("*.json"))
    require(len(report_paths) == 1, "expected one complete observation report")
    report = store.read("reports", report_paths[0].stem)
    require(
        digest(report) == report_paths[0].stem
        and report["protocol_digest"] == digest(protocol),
        "presence report corrupted",
    )
    frames, inputs, runs, cells, probes, rows = set(), set(), set(), set(), set(), []
    for probe in (False, True):
        for index, boundary in enumerate(boundaries):
            key = f"c21-{'probe' if probe else 'control'}-{index:02d}"
            cells.add(key)
            live, replay = key + "-live", key + "-replay"
            runs.update((live, replay))
            row = store.read("observation_cells", key)
            offset, full = boundary["index"], boundary["original_request"]
            query = boundary["construction"]["query"]
            request = {
                **full,
                "actions": [
                    *full["actions"][:offset],
                    *([query] if probe else []),
                    *full["actions"][offset:],
                ],
            }
            expected_binding = {
                "protocol_digest": digest(protocol),
                "boundary_digest": digest(boundary),
                "request_digest": digest(request),
                "checkpoint_digest": digest(origin_checkpoint(boundary["origin"])),
                "probe": probe,
            }
            require(
                store.read("bindings", key) == expected_binding,
                "presence cell binding changed",
            )
            found_frames, found_inputs = RAW["check_processes"](
                store, protocol, key, request, offset
            )
            frames.update(found_frames)
            inputs.update(found_inputs)
            before = store.read("stream_frames", live + "-000")
            verification = verify_prefix_pair(
                boundary["origin"]["frame"],
                before,
                expected_error_indices=error_indices(boundary["origin"]["frame"]),
            )
            require(
                store.read("pre_action_checks", key)
                == {**expected_binding, "verification": verification},
                "pre-query identity check mismatch",
            )
            final = store.read("worker_results", live)
            score = store.read("native_evaluation", live)
            source = RunStore(Path(boundary["source_store"]))
            original_frame = source.read("worker_results", boundary["episode"])
            original_score = source.read("native_evaluation", boundary["episode"])
            require(
                source.read("worker_requests", boundary["episode"]) == full,
                "original source continuation changed",
            )
            paired, exclusion = None, None
            try:
                paired = audit_prefix_runs(
                    store, [[live, replay]], expected_error_indices=error_indices(final)
                )
            except IntegrityError as exc:
                if str(exc) != "unsupported namespace state; checkpoint is unverified":
                    raise
                exclusion = str(exc)
            compared = final
            checks, envelope, output_error = None, None, None
            if probe:
                probes.add(key)
                after = store.read("stream_frames", live + "-001")
                require(
                    after["results"][-1]["program"] == query
                    and len(after["results"]) == len(before["results"]) + 1,
                    "different inserted public query",
                )
                logs = store.read("probe_api_prefixes", key)
                raw = (
                    store.root
                    / "native"
                    / live
                    / "outputs/canonical/tasks"
                    / full["task_id"]
                    / "logs/api_calls.jsonl"
                ).read_bytes()
                require(
                    set(logs) == {"before", "after"}, "probe API snapshots incomplete"
                )
                for prefix in logs.values():
                    verify_log_prefix(raw, prefix)
                checks = {
                    "supported": not before["harness_only_state"]["namespace"][
                        "unsupported"
                    ]
                    and not after["harness_only_state"]["namespace"]["unsupported"],
                    "state_unchanged": before["harness_only_state"]
                    == after["harness_only_state"],
                    "completion_unchanged": before["completion_flag"]
                    == after["completion_flag"],
                    "earlier_public_results_unchanged": before["results"]
                    == after["results"][:-1],
                    "api_log_unchanged": logs["before"] == logs["after"],
                }
                try:
                    envelope = PUBLIC["parse_output"](
                        after["results"][-1]["output"],
                        boundary["construction"]["names"],
                    )
                except ValueError as exc:
                    output_error = str(exc)
                require(
                    final["results"][offset]["program"] == query,
                    "final history lost inserted query",
                )
                compared = {
                    **final,
                    "request_id": digest(full),
                    "results": [
                        *final["results"][:offset],
                        *final["results"][offset + 1 :],
                    ],
                }
            invariant_error = None
            try:
                verify_prefix_pair(
                    original_frame,
                    compared,
                    expected_error_indices=error_indices(original_frame),
                )
            except IntegrityError as exc:
                if not probe:
                    raise
                invariant_error = str(exc)
            require(
                probe or score == original_score, "factual score differs from original"
            )
            entries = api_log_count(store, live, full["task_id"])
            source_entries = api_log_count(source, boundary["episode"], full["task_id"])
            passed = bool(
                paired
                and invariant_error is None
                and score == original_score
                and entries == source_entries
                and (not probe or (envelope is not None and all(checks.values())))
            )
            computed = {
                "cell_id": key,
                **expected_binding,
                "episode": boundary["episode"],
                "index": offset,
                "actions": len(request["actions"]),
                "extra_public_code_actions": int(probe),
                "native_evaluation": score,
                "source_native_evaluation": original_score,
                "replay_audit_digest": digest(paired) if paired else None,
                "replay_eligible": paired is not None,
                "exclusion": exclusion,
                "source_invariance_error": invariant_error,
                "probe_checks": checks,
                "public_envelope": envelope,
                "public_output_error": output_error,
                "native_api_log_entries": entries,
                "source_native_api_log_entries": source_entries,
                "gate_passed": passed,
                "model_calls": 0,
                "api_usd": 0,
            }
            require(
                set(row) == set(computed) | {"elapsed_seconds"}
                and all(row[k] == v for k, v in computed.items()),
                "presence outcome/observation/accounting did not regenerate",
            )
            require(
                isinstance(row["elapsed_seconds"], (int, float))
                and math.isfinite(row["elapsed_seconds"])
                and row["elapsed_seconds"] >= 0,
                "invalid measured duration",
            )
            rows.append(row)
    primary = sum(
        rows[i]["gate_passed"] and rows[i + 3]["gate_passed"] for i in range(3)
    )
    require(
        report["rows"] == rows
        and report["primary_metric"] == primary
        and report["decision"] == ("KEEP" if primary == 3 else "REVISE")
        and report["complete_registered_sample"] is True
        and report["native_executions"] == report["native_scorers"] == 12
        and report["model_calls"]
        == report["api_usd"]
        == report["admitted_contracts"]
        == 0,
        "complete primary result did not regenerate",
    )
    expected = {
        "observation_cells": cells,
        "bindings": cells,
        "pre_action_checks": cells,
        "probe_api_prefixes": probes,
        "stream_frames": frames,
        "stream_inputs": inputs,
        **{
            kind: runs
            for kind in (
                "worker_requests",
                "worker_results",
                "worker_commands",
                "worker_processes",
                "native_evaluation",
                "evaluator_processes",
                "evaluator_commands",
            )
        },
        "boundaries": {digest(b) for b in boundaries},
        "public_inputs": {digest(b["public_input"]) for b in boundaries},
        "queries": {digest(b["construction"]) for b in boundaries},
        "source_audits": set(source_audits),
        **{
            kind: set()
            for kind in (
                "calls",
                "reservations",
                "settlements",
                "transport_attempts",
                "observation_failures",
                "partial_worker_results",
            )
        },
    }
    for kind, names in expected.items():
        require(
            {p.stem for p in (store.root / kind).glob("*.json")} == names,
            "missing or extra observation record: " + kind,
        )
    for boundary in boundaries:
        require(
            store.read("boundaries", digest(boundary)) == boundary
            and store.read("public_inputs", digest(boundary["public_input"]))
            == boundary["public_input"]
            and store.read("queries", digest(boundary["construction"]))
            == boundary["construction"],
            "public construction/source record changed",
        )
    require(
        all(
            store.read("source_audits", name) == value
            for name, value in source_audits.items()
        ),
        "source audit evidence changed",
    )
    return {
        "audit": "raw-native-public-presence-noninterference-v1",
        "protocol_digest": digest(protocol),
        "report_digest": digest(report),
        "source_snapshot": protocol["source_snapshot"],
        "current_sources_equal_frozen": True,
        "complete_cells": len(cells),
        "native_executions": len(runs),
        "live_frames": len(frames),
        "live_inputs": len(inputs),
        "primary_metric": primary,
        "decision": report["decision"],
        "model_calls": 0,
        "audit_native_executions": 0,
        "api_usd": 0,
        "admitted_contracts": 0,
        "limitation": report["limitation"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store", type=Path, default=Path("artifacts/research/cycle21_public_presence")
    )
    args = parser.parse_args()
    store = RunStore(args.store)
    record = audit(store)
    store.write("observation_audits", digest(record), record)
    print(json.dumps({"audit_digest": digest(record), **record}, indent=2))


if __name__ == "__main__":
    main()
