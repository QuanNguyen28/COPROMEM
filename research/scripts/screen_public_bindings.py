"""Cycle-18A complete public-code binding registry, with no native/model execution."""

from __future__ import annotations

import argparse
import json
import runpy
from collections import Counter
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest
from copromem.procedural_diff import BlockTransplant

BIND_PATH = Path(__file__).with_name("public_binding.py")
BIND_MODULE = runpy.run_path(str(BIND_PATH))
SOURCE_REPORT = "47ba12900b34835c813f99dd689b7d01b75c81be5e7ec559dfae3ea1b7778268"


def public_inputs(candidate: dict, action_pair: dict) -> dict:
    target, donor = action_pair["target"], action_pair["donor"]
    proposal = candidate["proposal"]
    prefix = candidate["origin"]["prefix_request"]
    if (
        digest(action_pair) != candidate["action_pair_id"]
        or target["task_id"] != candidate["task_id"]
        or donor["task_id"] != candidate["task_id"]
        or candidate["target_action_index"] != target["action_index"]
        or candidate["donor_action_index"] != donor["action_index"]
        or candidate["origin"]["step"]["code"] != target["code"]
        or len(prefix["actions"]) != candidate["target_action_index"]
        or prefix["task_id"] != candidate["task_id"]
    ):
        raise IntegrityError("public source action/prefix/candidate binding mismatch")
    edit = BlockTransplant(
        target["code"],
        donor["code"],
        proposal["anchor"],
        tuple(proposal["origin_span"]),
        tuple(proposal["donor_span"]),
        tuple(proposal["retained_donor_indices"]),
    )
    if edit.record() != proposal:
        raise IntegrityError("original proposal does not regenerate from source code")
    return {
        "target_program": target["code"],
        "donor_program": donor["code"],
        "anchor": proposal["anchor"],
        "origin_span": proposal["origin_span"],
        "donor_span": proposal["donor_span"],
        "retained_donor_indices": proposal["retained_donor_indices"],
        "public_prefix": prefix["actions"],
    }


def construct(public: dict) -> dict:
    allowed = {
        "target_program",
        "donor_program",
        "anchor",
        "origin_span",
        "donor_span",
        "retained_donor_indices",
        "public_prefix",
    }
    if set(public) != allowed:
        raise IntegrityError(
            "constructor input has missing or non-public-schema fields"
        )
    edit = BlockTransplant(
        public["target_program"],
        public["donor_program"],
        public["anchor"],
        tuple(public["origin_span"]),
        tuple(public["donor_span"]),
        tuple(public["retained_donor_indices"]),
    )
    return BIND_MODULE["bind_transplant"](edit, public["public_prefix"])


