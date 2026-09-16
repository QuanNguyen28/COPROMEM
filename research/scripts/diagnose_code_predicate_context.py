"""Post-hoc public-code/error context for every cycle-19 identical-AST conflict."""

from __future__ import annotations

import ast
import json
import re
import runpy
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LANG = runpy.run_path(str(HERE / "code_predicate_language.py"))
SOURCE = runpy.run_path(str(HERE / "code_predicate_sources.py"))
REPORT_ID = "e70d3ef6d1c0ba9abea12f43c90b4ef3dde8dc4bdb35d3f09df5962f4b053d6b"


def assignment_indices(prefix: list[str], name: str) -> list[int]:
    """Syntactic stores only; does not assert that an assignment really executed."""
    return [
        i
        for i, program in enumerate(prefix)
        if any(
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Store)
            and node.id == name
            for node in ast.walk(ast.parse(program))
        )
    ]


def main():
    store = RunStore(ROOT / "artifacts/research/cycle19_code_predicates")
    report = store.read("reports", REPORT_ID)
    if digest(report) != REPORT_ID:
        raise IntegrityError("predicate report changed")
    groups = []
    for group in report["conflicting_normalized_ast_groups"]:
        examples, missing = [], set()
        for index in group["indices"]:
            row = store.read("examples", f"diagnostic-{index:02d}")
            source = RunStore(
                ROOT
                / "artifacts/research"
                / SOURCE["SOURCES"][row["evidence"]["source"]][0]
            )
            key = row["evidence"]["cell_id"] + "-live"
            worker = source.read("worker_results", key)
            request = source.read("worker_requests", key)
            public = SOURCE["public_action"](
                request,
                worker,
                source.read("native_evaluation", key),
                row["action_index"],
                row["public"]["program"],
            )
            if public != row["public"]:
                raise IntegrityError("diagnostic public action changed")
            output = worker["results"][row["action_index"]]["output"]
            names = sorted(
                set(
                    re.findall(
                        r"NameError: name '([A-Za-z_]\w*)' is not defined", output
                    )
                )
            )
            missing.update(names)
            examples.append(
                (index, row, request["actions"][: row["action_index"]], names)
            )
        ast_ids = {
            digest(LANG["ast_identity"](row["public"]["program"]))
            for _, row, _, _ in examples
        }
        if len(ast_ids) != 1:
            raise IntegrityError("conflict no longer has identical normalized code")
        groups.append(
            {
                "conflict": group,
                "normalized_ast_digest": next(iter(ast_ids)),
                "names_from_public_error_strings": sorted(missing),
                "examples": [
                    {
                        "diagnostic_index": index,
                        "source_cell": row["evidence"]["cell_id"],
                        "origin_episode": row["origin_episode"],
                        "action_index": row["action_index"],
                        "native_success": row["public"]["label"],
                        "public_name_errors": names,
                        "earlier_syntactic_stores": {
                            name: assignment_indices(prefix, name)
                            for name in sorted(missing)
                        },
                        "public_prefix_digest": digest(prefix),
                    }
                    for index, row, prefix, names in examples
                ],
            }
        )
    record = {
        "diagnostic": "posthoc-public-prefix-stores-versus-observed-name-errors-v1",
        "source_report": REPORT_ID,
        "source_text_digest": digest(Path(__file__).read_text(encoding="utf-8")),
        "groups": groups,
        "hidden_state_read": False,
        "fed_back_into_frozen_miner": False,
        "model_calls": 0,
        "native_executions": 0,
        "api_usd": 0,
        "limitation": "Public error-string and source-code diagnosis only; syntactic stores need not have executed and error strings are not a sound classifier. Does not infer or validate scope.",
    }
    store.write("context_diagnostics", digest(record), record)
    print(json.dumps({"diagnostic_digest": digest(record), **record}, indent=2))


if __name__ == "__main__":
    main()
