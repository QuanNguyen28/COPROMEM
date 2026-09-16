"""Record installed Ruff/version/rule and two non-benchmark stdin fixtures."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest

HERE = Path(__file__).resolve().parent
CHECK = runpy.run_path(str(HERE / "static_name_check.py"))


def main():
    store = RunStore(HERE.parents[1] / "artifacts/research/cycle22_checker_preflight")
    profile = CHECK["tool_profile"]()
    CHECK["verify_tool"](profile)
    store.write("tool_profiles", digest(profile), profile)
    rows = []
    for name, source, offset, expected in (
        ("ascii", "apis = None\nprint(missing)\n", 1, ["missing"]),
        (
            "unicode_no_execution",
            "apis = None\nexisting = None\nprint(existing, 未知)\nraise RuntimeError('fixture_must_never_execute')\n",
            2,
            ["未知"],
        ),
    ):
        process = CHECK["invocation"](profile["executable"], CHECK["OPTIONS"], source)
        parsed = CHECK["parse_findings"](
            process, {"source": source, "line_offset": offset}
        )
        record = {
            "fixture": name,
            "process": process,
            "parsed": parsed,
            "expected_names": expected,
            "passed": parsed["valid"] and parsed["warning_names"] == expected,
        }
        store.write("fixtures", digest(record), record)
        rows.append(record)
    texts = {
        p.name: p.read_text(encoding="utf-8")
        for p in (Path(__file__).resolve(), HERE / "static_name_check.py")
    }
    report = {
        "tool_profile": digest(profile),
        "source_snapshot": digest(texts),
        "fixture_records": [digest(row) for row in rows],
        "all_passed": all(row["passed"] for row in rows),
        "recorded_metadata_calls": 2,
        "recorded_fixture_calls": 2,
        "benchmark_checker_cells": 0,
        "native_executions": 0,
        "model_calls": 0,
        "api_usd": 0,
    }
    store.write("source_snapshots", digest(texts), texts)
    store.write("reports", digest(report), report)
    print(
        json.dumps(
            {
                "report_digest": digest(report),
                "profile_digest": digest(profile),
                **report,
                "fixtures": [
                    {"name": row["fixture"], "parsed": row["parsed"]} for row in rows
                ],
            },
            indent=2,
        )
    )
    if not report["all_passed"]:
        raise IntegrityError("checker fixture gate failed; raw output retained")


if __name__ == "__main__":
    main()
