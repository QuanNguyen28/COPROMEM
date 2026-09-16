"""Preregistered context/no-context F821 comparison; no source code is executed."""

from __future__ import annotations

import argparse
import json
import runpy
from collections import Counter
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CHECK = runpy.run_path(str(HERE / "static_name_check.py"))
SOURCE = runpy.run_path(str(HERE / "static_name_sources.py"))
PREFLIGHT = "0ca17e819fd654cb8904faa485c2a19bc17bc7f2a84bfd74a468dc13ae62d6a0"


def summarize(cases: list[dict], results: list[dict]) -> dict:
    if len(cases) != 14 or len(results) != 28:
        raise IntegrityError("registered source/checker denominator incomplete")
    by_key = {(r["case_index"], r["context"]): r for r in results}
    if len(by_key) != 28 or set(by_key) != {
        (i, c) for i in range(14) for c in (False, True)
    }:
        raise IntegrityError("duplicate or missing paired checker configuration")
    eligible = [
        i
        for i, case in enumerate(cases)
        if type(case["local_label"]["label"]) is bool
        and all(
            by_key[i, c]["parsed"]["valid"] and by_key[i, c]["analysis"]["covered"]
            for c in (False, True)
        )
    ]
    metrics, detected, false_warnings = {}, {}, {}
    for context in (False, True):
        values = Counter(
            {
                "true_warning": 0,
                "false_warning": 0,
                "true_clear": 0,
                "missed_name_error": 0,
            }
        )
        detected[context], false_warnings[context] = set(), set()
        exact_names = []
        for i in eligible:
            label = cases[i]["local_label"]["label"]
            names = by_key[i, context]["parsed"]["warning_names"]
            if label and names:
                values["true_warning"] += 1
                detected[context].add(i)
            elif names:
                values["false_warning"] += 1
                false_warnings[context].add(i)
            elif label:
                values["missed_name_error"] += 1
            else:
                values["true_clear"] += 1
            if label and cases[i]["local_label"]["name"] in names:
                exact_names.append(i)
        metrics["public_context" if context else "no_context"] = {
            "eligible_actions": len(eligible),
            **dict(values),
            "detected_name_error_indices": sorted(detected[context]),
            "exact_error_name_detected_indices": exact_names,
            "false_warning_indices": sorted(false_warnings[context]),
        }
    lost = sorted(detected[False] - detected[True])
    reduction = len(false_warnings[False]) - len(false_warnings[True])
    return {
        "complete_registered_sample": True,
        "cases": 14,
        "checker_configurations": 28,
        "eligible_indices": eligible,
        "excluded_indices": [i for i in range(14) if i not in eligible],
        "label_kinds": dict(Counter(c["local_label"]["kind"] for c in cases)),
        "metrics": metrics,
        "lost_true_detections": lost,
        "false_warning_reduction": reduction,
        "primary_passed": bool(eligible and reduction > 0 and not lost),
        "decision": "KEEP" if eligible and reduction > 0 and not lost else "REVISE",
        "model_calls": 0,
        "native_executions": 0,
        "api_usd": 0,
        "admitted_contracts": 0,
    }


def prepare(store: RunStore) -> tuple[dict, list[dict], dict]:
    preflight = RunStore(ROOT / "artifacts/research/cycle22_checker_preflight")
    gate = preflight.read("reports", PREFLIGHT)
    if digest(gate) != PREFLIGHT or not gate["all_passed"]:
        raise IntegrityError("installed checker fixture gate changed")
    profile = preflight.read("tool_profiles", gate["tool_profile"])
    if digest(profile) != gate["tool_profile"]:
        raise IntegrityError("checker profile corrupted")
    CHECK["verify_tool"](profile)
    print(
        json.dumps(
            {"phase": "serial_source_audit_and_fourteen_public_context_bindings"}
        ),
        flush=True,
    )
    cases, source_audit = SOURCE["collect"]()
    paths = [
        *sorted((ROOT / "src/copromem").glob("*.py")),
        Path(__file__).resolve(),
        HERE / "static_name_check.py",
        HERE / "static_name_sources.py",
        HERE / "public_presence.py",
        ROOT / "research/050_CYCLE22_LOCAL_ERROR_AND_STATIC_CONTEXT_PROTOCOL.md",
        ROOT / "tests/test_static_name_check.py",
        ROOT / "tests/test_static_name_sources.py",
    ]
    texts = {
        p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8") for p in paths
    }
    protocol = {
        "cycle": "cycle22-local-name-error-static-context-component",
        "source_snapshot": digest(texts),
        "preflight_report": PREFLIGHT,
        "tool_profile": digest(profile),
        "presence_audit": digest(source_audit),
        "case_ids": [digest(case) for case in cases],
        "checker_options": CHECK["OPTIONS"],
        "expected_cases": 14,
        "expected_configurations": 28,
        "model_calls": 0,
        "native_executions": 0,
        "api_usd": 0,
    }
    store.bind_provenance({"protocol_digest": digest(protocol)})
    store.write("protocol", "preregistration", protocol)
    store.write("source_snapshots", digest(texts), texts)
    store.write("tool_profiles", digest(profile), profile)
    store.write("source_audits", digest(source_audit), source_audit)
    for case in cases:
        store.write("cases", digest(case), case)
        store.write("public_inputs", case["public_input_digest"], case["public_input"])
    for i, case in enumerate(cases):
        for context in (False, True):
            key = f"case-{i:02d}-{'context' if context else 'plain'}"
            analysis = CHECK["analysis_input"](case["public_input"], context=context)
            store.write(
                "checker_inputs",
                key,
                {"case_id": digest(case), "context": context, "analysis": analysis},
            )
    return protocol, cases, profile