def screen(store: RunStore, *, audit_only: bool = False) -> dict:
    root = Path(__file__).resolve().parents[2]
    source = RunStore(root / "artifacts/research/cycle17_all_boundary_screen")
    coverage = runpy.run_path(
        str(Path(__file__).with_name("screen_all_boundaries.py"))
    )["screen"](source, audit_only=True)
    if digest(coverage) != SOURCE_REPORT:
        raise IntegrityError("registered complete source coverage changed")
    candidates = {
        path.stem: source.read("candidates", path.stem)
        for path in sorted((source.root / "candidates").glob("*.json"))
    }
    if len(candidates) != 34 or any(
        digest(row) != key for key, row in candidates.items()
    ):
        raise IntegrityError("original 34-candidate provenance registry changed")
    paths = [
        *sorted((root / "src/copromem").glob("*.py")),
        Path(__file__).resolve(),
        BIND_PATH,
        root / "research/042_CYCLE18_PUBLIC_BINDING_PREREGISTRATION.md",
        root / "tests/test_public_binding.py",
        root / "tests/test_public_binding_inputs.py",
    ]
    texts = {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in paths
    }
    protocol = {
        "cycle_id": "cycle18a-public-api-argument-binding-output-closure",
        "source_report": SOURCE_REPORT,
        "source_protocol": coverage["protocol_digest"],
        "source_candidate_ids": sorted(candidates),
        "source_snapshot": digest(texts),
        "operator": BIND_MODULE["VERSION"],
        "known_repair_tasks": ["aa8502b_1"],
        "model_calls": 0,
        "native_executions": 0,
        "effect_outcomes_or_hidden_state_passed_to_constructor": False,
    }
    if audit_only:
        if (
            store.read("protocol", "preregistration") != protocol
            or store.read("source_snapshots", digest(texts)) != texts
        ):
            raise IntegrityError(
                "frozen public binding implementation/protocol changed"
            )
    else:
        store.bind_provenance(
            {"protocol_digest": digest(protocol), "source_snapshot": digest(texts)}
        )
        store.write("protocol", "preregistration", protocol)
        store.write("source_snapshots", digest(texts), texts)
    rows, input_ids = [], set()
    for key, candidate in candidates.items():
        pair = source.read("action_pairs", candidate["action_pair_id"])
        public = public_inputs(candidate, pair)
        public_id = digest(public)
        input_ids.add(public_id)
        constructed = construct(public)
        row = {
            "protocol_digest": digest(protocol),
            "source_candidate_id": key,
            "task_id": candidate["task_id"],
            "origin_episode": candidate["origin_source"]["source_id"],
            "target_action_index": candidate["target_action_index"],
            "public_input_digest": public_id,
            "construction": constructed,
        }
        if audit_only:
            if (
                store.read("public_inputs", public_id) != public
                or store.read("bound_candidates", key) != row
            ):
                raise IntegrityError(
                    "candidate binding/input/rejection does not regenerate"
                )
        else:
            store.write("public_inputs", public_id, public)
            store.write("bound_candidates", key, row)
        rows.append(row)
    changed = [
        row for row in rows if row["construction"]["status"] == "accepted_changed"
    ]
    new_tasks = sorted(
        {
            row["task_id"]
            for row in changed
            if row["task_id"] not in protocol["known_repair_tasks"]
        }
    )
    unique = {
        (
            row["origin_episode"],
            row["target_action_index"],
            row["construction"]["program_ast_digest"],
        )
        for row in changed
    }
    tasks = []
    for task in coverage["tasks"]:
        task_rows = [row for row in rows if row["task_id"] == task["task_id"]]
        tasks.append(
            {
                "task_id": task["task_id"],
                "original_candidates": len(task_rows),
                "statuses": dict(
                    sorted(
                        Counter(
                            row["construction"]["status"] for row in task_rows
                        ).items()
                    )
                ),
            }
        )
    record = {
        "protocol_digest": digest(protocol),
        "rows": rows,
        "tasks": tasks,
        "complete_registered_sample": len(rows) == 34,
        "original_candidate_records": len(rows),
        "construction_statuses": dict(
            sorted(Counter(row["construction"]["status"] for row in rows).items())
        ),
        "rejection_reasons": dict(
            sorted(
                Counter(
                    item["reason"]
                    for row in rows
                    for item in row["construction"]["rejections"]
                ).items()
            )
        ),
        "accepted_changed_records": len(changed),
        "unique_changed_boundary_programs": len(unique),
        "new_tasks_with_bound_candidate": new_tasks,
        "primary_metric": len(new_tasks),
        "decision": "KEEP" if new_tasks else "REVISE",
        "model_calls": 0,
        "native_executions": 0,
        "admitted_contracts": 0,
        "limitation": "Public-code construction closure under a bounded syntax check only; task effect, source-call success, semantic equivalence, learned scope, same-rule independent support and held-out advantage remain unproved.",
    }
    if audit_only:
        if store.read("reports", digest(record)) != record:
            raise IntegrityError("public binding coverage report does not regenerate")
        for kind, expected in (
            ("bound_candidates", set(candidates)),
            ("public_inputs", input_ids),
            ("reports", {digest(record)}),
        ):
            if {path.stem for path in (store.root / kind).glob("*.json")} != expected:
                raise IntegrityError("missing or extra binding record in " + kind)
    else:
        store.write("reports", digest(record), record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store", type=Path, default=Path("artifacts/research/cycle18_public_binding")
    )
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    record = screen(RunStore(args.store), audit_only=args.audit_only)
    print(
        json.dumps(
            {
                "report_id": digest(record),
                "regenerated_audit": args.audit_only,
                **{key: value for key, value in record.items() if key != "rows"},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
