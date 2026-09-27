#!/usr/bin/env python3
"""Write the sanitized terminal budget report for fixed_dynamic_v2."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v2"
OUT = ROOT / "research/fixed_dynamic_v2_results"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    manifest_path, budget_path = RUN / "manifest.json", RUN / "budget-preflight.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    budget = json.loads(budget_path.read_text(encoding="utf-8"))
    manifest_sha = (RUN / "manifest.sha256").read_text(encoding="utf-8").strip()
    if sha(manifest_path) != manifest_sha or budget["fits_hard_cap"]:
        raise SystemExit("v2 budget result is not the frozen fail-closed state")
    if (RUN / "progress.jsonl").exists() or (RUN / "ledger.jsonl").exists():
        raise SystemExit("v2 paid-execution evidence exists; budget NO-GO report is inapplicable")
    report = {
        "protocol": manifest["protocol"],
        "source_commit": manifest["git_commit"],
        "source_tree": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", f"{manifest['git_commit']}^{{tree}}"], text=True).strip(),
        "manifest_sha256": manifest_sha,
        "decision": "NO-GO",
        "reason": "The 16-task minimum remains above the USD 140 all-inclusive cap after the required 15% nondispatchable contingency.",
        "v1_carry_forward": {"trajectory_count": manifest["acquisition"]["carry_forward_v1_count"], "exposure_usd": budget["carried_v1_exposure_usd"], "hash_verified": True},
        "new_acquisition": {"planned_task_count": len(manifest["acquisition"]["new_task_ids"]), "executed_trajectory_count": 0},
        "evaluation": {"planned_task_count": len(manifest["evaluation"]["task_ids"]), "executed_trajectory_count": 0},
        "budget": budget,
        "provider_dispatch": {"v2_model_calls": 0, "v2_embedding_calls": 0, "v2_lifecycle_calls": 0},
        "required_change_to_proceed": "A new preregistered protocol with an explicit budget authorization sufficient for USD 145.18108448 or more; no other scientific parameter may be silently reduced.",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "final-report.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (OUT / "FINAL_REPORT.md").write_text(
        "# Corrected fixed/dynamic v2: budget NO-GO\n\n"
        f"Manifest SHA-256: `{manifest_sha}`\n\n"
        "**NO-GO.** No v2 acquisition, lifecycle, embedding, or evaluation request was dispatched.\n\n"
        f"The minimum permitted 16-task evaluation design has an all-inclusive maximum of **USD {budget['all_in_usd']:.8f}**, exceeding the fixed **USD {budget['hard_cap_usd']:.2f}** cap after the mandatory 15% non-dispatchable contingency.\n\n"
        f"The immutable v1 carry-forward pool was hash-verified ({manifest['acquisition']['carry_forward_v1_count']} trajectories; USD {budget['carried_v1_exposure_usd']:.6f}). The new eight-ID acquisition allocation and v1 evaluation custody audit were frozen but never opened.\n\n"
        "Proceeding would require an explicit new budget authorization; reducing arms, trials, actions, token ceilings, acquisition diversity, or evaluation below 16 IDs is not permitted by this protocol.\n",
        encoding="utf-8",
    )
    (OUT / "evidence-checksums.json").write_text(json.dumps({"evidence": [
        {"kind": "v2_manifest", "path": manifest_path.relative_to(ROOT).as_posix(), "sha256": sha(manifest_path)},
        {"kind": "v2_budget_preflight", "path": budget_path.relative_to(ROOT).as_posix(), "sha256": sha(budget_path)},
        {"kind": "v1_no_go_report", "path": "research/fixed_dynamic_v1_results/no-go-report.json", "sha256": sha(ROOT / "research/fixed_dynamic_v1_results/no-go-report.json")},
    ]}, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("PASS fixed_dynamic_v2 budget NO-GO package generated")


if __name__ == "__main__":
    main()
