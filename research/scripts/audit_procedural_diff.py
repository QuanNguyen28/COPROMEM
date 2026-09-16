"""Regenerate saved edit/search decisions and verify native evidence, no execution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest
from copromem.procedural_diff import (
    BlockTransplant,
    propose_transplants,
    reduce_transplants,
)
from copromem.stateful_adapter import audit_prefix_runs, verify_prefix_pair
from copromem.stateful_effect import effect_passes, error_indices, origin_checkpoint


def require(condition: bool, message: str) -> None:
    if not condition:
        raise IntegrityError(message)


def audit(store: RunStore, result_id: str) -> dict:
    protocol = store.read("protocol", "preregistration")
    result = store.read("reports", result_id)
    require(
        result is not None and digest(result) == result_id, "result absent or corrupted"
    )
    require(digest(protocol) == result["protocol_digest"], "protocol mismatch")
    records, cells_checked = {}, []
    for path in sorted((store.root / "variant_results").glob("*.json")):
        value = store.read("variant_results", path.stem)
        proposal = store.read("variant_proposals", path.stem)
        endpoints = protocol["source_protocol"]["pairs"][value["pair_index"]]
        failed = next(
            origin
            for origin in endpoints
            if not origin["episode"]["native_evaluation"]["native_success"]
        )
        successful = next(
            origin
            for origin in endpoints
            if origin["episode"]["native_evaluation"]["native_success"]
        )
        edit = BlockTransplant(
            failed["step"]["code"],
            successful["step"]["code"],
            proposal["anchor"],
            tuple(proposal["origin_span"]),
            tuple(proposal["donor_span"]),
            tuple(proposal["retained_donor_indices"]),
        )
        require(
            edit.record() == proposal and digest(proposal) == value["proposal_digest"],
            "edited program/proposal differs from source",
        )
        require(len(value["cells"]) == len(endpoints) == 2, "both origins required")
        for origin, cell in zip(endpoints, value["cells"]):
            cell_id = cell["cell_id"]
            live_id, replay_id = cell_id + "-live", cell_id + "-replay"
            observed = store.read("worker_results", live_id)
            before = store.read("stream_frames", live_id + "-000")
            verify_prefix_pair(
                origin["frame"],
                before,
                expected_error_indices=error_indices(origin["frame"]),
            )
            checkpoint = origin_checkpoint(origin)
            require(
                digest(checkpoint) == cell["checkpoint_id"],
                "origin checkpoint mismatch",
            )
            require(
                digest(edit.program()) == cell["program_digest"]
                and observed["results"][-1]["program"] == edit.program(),
                "native executed program mismatch",
            )
            paired = audit_prefix_runs(
                store,
                [[live_id, replay_id]],
                expected_error_indices=error_indices(observed),
            )
            require(digest(paired) == cell["replay_audit_id"], "replay audit changed")
            require(
                paired["pairs"][0]["native_evaluation"] == cell["native_evaluation"],
                "native evaluator record mismatch",
            )
            require(
                effect_passes(observed, cell["native_evaluation"])
                == cell["effect_gate_passed"],
                "effect gate mismatch",
            )
            require(
                cell["final_public_output"] == observed["results"][-1]["output"],
                "public output mismatch",
            )
            cells_checked.append(cell_id)
        require(
            value["passed"]
            == all(cell["effect_gate_passed"] for cell in value["cells"]),
            "variant admission differs from per-origin evidence",
        )
        records[(value["pair_index"], value["program_ast_digest"])] = value
    for pair_index, endpoints in enumerate(protocol["source_protocol"]["pairs"]):
        failed = next(
            origin
            for origin in endpoints
            if not origin["episode"]["native_evaluation"]["native_success"]
        )
        successful = next(
            origin
            for origin in endpoints
            if origin["episode"]["native_evaluation"]["native_success"]
        )
        proposals, rejected = propose_transplants(
            failed["step"]["code"], successful["step"]["code"]
        )
        require(
            protocol["proposal_records"][pair_index]
            == {
                "pair_index": pair_index,
                "proposals": [edit.record() for edit in proposals],
                "rejected_proposals": rejected,
            },
            "proposal search does not regenerate",
        )

        def lookup(edit, pair_index=pair_index):
            return records[(pair_index, edit.record()["program_ast_digest"])]["passed"]

        regenerated = reduce_transplants(
            proposals,
            lookup,
            max_variants=protocol["settings"]["max_variants_per_pair"],
        )
        require(
            regenerated == result["pairs"][pair_index],
            "deletion search does not regenerate",
        )
        require(
            set(regenerated["tested_programs"])
            == {key for index, key in records if index == pair_index},
            "unaccounted tested variants",
        )
    return {
        "source_report_id": result_id,
        "variant_count": len(records),
        "cells_verified": cells_checked,
        "native_execution_count": len(cells_checked) * 2,
        "proposal_and_deletion_search_regenerated": True,
        "original_environment_and_planner_verified": True,
        "independent_replay_and_scoring_records_verified": True,
        "model_calls_for_audit": 0,
        "limitation": "Archive integrity and exact local source-effect evidence only; not new independent tasks, minimal semantic edit or admitted contract.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store", type=Path, default=Path("artifacts/research/cycle13_procedural_diff")
    )
    parser.add_argument(
        "--report",
        default="3b804f5a064696081627852d0eb3046e761a7dae49ec410d8ecb92d1da2a166d",
    )
    args = parser.parse_args()
    store = RunStore(args.store)
    record = audit(store, args.report)
    key = digest(record)
    store.write("independent_audits", key, record)
    print(json.dumps({"audit_id": key, **record}, indent=2))


if __name__ == "__main__":
    main()