def run(store: RunStore, *, audit_only: bool = False) -> dict:
    protocol, cases, profile = prepare(store)
    rows = []
    for i, case in enumerate(cases):
        for context in (False, True):
            key = f"case-{i:02d}-{'context' if context else 'plain'}"
            analysis = CHECK["analysis_input"](case["public_input"], context=context)
            process = store.read("checker_processes", key)
            if process is None:
                if audit_only:
                    raise IntegrityError("missing raw checker process")
                if store.read("checker_attempts", key) is not None:
                    raise IntegrityError(
                        "unresolved earlier checker attempt; no silent restart"
                    )
                store.write(
                    "checker_attempts",
                    key,
                    {
                        "argv": [profile["executable"], *protocol["checker_options"]],
                        "stdin_digest": digest(analysis["source"]),
                    },
                )
                try:
                    process = CHECK["invocation"](
                        profile["executable"],
                        protocol["checker_options"],
                        analysis["source"],
                    )
                except Exception as exc:
                    store.write(
                        "checker_failures",
                        key,
                        {
                            "error_type": type(exc).__name__,
                            "silent_restart_permitted": False,
                        },
                    )
                    raise
                store.write("checker_processes", key, process)
            if (
                process["argv"] != [profile["executable"], *protocol["checker_options"]]
                or process["cwd"] != str(ROOT)
                or process["stdin"] != analysis["source"]
                or process["stdin_digest"] != digest(analysis["source"])
            ):
                raise IntegrityError("checker tool/options/input changed")
            row = {
                "key": key,
                "case_index": i,
                "case_id": digest(case),
                "context": context,
                "analysis": analysis,
                "process_digest": digest(process),
                "parsed": CHECK["parse_findings"](process, analysis),
            }
            if audit_only and store.read("checker_results", key) != row:
                raise IntegrityError(
                    "checker finding/source positions did not regenerate"
                )
            store.write("checker_results", key, row)
            rows.append(row)
    report = {
        "protocol_digest": digest(protocol),
        "rows": rows,
        **summarize(cases, rows),
        "limitation": "Known-build local reported-NameError diagnostic of standard F821, not learned memory, a sound definite-assignment/semantic verifier, or held-out method superiority.",
    }
    if audit_only and store.read("reports", digest(report)) != report:
        raise IntegrityError("component metrics did not regenerate")
    store.write("reports", digest(report), report)
    expected = {
        "cases": {digest(c) for c in cases},
        "public_inputs": {c["public_input_digest"] for c in cases},
        "checker_inputs": {r["key"] for r in rows},
        "checker_attempts": {r["key"] for r in rows},
        "checker_processes": {r["key"] for r in rows},
        "checker_results": {r["key"] for r in rows},
        "reports": {digest(report)},
    }
    for kind, keys in expected.items():
        if {p.stem for p in (store.root / kind).glob("*.json")} != keys:
            raise IntegrityError("missing or extra checker record: " + kind)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store",
        type=Path,
        default=Path("artifacts/research/cycle22_static_name_check"),
    )
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    report = run(RunStore(args.store), audit_only=args.audit_only)
    print(
        json.dumps(
            {
                "report_digest": digest(report),
                **{k: v for k, v in report.items() if k != "rows"},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
