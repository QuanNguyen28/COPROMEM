"""Cycle-20 policy preflight: no native task or submitted probe is executed."""

from __future__ import annotations

import argparse
import ast
import json
import runpy
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORKER_PATH = ROOT / "research/containers/appworld/worker.py"
WORKER = runpy.run_path(str(WORKER_PATH))
CAPABILITIES = {
    "namespace_enumeration": "globals()",
    "exact_builtin_type": "type([]) is list",
    "ordinary_public_reference_control": "print(example_binding)",
}


def check_capabilities() -> dict:
    rows = []
    for name, program in CAPABILITIES.items():
        try:
            WORKER["validate_program"](program)
            accepted, error = True, None
        except ValueError as exc:
            accepted, error = False, str(exc)
        rows.append(
            {
                "capability": name,
                "program": program,
                "accepted_by_frozen_policy": accepted,
                "error": error,
                "forbidden_identifiers": sorted(
                    {
                        node.id
                        for node in ast.walk(ast.parse(program))
                        if isinstance(node, ast.Name)
                        and node.id in WORKER["FORBIDDEN_NAMES"]
                    }
                ),
            }
        )
    return {
        "rows": rows,
        "required_capabilities_accepted": all(
            row["accepted_by_frozen_policy"] for row in rows[:2]
        ),
    }


def run(store: RunStore) -> dict:
    # Verify the policy is still the exact worker text used by completed cycle 18.
    old = RunStore(ROOT / "artifacts/research/cycle18_bound_effects")
    protocol = old.read("protocol", "preregistration")
    snapshot = old.read("source_snapshots", protocol["source_snapshot"])
    text = WORKER_PATH.read_text(encoding="utf-8")
    if (
        digest(snapshot) != protocol["source_snapshot"]
        or snapshot["research/containers/appworld/worker.py"] != text
    ):
        raise IntegrityError("frozen native worker policy changed")
    sources = {
        str(path.relative_to(ROOT).as_posix()): path.read_text(encoding="utf-8")
        for path in (
            Path(__file__).resolve(),
            WORKER_PATH,
            ROOT / "research/047_CYCLE20_PUBLIC_BOUNDARY_OBSERVATION_GATE.md",
            ROOT / "tests/test_public_observation_preflight.py",
        )
    }
    result = {
        "cycle": "cycle20-public-observation-policy-preflight",
        "source_snapshot": digest(sources),
        "native_image": protocol["image_id"],
        **check_capabilities(),
        "planned_checkpoints": 3,
        "planned_native_cells": 6,
        "planned_native_executions": 12,
        "actual_native_executions": 0,
        "actual_native_scorers": 0,
        "executed_full_probes": 0,
        "complete_registered_native_sample": False,
        "model_calls": 0,
        "api_usd": 0,
        "admitted_contracts": 0,
        "decision": "REVISE",
        "reason": "Registered full envelope construction blocked at unchanged public-language capability preflight; no guard bypass or hidden-state substitution.",
        "limitation": "Rejects the proposed introspection-based implementation before execution; not a theorem that every equivalent observation interface is impossible, nor a completed six-cell native experiment.",
    }
    store.bind_provenance({"source_snapshot": digest(sources)})
    store.write("source_snapshots", digest(sources), sources)
    store.write("reports", digest(result), result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store",
        type=Path,
        default=Path("artifacts/research/cycle20_observation_preflight"),
    )
    args = parser.parse_args()
    result = run(RunStore(args.store))
    print(json.dumps({"report_digest": digest(result), **result}, indent=2))


if __name__ == "__main__":
    main()
