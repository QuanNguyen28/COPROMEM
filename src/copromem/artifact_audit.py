"""Offline integrity and accounting checks over saved research artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .checkpoints import IntegrityError, PlannerCheckpoint, RunStore, digest
from .induction import HandoffEvidence, mine_candidates


def audit_store(root: Path) -> dict:
    store = RunStore(root)
    calls = {}
    for path in sorted((root / "calls").glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if (
            digest(value["request"]) != path.stem
            or digest(value["response"]) != value["response_sha256"]
        ):
            raise IntegrityError("provider record digest mismatch")
        calls[path.stem] = value
    checkpoints = {}
    for path in sorted((root / "checkpoints").glob("*.json")):
        checkpoint = PlannerCheckpoint.load(store, path.stem)
        if checkpoint.generation_id not in calls:
            raise IntegrityError("checkpoint generation is missing")
        if (
            checkpoint.question
            not in calls[checkpoint.generation_id]["request"]["user"]
        ):
            raise IntegrityError("checkpoint question/generation mismatch")
        checkpoints[path.stem] = checkpoint
    evidence = []
    for path in sorted((root / "source_evidence").glob("*.json")):
        item = HandoffEvidence(**json.loads(path.read_text(encoding="utf-8")))
        if item.evidence_id != path.stem:
            raise IntegrityError("source evidence digest mismatch")
        checkpoint = checkpoints.get(item.checkpoint_id)
        if (
            checkpoint is None
            or checkpoint.artifact_json != item.artifact_json
            or checkpoint.task_id != item.task_id
        ):
            raise IntegrityError("source evidence/checkpoint mismatch")
        evidence.append(item)
    for path in sorted((root / "reports").glob("*.json")):
        if digest(json.loads(path.read_text(encoding="utf-8"))) != path.stem:
            raise IntegrityError("report digest mismatch")
    reservations = {
        path.stem: json.loads(path.read_text())["reserved_usd"]
        for path in (root / "reservations").glob("*.json")
    }
    settlements = {
        path.stem: json.loads(path.read_text())["actual_usd"]
        for path in (root / "settlements").glob("*.json")
    }
    if not settlements.keys() <= reservations.keys():
        raise IntegrityError("settlement without reservation")
    actual = sum(x["response"]["usage"]["usd"] for x in calls.values())
    settled = sum(settlements.values())
    if reservations and abs(actual - settled) > 1e-8:
        raise IntegrityError(
            "successful generation usage does not reconcile with settlements"
        )
    for value in calls.values():
        key = value["response"]["metadata"].get("budget_reservation")
        if reservations and key not in settlements:
            raise IntegrityError("successful call has no settled budget reservation")
    charged = sum(settlements.get(key, value) for key, value in reservations.items())
    result = {
        "store": str(root),
        "status": "passed",
        "completed_generations": len(calls),
        "checkpoints": len(checkpoints),
        "source_evidence": len(evidence),
        "successful_generation_usd": actual,
        "http_attempts": sum(value["http_attempts"] for value in calls.values()),
        "reservation_count": len(reservations),
        "unsettled_attempts": len(reservations.keys() - settlements.keys()),
        "charged_or_reserved_usd": charged,
        "limitations": "Content integrity and accounting only; hashes are not authentication against an actor who can rewrite all evidence.",
    }
    if evidence:
        proposed = mine_candidates(evidence)
        result["offline_current_miner_version"] = proposed["algorithm"]
        result["offline_current_miner_candidate_count"] = len(proposed["candidates"])
        result["reanalysis_note"] = (
            "New all-success-counterexample veto; original proposals and scores unchanged. No new model calls."
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, action="append", required=True)
    parser.add_argument("--output-store", type=Path, required=True)
    args = parser.parse_args()
    report = {
        "audit": "research-integrity-v1",
        "stores": [audit_store(path) for path in args.store],
    }
    RunStore(args.output_store).write("integrity", digest(report), report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
