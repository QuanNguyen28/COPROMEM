"""Retrospective syntax/name diagnostics; never a learned public verifier."""

from __future__ import annotations

import ast
import builtins
import json
import re
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest


def possible_missing_names(program: str, available: set[str]) -> list[str]:
    tree = ast.parse(program)
    reads = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    writes = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            writes.update(
                alias.asname or alias.name.split(".")[0] for alias in node.names
            )
        elif isinstance(node, ast.ExceptHandler) and node.name:
            writes.add(node.name)
    return sorted(reads - writes - available - set(dir(builtins)) - {"apis"})


def main():
    root = Path(__file__).resolve().parents[2]
    store = RunStore(root / "artifacts/research/cycle17_boundary_effects")
    source = RunStore(root / "artifacts/research/cycle17_all_boundary_screen")
    report_id = "34d849a67422629d7c6c6b35761794ed44c21765928d61fa1ff9856de415264c"
    report = store.read("reports", report_id)
    if (
        report is None
        or digest(report) != report_id
        or not report["complete_registered_sample"]
    ):
        raise IntegrityError("complete effect report required before diagnosis")
    rows = []
    for cell in report["rows"]:
        if cell["factual"]:
            continue
        candidate = source.read("candidates", cell["candidate_id"])
        if digest(candidate) != cell["candidate_id"]:
            raise IntegrityError("candidate provenance mismatch")
        namespace = candidate["origin"]["frame"]["harness_only_state"]["namespace"]
        available = set(namespace["serializable"]) | set(namespace["unsupported"])
        final = store.read("worker_results", cell["cell_id"] + "-live")
        output = final["results"][cell["action_index"]]["output"]
        rows.append(
            {
                "cell_id": cell["cell_id"],
                "task_id": cell["task_id"],
                "origin_episode": cell["origin_episode"],
                "action_index": cell["action_index"],
                "anchor": candidate["proposal"]["anchor"],
                "candidate_id": cell["candidate_id"],
                "target_output_digest": digest(output),
                "possible_missing_names": possible_missing_names(
                    candidate["proposal"]["program"], available
                ),
                "observed_name_errors": sorted(
                    set(
                        re.findall(
                            r"NameError: name ['\"]([A-Za-z_]\w*)['\"] is not defined",
                            output,
                        )
                    )
                ),
                "target_uncaught_error": output.startswith("Execution failed."),
                "effect_gate_passed": cell["effect_gate_passed"],
                "native_api_log_delta": None
                if cell["native_api_log_entries_total"] is None
                or cell["source_native_api_log_entries_total"] is None
                else cell["native_api_log_entries_total"]
                - cell["source_native_api_log_entries_total"],
            }
        )
    record = {
        "diagnostic": "retrospective-all-distinct-boundary-name-availability-v1",
        "source_report_digest": report_id,
        "script_digest": digest(Path(__file__).read_text(encoding="utf-8")),
        "rows": rows,
        "possible_missing_name_candidates": sum(
            bool(row["possible_missing_names"]) for row in rows
        ),
        "observed_name_error_candidates": sum(
            bool(row["observed_name_errors"]) for row in rows
        ),
        "model_calls": 0,
        "native_executions": 0,
        "limitation": "Retrospective harness-name-assisted diagnostic, not public agent evidence or a sound Python definite-assignment analysis. No candidate selection/outcome changes; future binding synthesis must use shared public code/artifacts, not hidden harness values.",
    }
    store.write("binding_diagnostics", digest(record), record)
    print(json.dumps({"diagnostic_id": digest(record), **record}, indent=2))


if __name__ == "__main__":
    main()
