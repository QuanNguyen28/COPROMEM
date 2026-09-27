#!/usr/bin/env python3
"""Build a sanitized NO-GO report for the corrected fixed/dynamic pilot.

This tool is deliberately read-only with respect to raw evidence.  It writes
only compact derived results and SHA-256 evidence references; task prompts,
action histories, provider responses, and credentials remain in ignored local
artifacts.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v1"
OUT = ROOT / "research/fixed_dynamic_v1_results"


def canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> None:
    manifest_path = RUN / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_sha = (RUN / "manifest.sha256").read_text(encoding="utf-8").strip()
    if canonical_sha(manifest) != manifest_sha:
        raise SystemExit("manifest digest mismatch")

    expected = [
        (task_id, seed, index)
        for task_id in manifest["acquisition"]["task_ids"]
        for index, seed in enumerate(manifest["acquisition"]["seeds"])
    ]
    artifacts: list[dict] = []
    evidence: list[dict] = [
        {
            "kind": "manifest",
            "path": manifest_path.relative_to(ROOT).as_posix(),
            "sha256": file_sha(manifest_path),
        }
    ]
    for path in sorted((RUN / "acquisition").glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        required = {"task_id", "seed", "trial_id", "after_score", "actions", "termination"}
        if not required.issubset(raw):
            raise SystemExit(f"incomplete acquisition artifact: {path.name}")
        artifacts.append(
            {
                "task_id": raw["task_id"],
                "seed": raw["seed"],
                "trial": raw["trial_id"],
                "after_score": raw["after_score"],
                "actions": raw["actions"],
                "termination": raw["termination"],
            }
        )
        evidence.append(
            {
                "kind": "acquisition_artifact",
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": file_sha(path),
            }
        )
    actual = {(row["task_id"], int(row["seed"]), int(row["trial"])) for row in artifacts}
    if actual != set(expected):
        raise SystemExit(f"acquisition identity mismatch: {len(actual)}/{len(expected)}")

    full = [row for row in artifacts if float(row["after_score"]) == 1.0]
    family = lambda task_id: str(task_id).split("_", 1)[0]
    full_families = sorted({family(row["task_id"]) for row in full})
    successes_by_family: dict[str, int] = defaultdict(int)
    for row in full:
        successes_by_family[family(row["task_id"])] += 1

    progress_path = RUN / "progress.jsonl"
    ledger_path = RUN / "ledger.jsonl"
    progress = jsonl(progress_path)
    ledger = jsonl(ledger_path)
    evidence.extend(
        [
            {"kind": "progress", "path": progress_path.relative_to(ROOT).as_posix(), "sha256": file_sha(progress_path)},
            {"kind": "ledger", "path": ledger_path.relative_to(ROOT).as_posix(), "sha256": file_sha(ledger_path)},
        ]
    )
    calls = [row for row in progress if row.get("event") == "call_settled"]
    if any("evaluation" in str(row.get("role", "")) or "lifecycle" in str(row.get("role", "")) for row in calls):
        raise SystemExit("post-acquisition provider call found in NO-GO run")
    latest: dict[str, dict] = {}
    for row in ledger:
        if row.get("event") in {"reserve", "settle"}:
            latest[str(row["id"])] = row
    settled = [row for row in latest.values() if row.get("event") == "settle"]
    retained = [row for row in latest.values() if row.get("event") == "reserve"]
    exposure = sum(float(row["usd"]) for row in settled + retained)

    report = {
        "protocol": manifest["protocol"],
        "manifest_sha256": manifest_sha,
        "decision": "NO-GO",
        "reason": "Preregistered acquisition gate failed; evaluation and lifecycle construction were not started.",
        "gate": {
            "required_full_successes": 8,
            "observed_full_successes": len(full),
            "required_distinct_success_families": 6,
            "observed_distinct_success_families": len(full_families),
            "full_successes_by_family": dict(sorted(successes_by_family.items())),
            "passed": False,
        },
        "acquisition": {
            "expected_trajectories": len(expected),
            "completed_trajectories": len(artifacts),
            "complete": len(artifacts) == len(expected),
            "rows": sorted(artifacts, key=lambda row: (row["task_id"], row["seed"])),
        },
        "provider_usage": {
            "settled_calls": len(calls),
            "prompt_tokens": sum(int(row.get("prompt_tokens") or 0) for row in calls),
            "completion_tokens": sum(int(row.get("completion_tokens") or 0) for row in calls),
            "reasoning_tokens": sum(int(row.get("reasoning_tokens") or 0) for row in calls),
            "latency_seconds": sum(float(row.get("latency") or 0) for row in calls),
            "settled_or_retained_usd": exposure,
            "hard_cap_usd": float(manifest["budget"]["hard_cap_usd"]),
        },
        "execution_boundary": {
            "evaluation_trajectories": 0,
            "lifecycle_calls": 0,
            "no_go_before_evaluation": True,
        },
        "evidence_index_sha256": canonical_sha(evidence),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "no-go-report.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (OUT / "evidence-checksums.json").write_text(json.dumps({"evidence": evidence}, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Corrected fixed/dynamic pilot: acquisition NO-GO",
        "",
        f"Manifest SHA-256: `{manifest_sha}`",
        "",
        "**NO-GO.** The preregistered acquisition gate failed, so no lifecycle construction or evaluation trajectory was run.",
        "",
        f"- Acquisition: {len(artifacts)}/{len(expected)} trajectories durably completed.",
        f"- Full official successes: {len(full)}/8 required.",
        f"- Distinct successful families: {len(full_families)}/6 required.",
        f"- Settled or retained provider exposure: USD {exposure:.6f} of USD {float(manifest['budget']['hard_cap_usd']):.2f}.",
        f"- Provider calls: {len(calls)}; prompt tokens: {sum(int(row.get('prompt_tokens') or 0) for row in calls)}; completion tokens: {sum(int(row.get('completion_tokens') or 0) for row in calls)}.",
        "",
        "Raw task text, action histories, scorer artifacts, provider responses, and ledger records remain local and ignored. The checksum index binds this report to that local evidence.",
    ]
    (OUT / "NO_GO_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("PASS corrected fixed/dynamic acquisition NO-GO report generated")


if __name__ == "__main__":
    main()
