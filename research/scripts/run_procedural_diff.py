"""Preregistered local block proposal/effect/deletion search, no model calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest
from copromem.procedural_diff import propose_transplants, reduce_transplants
from copromem.stateful_adapter import audit_prefix_runs
from copromem.stateful_effect import error_indices, origin_checkpoint, run_effect_cell


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("research/configs/cycle13_procedural_diff.json"),
    )
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    settings = json.loads(args.config.read_text(encoding="utf-8"))
    if (
        settings["model_calls"] != 0
        or type(settings["max_variants_per_pair"]) is not int
        or not 1 <= settings["max_variants_per_pair"] <= 12
    ):
        raise ValueError(
            "cycle requires zero model calls and at most 12 variants per pair"
        )
    source = RunStore(root / settings["source_store"])
    store = RunStore(root / settings["output_directory"])
    source_protocol = source.read("protocol", "preregistration")
    source_report = source.read("reports", settings["source_report_id"])
    if (
        digest(source_protocol) != settings["source_protocol_digest"]
        or digest(source_report) != settings["source_report_id"]
        or source_report["protocol_digest"] != settings["source_protocol_digest"]
        or source_protocol["image_id"] != settings["image_id"]
    ):
        raise IntegrityError("frozen source protocol/report/image mismatch")
    proposals_by_pair, proposal_records = [], []
    for pair_index, endpoints in enumerate(source_protocol["pairs"]):
        for endpoint in endpoints:
            checkpoint = origin_checkpoint(endpoint)
            if (
                source.read("intervention_checkpoints", digest(checkpoint))
                != checkpoint
            ):
                raise IntegrityError("origin differs from the prior audited checkpoint")
        failed = [
            endpoint
            for endpoint in endpoints
            if not endpoint["episode"]["native_evaluation"]["native_success"]
        ]
        successful = [
            endpoint
            for endpoint in endpoints
            if endpoint["episode"]["native_evaluation"]["native_success"]
        ]
        if len(failed) != 1 or len(successful) != 1:
            raise IntegrityError(
                "registered source pair lacks one clean success/failure"
            )
        proposals, rejected = propose_transplants(
            failed[0]["step"]["code"], successful[0]["step"]["code"]
        )
        proposals_by_pair.append(proposals)
        proposal_records.append(
            {
                "pair_index": pair_index,
                "proposals": [proposal.record() for proposal in proposals],
                "rejected_proposals": rejected,
            }
        )
    texts = {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in [
            *sorted((root / "src/copromem").glob("*.py")),
            root / "research/containers/appworld/worker.py",
            Path(__file__).resolve(),
            root / settings["preregistration"],
        ]
    }
    protocol = {
        "settings": settings,
        "source_protocol": source_protocol,
        "source_report_id": settings["source_report_id"],
        "proposal_records": proposal_records,
    }
    store.bind_provenance(
        {
            "protocol_digest": digest(protocol),
            "source_hashes": {name: digest(text) for name, text in texts.items()},
        }
    )
    store.write("protocol", "preregistration", protocol)
    store.write("source_snapshots", digest(texts), texts)
    for row in proposal_records:
        store.write("proposal_batches", f"pair-{row['pair_index']}", row)
    if args.prepare_only:
        print(
            json.dumps(
                {
                    "protocol_digest": digest(protocol),
                    "initial_proposals": sum(len(row) for row in proposals_by_pair),
                    "model_calls": 0,
                    "native_edited_program_executions": 0,
                }
            ),
            flush=True,
        )
        return
    # Revalidate all saved whole-program controls without changing their results.
    for cell in source_report["cells"]:
        live_id, replay_id = cell["cell_id"] + "-live", cell["cell_id"] + "-replay"
        audit = audit_prefix_runs(
            source,
            [[live_id, replay_id]],
            expected_error_indices=error_indices(
                source.read("worker_results", live_id)
            ),
        )
        if (
            digest(audit) != cell["replay_audit_id"]
            or audit["pairs"][0]["native_evaluation"] != cell["native_evaluation"]
        ):
            raise IntegrityError("source control audit changed")
    all_searches = []
    for pair_index, (endpoints, proposals) in enumerate(
        zip(source_protocol["pairs"], proposals_by_pair)
    ):

        def evaluate(edit, pair_index=pair_index, endpoints=endpoints):
            record = edit.record()
            key = record["program_ast_digest"]
            store.write("variant_proposals", f"p{pair_index}-{key}", record)
            cells = []
            for origin_index, origin in enumerate(endpoints):
                cell_id = f"c13-p{pair_index}-v{key[:16]}-o{origin_index}"
                cell = run_effect_cell(
                    image=settings["image_id"],
                    bundle=root / settings["public_bundle"],
                    native_data=root / settings["native_data"],
                    store=store,
                    cell_id=cell_id,
                    origin=origin,
                    program=record["program"],
                )
                cells.append(cell)
                print(
                    json.dumps(
                        {
                            "cell_id": cell_id,
                            "retained_donor_indices": record["retained_donor_indices"],
                            "native_success": cell["native_evaluation"][
                                "native_success"
                            ],
                            "effect_gate_passed": cell["effect_gate_passed"],
                            "new_action_error": cell["new_uncaught_action_error"],
                            "api_log_delta": cell[
                                "native_api_log_entries_final_action_delta"
                            ],
                        }
                    ),
                    flush=True,
                )
            result = {
                "pair_index": pair_index,
                "program_ast_digest": key,
                "proposal_digest": digest(record),
                "cells": cells,
                "passed": all(cell["effect_gate_passed"] for cell in cells),
            }
            store.write("variant_results", f"p{pair_index}-{key}", result)
            return result["passed"]

        search = reduce_transplants(
            proposals, evaluate, max_variants=settings["max_variants_per_pair"]
        )
        store.write("search_results", f"pair-{pair_index}", search)
        all_searches.append(search)
    report = {
        "protocol_digest": digest(protocol),
        "pairs": all_searches,
        "passing_initial_transplants": sum(
            len(search["retained_edits"]) for search in all_searches
        ),
        "tested_variants": sum(
            search["tested_variant_count"] for search in all_searches
        ),
        "registered_search_complete": all(
            search["search_complete"] for search in all_searches
        ),
        "decision": "KEEP"
        if any(search["retained_edits"] for search in all_searches)
        else "REVISE",
        "model_calls": 0,
        "contract_admission": False,
        "interpretation": settings["interpretation"],
    }
    key = digest(report)
    store.write("reports", key, report)
    print(
        json.dumps(
            {
                key_: value
                for key_, value in {"report_id": key, **report}.items()
                if key_ != "pairs"
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
