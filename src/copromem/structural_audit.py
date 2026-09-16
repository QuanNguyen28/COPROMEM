"""Offline observability audit of the bounded structural contract representation.

This consumes build evidence only and never proposes or admits a contract. A
signature collision is a representation limitation, not a statistical estimate
of accuracy and not proof that all procedural contracts are ineffective.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from .checkpoints import RunStore, digest
from .induction import HandoffEvidence, _candidate_predicates


def audit_observability(evidence: list[HandoffEvidence]) -> dict:
    if any(item.partition != "build" for item in evidence):
        raise ValueError("observability audit is restricted to build evidence")
    groups = defaultdict(list)
    for item in {x.evidence_id: x for x in evidence}.values():
        groups[
            (
                item.task_id,
                item.interface,
                item.public_context_json,
                item.execution_context,
            )
        ].append(item)
    pairs = []
    for items in groups.values():
        positives = [x for x in items if x.success]
        negatives = [x for x in items if not x.success]
        # Exactly the vocabulary available to the current positive-derived miner.
        vocabulary = sorted(
            set().union(
                *[_candidate_predicates(json.loads(x.artifact_json)) for x in positives]
            )
        )
        for positive in positives:
            for negative in negatives:
                p, n = (
                    json.loads(positive.artifact_json),
                    json.loads(negative.artifact_json),
                )
                differences = [
                    clause
                    for clause in vocabulary
                    if clause.holds(p) != clause.holds(n)
                ]
                usable = [clause for clause in differences if clause.holds(p)]
                pairs.append(
                    {
                        "task_id": positive.task_id,
                        "positive_checkpoint": positive.checkpoint_id,
                        "negative_checkpoint": negative.checkpoint_id,
                        "positive_evidence": positive.evidence_id,
                        "negative_evidence": negative.evidence_id,
                        "vocabulary_size": len(vocabulary),
                        "identical_signature": not differences,
                        "identical_artifact": positive.artifact_json
                        == negative.artifact_json,
                        "positive_accept_negative_reject": [asdict(x) for x in usable],
                        "different_predicates": [asdict(x) for x in differences],
                    }
                )
    return {
        "audit": "positive-derived-structural-observability-v2",
        "matched_pairs": len(pairs),
        "matched_tasks": len({x["task_id"] for x in pairs}),
        "identical_signature_pairs": sum(x["identical_signature"] for x in pairs),
        "identical_artifact_pairs": sum(x["identical_artifact"] for x in pairs),
        "potentially_separable_pairs": sum(
            bool(x["positive_accept_negative_reject"]) for x in pairs
        ),
        "pairs": pairs,
        "interpretation": "Identical signatures cannot be separated by any Boolean combination of the available features. Distinct signatures do not prove a generalizable or causal invariant.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    args = parser.parse_args()
    evidence = [
        HandoffEvidence(**json.loads(path.read_text(encoding="utf-8")))
        for path in sorted((args.store / "source_evidence").glob("*.json"))
    ]
    if not evidence:
        raise ValueError("no source evidence found")
    report = audit_observability(evidence)
    RunStore(args.store).write("observability", digest(report), report)
    print(json.dumps({k: v for k, v in report.items() if k != "pairs"}, indent=2))


if __name__ == "__main__":
    main()
