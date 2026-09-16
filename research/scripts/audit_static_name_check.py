"""Repeat every pinned checker invocation and independently count local labels."""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUN = runpy.run_path(str(HERE / "run_static_name_check.py"))
CHECK = runpy.run_path(str(HERE / "static_name_check.py"))


def require(value: bool, message: str) -> None:
    if not value:
        raise IntegrityError(message)


def same_process(original: dict, repeated: dict) -> None:
    require(
        original == repeated,
        "pinned checker stdout/stderr/status/input did not repeat exactly",
    )


def audit(store: RunStore) -> dict:
    report = RUN["run"](store, audit_only=True)
    protocol = store.read("protocol", "preregistration")
    snapshot = store.read("source_snapshots", protocol["source_snapshot"])
    require(
        digest(snapshot) == protocol["source_snapshot"]
        and all(
            (ROOT / name).read_text(encoding="utf-8") == value
            for name, value in snapshot.items()
        ),
        "frozen checker/source snapshot mismatch",
    )
    profile = store.read("tool_profiles", protocol["tool_profile"])
    CHECK["verify_tool"](profile)
    cases = [store.read("cases", key) for key in protocol["case_ids"]]
    keys = set()
    for row in report["rows"]:
        key = row["key"]
        keys.add(key)
        original = store.read("checker_processes", key)
        require(
            store.read("checker_attempts", key)
            == {
                "argv": [profile["executable"], *protocol["checker_options"]],
                "stdin_digest": digest(row["analysis"]["source"]),
            },
            "original checker attempt binding mismatch",
        )
        repeated = store.read("checker_repeat_processes", key)
        if repeated is None:
            require(
                store.read("checker_repeat_attempts", key) is None,
                "unresolved checker repeat; no silent restart",
            )
            store.write(
                "checker_repeat_attempts",
                key,
                {
                    "original_process_digest": digest(original),
                    "tool_profile": digest(profile),
                },
            )
            try:
                repeated = CHECK["invocation"](
                    profile["executable"],
                    protocol["checker_options"],
                    original["stdin"],
                )
            except Exception as exc:
                store.write(
                    "checker_repeat_failures",
                    key,
                    {
                        "error_type": type(exc).__name__,
                        "silent_restart_permitted": False,
                    },
                )
                raise
            store.write("checker_repeat_processes", key, repeated)
        same_process(original, repeated)
        require(
            CHECK["parse_findings"](repeated, row["analysis"]) == row["parsed"],
            "repeated findings differ",
        )
    CHECK["verify_tool"](profile)
    by_key = {(r["case_index"], r["context"]): r for r in report["rows"]}
    eligible = []
    for i, case in enumerate(cases):
        require(
            CHECK["local_label"](case["public_action_output"]) == case["local_label"],
            "local label differs from public action output",
        )
        if type(case["local_label"]["label"]) is bool and all(
            by_key[i, c]["analysis"]["covered"] and by_key[i, c]["parsed"]["valid"]
            for c in (False, True)
        ):
            eligible.append(i)
    recomputed = {}
    detected, false_warnings = {}, {}
    for context, name in ((False, "no_context"), (True, "public_context")):
        positive = {i for i in eligible if cases[i]["local_label"]["label"]}
        negative = set(eligible) - positive
        warnings = {
            i for i in eligible if by_key[i, context]["parsed"]["warning_names"]
        }
        detected[context] = warnings & positive
        false_warnings[context] = warnings & negative
        recomputed[name] = {
            "eligible_actions": len(eligible),
            "true_warning": len(warnings & positive),
            "false_warning": len(warnings & negative),
            "true_clear": len(negative - warnings),
            "missed_name_error": len(positive - warnings),
            "detected_name_error_indices": sorted(warnings & positive),
            "exact_error_name_detected_indices": sorted(
                i
                for i in positive
                if cases[i]["local_label"]["name"]
                in by_key[i, context]["parsed"]["warning_names"]
            ),
            "false_warning_indices": sorted(warnings & negative),
        }
    loss = sorted(detected[False] - detected[True])
    reduction = len(false_warnings[False]) - len(false_warnings[True])
    passed = bool(eligible and reduction > 0 and not loss)
    require(
        report["metrics"] == recomputed
        and report["eligible_indices"] == eligible
        and report["false_warning_reduction"] == reduction
        and report["lost_true_detections"] == loss
        and report["primary_passed"] == passed
        and report["decision"] == ("KEEP" if passed else "REVISE"),
        "independent component metrics differ",
    )
    for kind, expected in (
        ("checker_repeat_processes", keys),
        ("checker_repeat_attempts", keys),
        ("checker_failures", set()),
        ("checker_repeat_failures", set()),
        ("calls", set()),
        ("worker_results", set()),
        ("native_evaluation", set()),
    ):
        require(
            {p.stem for p in (store.root / kind).glob("*.json")} == expected,
            "missing or extra component audit records: " + kind,
        )
    texts = {
        p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8")
        for p in (Path(__file__).resolve(), ROOT / "tests/test_static_checker_audit.py")
    }
    store.write("audit_source_snapshots", digest(texts), texts)
    return {
        "audit": "exact-pinned-f821-repeat-plus-independent-local-label-metrics-v1",
        "protocol_digest": digest(protocol),
        "report_digest": digest(report),
        "source_snapshot": protocol["source_snapshot"],
        "audit_source_snapshot": digest(texts),
        "tool_profile": digest(profile),
        "current_sources_equal_frozen": True,
        "complete_cases": 14,
        "original_checker_configurations": 28,
        "exact_checker_repeats": len(keys),
        "total_recorded_main_checker_processes": 56,
        "metadata_and_toy_fixtures_counted_separately": True,
        "metrics": recomputed,
        "decision": report["decision"],
        "model_calls": 0,
        "native_executions": 0,
        "api_usd": 0,
        "admitted_contracts": 0,
        "limitation": report["limitation"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store",
        type=Path,
        default=Path("artifacts/research/cycle22_static_name_check"),
    )
    args = parser.parse_args()
    store = RunStore(args.store)
    record = audit(store)
    store.write("component_audits", digest(record), record)
    print(json.dumps({"audit_digest": digest(record), **record}, indent=2))


if __name__ == "__main__":
    main()
