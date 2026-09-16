"""All cycle-18 bound candidates through the unchanged saved-continuation engine."""

from __future__ import annotations

import argparse
import copy
import json
import runpy
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest

ENGINE_PATH = Path(__file__).with_name("run_boundary_effects.py")
ENGINE = runpy.run_path(str(ENGINE_PATH))
BINDING_REPORT = "961c2829fc45d5d1c02e989dd454cbf248e65e1363d3480d3409b2ae87b8e9fe"


def effect_candidate(bound: dict, original: dict) -> dict:
    result = bound["construction"]
    if (
        digest(original) != bound["source_candidate_id"]
        or result["status"] != "accepted_changed"
        or not result["changed_from_original_proposal"]
        or result["missing_inputs"]
        or result["missing_outputs"]
        or result["rejections"]
    ):
        raise IntegrityError("effect requires an intact accepted changed construction")
    if (
        bound["task_id"] != original["task_id"]
        or bound["target_action_index"] != original["target_action_index"]
        or bound["origin_episode"] != original["origin_source"]["source_id"]
    ):
        raise IntegrityError("bound proposal is attached to a different target")
    return {
        "kind": "public-code-bound-local-program-proposal-not-admitted-contract",
        "source_candidate_id": bound["source_candidate_id"],
        "bound_candidate_digest": digest(bound),
        "public_input_digest": bound["public_input_digest"],
        "task_id": bound["task_id"],
        "target_action_index": bound["target_action_index"],
        "origin": copy.deepcopy(original["origin"]),
        "origin_source": copy.deepcopy(original["origin_source"]),
        "proposal": {
            "program": result["program"],
            "program_ast_digest": result["program_ast_digest"],
            "operator": result["operator"],
            "construction_digest": digest(result),
        },
    }


def prepare(store: RunStore) -> tuple[dict, dict[str, dict]]:
    root = Path(__file__).resolve().parents[2]
    binding = RunStore(root / "artifacts/research/cycle18_public_binding")
    source = RunStore(root / "artifacts/research/cycle17_all_boundary_screen")
    print(
        json.dumps({"phase": "regenerating_complete_public_binding_registry"}),
        flush=True,
    )
    report = runpy.run_path(str(Path(__file__).with_name("screen_public_bindings.py")))[
        "screen"
    ](binding, audit_only=True)
    if digest(report) != BINDING_REPORT:
        raise IntegrityError("registered public binding result changed")
    candidates = {}
    for row in report["rows"]:
        if row["construction"]["status"] != "accepted_changed":
            continue
        candidate = effect_candidate(
            row, source.read("candidates", row["source_candidate_id"])
        )
        candidates[digest(candidate)] = candidate
    selected, controls = ENGINE["manifest"](candidates)
    if len(candidates) != 5 or len(selected) != 5 or len(controls) != 3:
        raise IntegrityError(
            "registered five effects and three controls did not regenerate"
        )
    paths = [
        *sorted((root / "src/copromem").glob("*.py")),
        Path(__file__).resolve(),
        ENGINE_PATH,
        Path(__file__).with_name("public_binding.py"),
        Path(__file__).with_name("screen_public_bindings.py"),
        root / "research/043_CYCLE18A_RESULT_AND_BOUND_EFFECT_PREREGISTRATION.md",
        *sorted((root / "research/containers/appworld").glob("*.py")),
    ]
    texts = {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in paths
    }
    protocol = {
        "cycle_id": "cycle18b-public-bound-input-saved-continuation-effects",
        "binding_report": BINDING_REPORT,
        "binding_protocol": report["protocol_digest"],
        "source_snapshot": digest(texts),
        "image_id": ENGINE["IMAGE"],
        "selected": selected,
        "factual_controls": controls,
        "expected_cells": 8,
        "expected_native_executions": 16,
        "expected_native_evaluations": 16,
        "effect_candidate_ids": sorted(candidates),
        "public_bundle": "artifacts/research/cycle15_reflection_source/public_bundle",
        "public_bundle_manifest": "e5f5a2dae7640d2a364ec82861ad58ac86f3d0d62adf9d18d3250be14c234255",
        "native_data": "artifacts/research/appworld_preflight_20260916/data",
        "known_repair_tasks": ["aa8502b_1"],
        "model_calls": 0,
        "api_usd": 0,
        "continuation": "unchanged saved future action strings using unmodified cycle-17 cell engine",
    }
    if (
        digest(
            RunStore(root / protocol["public_bundle"]).read("manifest", "public_bundle")
        )
        != protocol["public_bundle_manifest"]
    ):
        raise IntegrityError("canonical bundle manifest changed")
    store.bind_provenance(
        {"protocol_digest": digest(protocol), "source_snapshot": digest(texts)}
    )
    store.write("protocol", "preregistration", protocol)
    store.write("source_snapshots", digest(texts), texts)
    for key, candidate in candidates.items():
        store.write("effect_candidates", key, candidate)
    return protocol, candidates


def run(store: RunStore) -> dict:
    protocol, candidates = prepare(store)
    print(
        json.dumps(
            {
                "protocol_digest": digest(protocol),
                "effects": 5,
                "factual_controls": 3,
                "native_executions": 16,
                "model_calls": 0,
            }
        ),
        flush=True,
    )
    rows = []
    for factual, registry in (
        (True, protocol["factual_controls"]),
        (False, protocol["selected"]),
    ):
        for index, selected in enumerate(registry):
            key = f"c18b-{'control' if factual else 'edit'}-{index:02d}"
            row = ENGINE["run_cell"](
                store,
                protocol,
                candidates[selected["representative"]],
                key,
                factual=factual,
            )
            rows.append(row)
            print(
                json.dumps(
                    {
                        "cell_id": key,
                        "origin_episode": row["origin_episode"],
                        "action_index": row["action_index"],
                        "native_success": row["native_evaluation"]["native_success"],
                        "eligible": row["eligible"],
                        "introduced_errors": row["introduced_error_indices"],
                        "effect_gate_passed": row["effect_gate_passed"],
                    }
                ),
                flush=True,
            )
    new_tasks = sorted(
        {
            row["task_id"]
            for row in rows
            if row["effect_gate_passed"]
            and row["task_id"] not in protocol["known_repair_tasks"]
        }
    )
    record = {
        "protocol_digest": digest(protocol),
        "rows": rows,
        "complete_registered_sample": len(rows) == 8,
        "factual_controls": 3,
        "distinct_interventions": 5,
        "eligible_interventions": sum(
            row["eligible"] for row in rows if not row["factual"]
        ),
        "passing_interventions": sum(row["effect_gate_passed"] for row in rows),
        "new_tasks_with_validated_local_repair": new_tasks,
        "primary_metric": len(new_tasks),
        "native_executions": len(list((store.root / "worker_results").glob("*.json"))),
        "native_evaluations": len(
            list((store.root / "native_evaluation").glob("*.json"))
        ),
        "model_calls": 0,
        "api_usd": 0,
        "decision": "KEEP" if new_tasks and len(rows) == 8 else "REVISE",
        "limitation": "Build-only local bound-program effects; no successful-origin safety guard, learned verifier/scope, same-rule independent support, contract admission or held-out method advantage.",
    }
    if record["native_executions"] != 16 or record["native_evaluations"] != 16:
        raise IntegrityError("registered native worker/scorer accounting mismatch")
    store.write("reports", digest(record), record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store", type=Path, default=Path("artifacts/research/cycle18_bound_effects")
    )
    args = parser.parse_args()
    record = run(RunStore(args.store))
    print(
        json.dumps(
            {
                "report_id": digest(record),
                **{key: value for key, value in record.items() if key != "rows"},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
