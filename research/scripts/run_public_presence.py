"""Cycle-21 fixed-checkpoint public presence queries with unchanged continuations."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import runpy
import time
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PUBLIC = runpy.run_path(str(HERE / "public_presence.py"))
IMAGE = "sha256:b5f9aaedde041e30fc4ff795ab46d47849cfc72701b9ffc8c8983fdefe36fcf6"
CANONICAL_AST = "45c299c43e68a9e627fc074073eff39dc0118e137d6f0b66afb59572c7338db3"
DELETION_AST = "3b6e3851403f4a101337fc8401784c933f2dd7fd3214d56f306bc9054058ee9e"
NEW_CANDIDATE = "70c1d9f82e108bd06798add563d04e35f37cca8d003fbeae811aad468cb5239a"


def require(value: bool, message: str) -> None:
    if not value:
        raise IntegrityError(message)


def source_boundaries() -> tuple[list[dict], dict]:
    old = RunStore(ROOT / "artifacts/research/cycle13_procedural_diff")
    new = RunStore(ROOT / "artifacts/research/cycle18_bound_effects")
    audits = {
        "c13": runpy.run_path(str(HERE / "audit_procedural_diff.py"))["audit"](
            old, "3b804f5a064696081627852d0eb3046e761a7dae49ec410d8ecb92d1da2a166d"
        ),
        "c18": runpy.run_path(str(HERE / "audit_bound_effects.py"))["audit"](new),
    }
    canonical = old.read("variant_proposals", "p0-" + CANONICAL_AST)
    deletion = old.read("variant_proposals", "p0-" + DELETION_AST)
    candidate = new.read("effect_candidates", NEW_CANDIDATE)
    require(digest(candidate) == NEW_CANDIDATE, "registered new origin changed")
    specifications = [
        (origin, [canonical["program"], deletion["program"]])
        for origin in old.read("protocol", "preregistration")["source_protocol"][
            "pairs"
        ][0]
    ] + [(candidate["origin"], [candidate["proposal"]["program"]])]
    expected = [
        ("c11-aa8502b_1-r0", 13),
        ("c11-aa8502b_1-r1", 10),
        ("c11-b7a9ee9_1-r0", 19),
    ]
    source = RunStore(ROOT / "artifacts/research/cycle11_appworld_source")
    result = []
    for (origin, programs), (episode, index) in zip(
        specifications, expected, strict=True
    ):
        require(
            origin["episode"]["episode_id"] == episode
            and origin["step"]["step"] == index,
            "selected boundary changed",
        )
        require(
            source.read("source_episodes", episode) == origin["episode"],
            "source episode provenance mismatch",
        )
        public = {
            "programs": [origin["step"]["code"], *programs],
            "prefix": origin["prefix_request"]["actions"],
        }
        construction = PUBLIC["construct"](public)
        checkpoint = origin_checkpoint(origin)
        full = source.read("worker_requests", episode)
        require(
            full["actions"][:index] == public["prefix"]
            and full["actions"][index] == origin["step"]["code"],
            "original continuation differs",
        )
        require(
            len(full["actions"]) + 1 <= 50, "probe would exceed unchanged action cap"
        )
        result.append(
            {
                "origin": origin,
                "checkpoint": checkpoint,
                "episode": episode,
                "index": index,
                "source_store": str(source.root),
                "original_request": full,
                "public_input": public,
                "construction": construction,
            }
        )
    return result, audits


def insertion_request(boundary: dict, probe: bool) -> dict:
    full, index = boundary["original_request"], boundary["index"]
    prefix = boundary["origin"]["prefix_request"]
    require(
        full["task_id"] == prefix["task_id"]
        and full["seed"] == prefix["seed"]
        and index == len(prefix["actions"])
        and full["actions"][:index] == prefix["actions"]
        and full["actions"][index] == boundary["origin"]["step"]["code"],
        "not the registered origin prefix/action",
    )
    return {
        **full,
        "actions": [
            *full["actions"][:index],
            *([boundary["construction"]["query"]] if probe else []),
            *full["actions"][index:],
        ],
    }


def normalized_final(frame: dict, original: dict, index: int, query: str) -> dict:
    require(frame["results"][index]["program"] == query, "wrong removed probe action")
    expected = {
        **original,
        "actions": [*original["actions"][:index], query, *original["actions"][index:]],
    }
    require(
        frame["request_id"] == digest(expected)
        and [r["program"] for r in frame["results"]] == expected["actions"],
        "probe final request/action identity mismatch",
    )
    normalized = copy.deepcopy(frame)
    normalized["results"].pop(index)
    normalized["request_id"] = digest(original)
    return normalized


def log_prefix(store: RunStore, run_id: str, task: str) -> dict:
    path = (
        store.root
        / "native"
        / run_id
        / "outputs/canonical/tasks"
        / task
        / "logs/api_calls.jsonl"
    )
    value = path.read_bytes()
    return {
        "bytes": len(value),
        "sha256": hashlib.sha256(value).hexdigest(),
        "entries": sum(bool(line.strip()) for line in value.splitlines()),
    }


def compare_probe(
    before: dict, after: dict, query: str, prelog: dict, postlog: dict
) -> dict:
    for frame in (before, after):
        require(
            frame["state_digest"] == digest(frame["harness_only_state"]),
            "probe state digest corrupted",
        )
    require(
        len(after["results"]) == len(before["results"]) + 1
        and after["results"][-1]["program"] == query,
        "probe frame is not one inserted query",
    )
    return {
        "supported": not before["harness_only_state"]["namespace"]["unsupported"]
        and not after["harness_only_state"]["namespace"]["unsupported"],
        "state_unchanged": before["harness_only_state"] == after["harness_only_state"],
        "completion_unchanged": before["completion_flag"] == after["completion_flag"],
        "earlier_public_results_unchanged": before["results"] == after["results"][:-1],
        "api_log_unchanged": prelog == postlog,
    }


def evaluate_cell(store: RunStore, boundary: dict, key: str, probe: bool) -> dict:
    source = RunStore(Path(boundary["source_store"]))
    old_frame = source.read("worker_results", boundary["episode"])
    old_score = source.read("native_evaluation", boundary["episode"])
    live, replay = key + "-live", key + "-replay"
    final = store.read("worker_results", live)
    score = store.read("native_evaluation", live)
    paired, exclusion = None, None
    try:
        paired = audit_prefix_runs(
            store, [[live, replay]], expected_error_indices=error_indices(final)
        )
    except IntegrityError as exc:
        if str(exc) != "unsupported namespace state; checkpoint is unverified":
            raise
        exclusion = str(exc)
    comparison = (
        normalized_final(
            final,
            boundary["original_request"],
            boundary["index"],
            boundary["construction"]["query"],
        )
        if probe
        else final
    )
    invariant_error = None
    try:
        verify_prefix_pair(
            old_frame, comparison, expected_error_indices=error_indices(old_frame)
        )
    except IntegrityError as exc:
        if not probe:
            raise
        invariant_error = str(exc)
    require(probe or score == old_score, "fresh factual native score changed")
    checks, envelope, output_error = None, None, None
    if probe:
        before = store.read("stream_frames", live + "-000")
        after = store.read("stream_frames", live + "-001")
        logs = store.read("probe_api_prefixes", key)
        checks = compare_probe(
            before,
            after,
            boundary["construction"]["query"],
            logs["before"],
            logs["after"],
        )
        try:
            envelope = PUBLIC["parse_output"](
                after["results"][-1]["output"], boundary["construction"]["names"]
            )
        except ValueError as exc:
            output_error = str(exc)
    api_entries = api_log_count(store, live, final["task_id"])
    source_entries = api_log_count(source, boundary["episode"], final["task_id"])
    passed = bool(
        paired
        and invariant_error is None
        and score == old_score
        and api_entries == source_entries
        and (not probe or (envelope is not None and all(checks.values())))
    )
    return {
        "native_evaluation": score,
        "source_native_evaluation": old_score,
        "replay_audit_digest": digest(paired) if paired else None,
        "replay_eligible": paired is not None,
        "exclusion": exclusion,
        "source_invariance_error": invariant_error,
        "probe_checks": checks,
        "public_envelope": envelope,
        "public_output_error": output_error,
        "native_api_log_entries": api_entries,
        "source_native_api_log_entries": source_entries,
        "gate_passed": passed,
    }


def run_cell(
    store: RunStore, protocol: dict, boundary: dict, key: str, probe: bool
) -> dict:
    request = insertion_request(boundary, probe)
    binding = {
        "protocol_digest": digest(protocol),
        "boundary_digest": digest(boundary),
        "request_digest": digest(request),
        "checkpoint_digest": digest(boundary["checkpoint"]),
        "probe": probe,
    }
    store.write("bindings", key, binding)
    existing = store.read("observation_cells", key)
    if existing:
        require(
            all(existing[k] == v for k, v in binding.items()),
            "completed observation binding changed",
        )
        return existing
    started = time.monotonic()
    live, replay = key + "-live", key + "-replay"
    index, task = boundary["index"], request["task_id"]
    try:
        if store.read("worker_results", live) is None:
            with StreamWorker(
                IMAGE,
                ROOT / protocol["public_bundle"],
                store,
                live,
                task,
                request["seed"],
                actions=request["actions"][:index],
            ) as worker:
                verified = verify_prefix_pair(
                    boundary["origin"]["frame"],
                    worker.last,
                    expected_error_indices=error_indices(boundary["origin"]["frame"]),
                )
                store.write(
                    "pre_action_checks", key, {**binding, "verification": verified}
                )
                if probe:
                    prelog = log_prefix(store, live, task)
                    worker.act(boundary["construction"]["query"])
                    store.write(
                        "probe_api_prefixes",
                        key,
                        {"before": prelog, "after": log_prefix(store, live, task)},
                    )
                for action in boundary["original_request"]["actions"][index:]:
                    worker.act(action)
        require(
            store.read("worker_requests", live) == request,
            "observed live continuation changed",
        )
        if store.read("worker_results", replay) is None:
            result = run_worker(
                IMAGE, ROOT / protocol["public_bundle"], store, replay, request
            )
            require(
                result.get("status") == "completed", "fresh public-query replay failed"
            )
        for run_id in (live, replay):
            if store.read("native_evaluation", run_id) is None:
                evaluate_worker_output(
                    IMAGE, ROOT / protocol["native_data"], store, run_id, task
                )
        row = {
            "cell_id": key,
            **binding,
            "episode": boundary["episode"],
            "index": index,
            "actions": len(request["actions"]),
            "extra_public_code_actions": int(probe),
            **evaluate_cell(store, boundary, key, probe),
            "elapsed_seconds": time.monotonic() - started,
            "model_calls": 0,
            "api_usd": 0,
        }
        store.write("observation_cells", key, row)
        return row
    except Exception as exc:
        store.write(
            "observation_failures",
            key,
            {
                **binding,
                "error_type": type(exc).__name__,
                "silent_restart_permitted": False,
            },
        )
        raise


def prepare(store: RunStore) -> tuple[dict, list[dict]]:
    print(
        json.dumps({"phase": "serial_source_audits_and_public_query_construction"}),
        flush=True,
    )
    boundaries, audits = source_boundaries()
    paths = [
        *sorted((ROOT / "src/copromem").glob("*.py")),
        Path(__file__).resolve(),
        HERE / "public_presence.py",
        ROOT / "research/048_CYCLE20_PREFLIGHT_RESULT_AND_PRESENCE_REVISION.md",
        ROOT / "research/047_CYCLE20_PUBLIC_BOUNDARY_OBSERVATION_GATE.md",
        ROOT / "tests/test_public_presence.py",
        ROOT / "tests/test_public_presence_effects.py",
        *sorted((ROOT / "research/containers/appworld").glob("*.py")),
    ]
    texts = {
        p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8") for p in paths
    }
    protocol = {
        "cycle": "cycle21-public-presence-noninterference",
        "image_id": IMAGE,
        "source_snapshot": digest(texts),
        "boundary_ids": [digest(b) for b in boundaries],
        "source_audits": {k: digest(v) for k, v in audits.items()},
        "public_bundle": "artifacts/research/cycle15_reflection_source/public_bundle",
        "public_bundle_manifest": "e5f5a2dae7640d2a364ec82861ad58ac86f3d0d62adf9d18d3250be14c234255",
        "native_data": "artifacts/research/appworld_preflight_20260916/data",
        "expected_cells": 6,
        "expected_native_executions": 12,
        "expected_native_scorers": 12,
        "model_calls": 0,
        "api_usd": 0,
    }
    require(
        digest(
            RunStore(ROOT / protocol["public_bundle"]).read("manifest", "public_bundle")
        )
        == protocol["public_bundle_manifest"],
        "public bundle manifest changed",
    )
    store.bind_provenance({"protocol_digest": digest(protocol)})
    store.write("protocol", "preregistration", protocol)
    store.write("source_snapshots", digest(texts), texts)
    for boundary in boundaries:
        store.write("boundaries", digest(boundary), boundary)
        store.write(
            "public_inputs", digest(boundary["public_input"]), boundary["public_input"]
        )
        store.write(
            "queries", digest(boundary["construction"]), boundary["construction"]
        )
    for name, audit in audits.items():
        store.write("source_audits", name, audit)
    return protocol, boundaries


def run(store: RunStore, *, prepare_only: bool = False) -> dict:
    protocol, boundaries = prepare(store)
    if prepare_only:
        return {
            "protocol_digest": digest(protocol),
            "names_per_boundary": [len(b["construction"]["names"]) for b in boundaries],
            "prepared_only": True,
        }
    rows = []
    for probe in (False, True):
        for i, boundary in enumerate(boundaries):
            key = f"c21-{'probe' if probe else 'control'}-{i:02d}"
            row = run_cell(store, protocol, boundary, key, probe)
            rows.append(row)
            print(
                json.dumps(
                    {
                        "cell": key,
                        "gate_passed": row["gate_passed"],
                        "source_invariance_error": row["source_invariance_error"],
                        "output_error": row["public_output_error"],
                    }
                ),
                flush=True,
            )
    primary = sum(
        rows[i]["gate_passed"] and rows[i + 3]["gate_passed"] for i in range(3)
    )
    report = {
        "protocol_digest": digest(protocol),
        "rows": rows,
        "primary_metric": primary,
        "decision": "KEEP" if primary == 3 else "REVISE",
        "complete_registered_sample": len(rows) == 6,
        "native_executions": len(list((store.root / "worker_results").glob("*.json"))),
        "native_scorers": len(list((store.root / "native_evaluation").glob("*.json"))),
        "model_calls": 0,
        "api_usd": 0,
        "admitted_contracts": 0,
        "limitation": "Public presence observation only, not type/length envelope, learned violation/scope, safe recovery or held-out advantage.",
    }
    require(
        report["native_executions"] == report["native_scorers"] == 12,
        "registered native denominator incomplete",
    )
    store.write("reports", digest(report), report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store", type=Path, default=Path("artifacts/research/cycle21_public_presence")
    )
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    report = run(RunStore(args.store), prepare_only=args.prepare_only)
    print(
        json.dumps(
            {
                "record_id": digest(report),
                **{k: v for k, v in report.items() if k != "rows"},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
