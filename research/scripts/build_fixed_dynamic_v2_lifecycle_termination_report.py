#!/usr/bin/env python3
"""Create a sanitized, read-only terminal report for fixed_dynamic_v2.

This is deliberately a report-only tool.  It reads durable run evidence but
never opens an AppWorld payload, sends a request, or alters a journal/ledger.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from collections import Counter
from typing import Any


ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
RUN = ROOT / "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v2"
OUT = ROOT / "research/fixed_dynamic_v2_results/budget-160-lifecycle-termination"


def read_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    manifest_path = RUN / "manifest-budget-160.json"
    manifest_hash = (RUN / "manifest-budget-160.sha256").read_text(encoding="utf-8").strip()
    manifest = read_json(manifest_path)
    if digest(manifest_path) != manifest_hash:
        raise SystemExit("frozen budget-160 manifest hash mismatch")
    status = read_json(RUN / "runner-status.json")
    gate = read_json(RUN / "acquisition/combined-gate.json")
    expected_ids = list(manifest["acquisition"]["new_task_ids"])
    artifacts = []
    for task_id in expected_ids:
        matches = list((RUN / "acquisition").glob(f"{task_id}--*.json"))
        if len(matches) != 1:
            raise SystemExit(f"expected exactly one acquisition artifact for {task_id}")
        row = read_json(matches[0])
        artifacts.append({
            "task_id": task_id,
            "score": float(row["after_score"]),
            "actions": int(row["actions"]),
            "artifact_sha256": digest(matches[0]),
        })
    checkpoint = jsonl(RUN / "reme/construction.jsonl")
    states = Counter(str(row.get("state", "unknown")) for row in checkpoint)
    completed_reme_inputs = {str(row["trajectory_id"]) for row in checkpoint if row.get("state") == "persisted"}
    ledger = jsonl(RUN / "ledger.jsonl")
    current: dict[str, float] = {}
    for row in ledger:
        if row.get("event") in {"reserve", "settle"}:
            current[str(row["id"])] = float(row["usd"])
    settled_ids = {str(row["id"]) for row in ledger if row.get("event") == "settle"}
    reserve_ids = {str(row["id"]) for row in ledger if row.get("event") == "reserve"}
    unpaid_reservations = sorted(reserve_ids - settled_ids)
    evidence_paths = [
        ("budget_160_manifest", manifest_path),
        ("budget_160_preflight", RUN / "budget-preflight-budget-160.json"),
        ("budget_amendment", RUN / "budget-amendment-v1.json"),
        ("original_140_results", ROOT / "research/fixed_dynamic_v2_results/final-report.json"),
        ("combined_acquisition_gate", RUN / "acquisition/combined-gate.json"),
        ("lifecycle_checkpoint", RUN / "reme/construction.jsonl"),
        ("ledger", RUN / "ledger.jsonl"),
        ("progress", RUN / "progress.jsonl"),
    ]
    evidence = [{"kind": kind, "path": str(path.relative_to(ROOT)), "sha256": digest(path)} for kind, path in evidence_paths]
    evidence.extend({"kind": "new_acquisition_artifact", "path": f"artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v2/acquisition/{row['task_id']}", "sha256": row["artifact_sha256"]} for row in artifacts)
    report = {
        "protocol": manifest["protocol"],
        "label": "corrected successor; terminal lifecycle-integrity NO-GO",
        "manifest_sha256": manifest_hash,
        "budget_amendment": {"version": 1, "hard_cap_usd": 160.0, "prior_usd_140_record_preserved": True},
        "acquisition": {
            "combined_trajectory_count": int(gate["planned"]),
            "full_successes": int(gate["full_successes"]),
            "successful_families": int(gate["successful_families"]),
            "gate_passed": bool(gate["passed"]),
            "new_trajectories": artifacts,
        },
        "lifecycle": {
            "evaluation_dispatched": False,
            "reme_checkpoint_state_counts": dict(sorted(states.items())),
            "reme_persisted_input_count": len(completed_reme_inputs),
            "terminal_failure": "frozen input-token ceiling rejected an upstream ReMe failure-extraction prompt before dispatch; the service surfaced this pre-dispatch condition as HTTP 500",
            "paid_request_for_terminal_failure": False,
            "permitted_resolution_not_applied": ["raise the frozen input ceiling", "truncate or alter upstream lifecycle input"],
        },
        "ledger": {
            "hard_cap_usd": float(manifest["budget"]["hard_cap_usd"]),
            "charged_or_retained_exposure_usd": round(sum(current.values()), 12),
            "ledger_records": len(ledger),
            "unsettled_reservation_ids": unpaid_reservations,
        },
        "evaluation": {"expected_trajectories": 320, "completed_trajectories": 0, "metrics": None},
        "decision": "NO-GO",
        "decision_basis": "The acquisition gate passed, but the mandatory upstream-ReMe lifecycle and retrieval-integrity gate could not be completed under the frozen 32,768-token input ceiling. No evaluation task, scorer, or model call was dispatched.",
        "limitations": [
            "The USD 160 amendment made the registered conservative cost bound feasible; budget was not the terminal condition.",
            "This is a terminal protocol-integrity result, not a method comparison and supports no efficacy, superiority, transfer, or generalization claim.",
            "The predecessor USD 140 NO-GO record and all raw local artifacts remain immutable and outside this sanitized package.",
        ],
        "evidence": evidence,
    }
    write_json(RUN / "final-report.json", report)
    lines = [
        "# Corrected fixed/dynamic v2: lifecycle-integrity NO-GO",
        "",
        f"Frozen amended manifest SHA-256: `{manifest_hash}`",
        "",
        "**NO-GO.** The USD 160 amendment passed its financial preflight and the combined acquisition gate passed, but mandatory official-upstream ReMe lifecycle construction terminated before evaluation.",
        "",
        "## Durable acquisition gate",
        "",
        f"- Combined trajectories: {gate['planned']}",
        f"- Full official successes: {gate['full_successes']}",
        f"- Successful scenario families: {gate['successful_families']}",
        f"- Gate result: {'PASS' if gate['passed'] else 'FAIL'}",
        "",
        "## Terminal lifecycle condition",
        "",
        "A pinned upstream ReMe failure-extraction request exceeded the frozen 32,768-token input ceiling. The shared transport rejected it before a provider request or ledger reservation; the upstream HTTP service exposed that local condition as HTTP 500. Raising the ceiling or truncating/changing the upstream lifecycle input would alter the frozen scientific protocol, so neither was applied.",
        "",
        f"- Persisted ReMe construction inputs before termination: {len(completed_reme_inputs)}",
        f"- New evaluation trajectories dispatched: 0 / 320",
        f"- Ledger exposure retained/charged: USD {report['ledger']['charged_or_retained_exposure_usd']:.6f} / USD 160.00",
        "",
        "No evaluation score, paired analysis, or method-ranking conclusion exists for this successor.",
    ]
    (RUN / "FINAL_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "final-report.json", report)
    (OUT / "FINAL_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(OUT / "evidence-checksums.json", {"evidence": evidence})
    # A terminal runner state is only durable after the immutable report files
    # themselves exist and are hashed.  This prevents a future launcher from
    # treating an unreported terminal failure as resumable work.
    status["state"] = "terminal_no_go"
    status["final_report_sha256"] = digest(RUN / "final-report.json")
    status["final_report_markdown_sha256"] = digest(RUN / "FINAL_REPORT.md")
    status["terminal_reason"] = "lifecycle_input_ceiling_pre_dispatch"
    write_json(RUN / "runner-status.json", status)
    print("fixed_dynamic_v2_lifecycle_termination_report=passed")


if __name__ == "__main__":
    main()
