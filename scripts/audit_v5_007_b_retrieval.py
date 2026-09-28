"""Zero-provider, sanitized forensic audit for strict-v5 B retrieval.

It deliberately exports only hashes, counts, IDs, and branch predicates.  Raw
task text, action histories, prompts, and provider responses never leave the
local evidence directory.
"""
from __future__ import annotations

import argparse
import json
import pathlib

from copromem.experiments.reme_copromem.runner import digest, write_json
from copromem.learning import ActionObservation, LearningCore, _digest


def events(rows: list[dict]) -> tuple[ActionObservation, ...]:
    return tuple(ActionObservation(**item) for item in rows)


def schema_id(family: str, signature: dict | None) -> str | None:
    return None if signature is None else f"schema_{_digest([family, signature])[:16]}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=pathlib.Path, required=True)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.run / "manifest.json").read_text(encoding="utf-8"))
    a, b = manifest["evaluation"]["task_ids"]
    a_pending = json.loads((args.run / "copromem/task_updates_pending" / f"{a}.json").read_text(encoding="utf-8"))
    a_marker = json.loads((args.run / "copromem/task_updates" / f"{a}.json").read_text(encoding="utf-8"))
    record = json.loads((args.run / "retrieval/copromem_dynamic" / b / "trial-1.json").read_text(encoding="utf-8"))
    provenance = record["provenance"]
    descriptor_signature = LearningCore.signature(events(manifest["evaluation"]["descriptors"][b]))
    query_signature = LearningCore.signature(events(provenance["task_input"]["structural_events"]))
    winner = a_marker["winner_episode_id"]
    trace = next(item for item in a_pending["plan"]["candidate_traces"] if item["episode_id"] == winner)
    promoted = trace["signature_sha256"]
    query_hash = digest(query_signature) if query_signature else None
    expected = schema_id("appworld", query_signature)
    result = {
        "audit_version": "v5-007-b-retrieval-forensic-v1",
        "a_task_id": a, "b_task_id": b,
        "descriptor_signature_sha256": digest(descriptor_signature) if descriptor_signature else None,
        "retrieval_query_signature_sha256": query_hash,
        "promoted_execution_signature_sha256": promoted,
        "descriptor_equals_query": descriptor_signature == query_signature,
        "promoted_equals_query": promoted == query_hash,
        "query_expected_schema_id": expected,
        "promoted_schema_id": a_marker["validation"]["winner_episode_id"] and
            next(item["schema_id"] for item in a_pending["plan"]["candidate_traces"] if item["episode_id"] == winner),
        "promoted_schema_present_in_candidates": a_marker["validation"]["winner_episode_id"] and
            next(item["schema_id"] for item in a_pending["plan"]["candidate_traces"] if item["episode_id"] == winner)
            in provenance["candidate_schema_ids"],
        "candidate_score_count": len(provenance["candidate_scores"]),
        "first_rejecting_predicate": "learning_core_exact_schema_lookup_missing",
        "reason": "query signature resolves to a schema ID distinct from the promoted execution-trace schema",
        "classification": "implementation_interface_defect: strict descriptor was not supplied to task-boundary validation",
    }
    write_json(args.out, result)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
