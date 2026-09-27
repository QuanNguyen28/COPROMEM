#!/usr/bin/env python3
"""Freeze and verify the fixed/dynamic v2 successor without opening payloads."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v1"
RUN = ROOT / "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v2"
SALT = "fixed_dynamic_v2_acquisition_id_only_20260927"
V1_ACQUISITION = [
    "22cc237_1", "22cc237_2", "27e1026_1", "27e1026_2", "287e338_1", "287e338_2",
    "29caf6f_1", "29caf6f_2", "2a163ab_1", "2a163ab_2", "302c169_1", "302c169_2",
]
V1_EVALUATION = [
    "3aa1a22_1", "2d9f728_1", "a30375d_1", "f323bae_1", "ff58e36_1", "325d6ec_1",
    "bde252e_1", "32616b5_1", "b9c5c9a_1", "ffe6d5e_1", "0a9d82a_1", "522e5e5_1",
    "90adc3f_1", "f861c32_1", "9dabbc9_1", "fd1f8fa_1",
]
# Selected by SHA-256(salt + "|" + ID) from the ID-only train inventory,
# with the five successful v1 families and historical used IDs excluded.
NEW_ACQUISITION = [
    "afc0fce_1", "e3d6c94_1", "b0a8eae_1", "d0b1f43_1",
    "692c77d_1", "cf6abd2_3", "6104387_1", "60d0b5b_2",
]
FULL_SUCCESS_FAMILIES_V1 = {"22cc237", "27e1026", "287e338", "29caf6f", "2a163ab"}
KNOWN_EXECUTED_OUTSIDE_RESEARCH = {"50e1ac9_1", "50e1ac9_2", "fac291d_1", "82e2fac_1"}

INPUT_PRICE = 0.30 / 1_000_000
OUTPUT_PRICE = 1.20 / 1_000_000
INPUT_TOKENS = 32_768
OUTPUT_TOKENS = 2_048
EMBEDDING_PRICE = 0.0000001


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def historical_execution_ids(*, evaluation_only: bool = False) -> set[str]:
    """Extract IDs from actual-run evidence, never benchmark inventories.

    This is an exposure audit over reports, journals, ledgers and completed
    artifacts.  It deliberately excludes ID inventories and broad benchmark
    scans, which identify availability rather than prior use.
    """
    result = set(KNOWN_EXECUTED_OUTSIDE_RESEARCH)
    pattern = re.compile(r"\b[0-9a-f]{7}_[0-9]+\b")
    roots = [ROOT / "artifacts/research", ROOT / "research"]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or "fixed_dynamic_v2" in path.parts:
                continue
            lowered = path.as_posix().lower()
            if any(token in path.name.lower() for token in ("ids", "inventory", "exposure")):
                continue
            if evaluation_only:
                relevant = "/evaluation/" in lowered or any(token in path.name.lower() for token in ("completed", "final-report", "final_report"))
            else:
                relevant = any(token in lowered for token in ("/acquisition", "/evaluation", "/journals", "/completed", "/progress", "/ledger", "final-report", "final_report", "/result", "/report"))
            if not relevant:
                continue
            try:
                result.update(pattern.findall(path.read_text(encoding="utf-8", errors="ignore")))
            except OSError:
                continue
    return result


def budget(eval_tasks: int = 16, *, hard_cap_usd: float = 140.0) -> dict:
    """All maxima are registered, not expected early-stop values."""
    if eval_tasks < 16:
        raise ValueError("protocol forbids fewer than 16 evaluation task IDs")
    per_chat = INPUT_TOKENS * INPUT_PRICE + OUTPUT_TOKENS * OUTPUT_PRICE
    executor_calls = len(NEW_ACQUISITION) * 30 + eval_tasks * 4 * 5 * 30
    copro_calls = 320
    reme_summary_calls = 32 + 64  # one initial summary per pool item + dynamic summaries
    embedding_calls = 216
    executor = executor_calls * per_chat
    copro = copro_calls * per_chat
    reme = reme_summary_calls * per_chat
    embeddings = embedding_calls * 8_192 * EMBEDDING_PRICE
    carried = 0.048008  # rounded upward from immutable v1 exposure 0.048007521
    dispatchable = executor + copro + reme + embeddings
    contingency = dispatchable * 0.15
    all_in = carried + dispatchable + contingency
    return {
        "hard_cap_usd": hard_cap_usd,
        "carried_v1_exposure_usd": carried,
        "executor_calls": executor_calls,
        "executor_usd": executor,
        "copromem_decomposition_calls": copro_calls,
        "copromem_decomposition_usd": copro,
        "reme_lifecycle_calls": reme_summary_calls,
        "reme_lifecycle_usd": reme,
        "embedding_calls": embedding_calls,
        "embedding_usd": embeddings,
        "dispatchable_usd": dispatchable,
        "nondispatchable_contingency_fraction": 0.15,
        "nondispatchable_contingency_usd": contingency,
        "all_in_usd": all_in,
        "fits_hard_cap": all_in <= hard_cap_usd,
    }


def verify_v1() -> list[dict]:
    report = json.loads((ROOT / "research/fixed_dynamic_v1_results/no-go-report.json").read_text(encoding="utf-8"))
    evidence = json.loads((ROOT / "research/fixed_dynamic_v1_results/evidence-checksums.json").read_text(encoding="utf-8"))["evidence"]
    expected_hashes = {entry["path"]: entry["sha256"] for entry in evidence if entry["kind"] == "acquisition_artifact"}
    v1_manifest = json.loads((V1 / "manifest.json").read_text(encoding="utf-8"))
    expected = {(task, seed, trial) for task in V1_ACQUISITION for trial, seed in enumerate(v1_manifest["acquisition"]["seeds"])}
    found: list[dict] = []
    report_mtime = (ROOT / "research/fixed_dynamic_v1_results/no-go-report.json").stat().st_mtime_ns
    for path in sorted((V1 / "acquisition").glob("*.json")):
        relative = path.relative_to(ROOT).as_posix()
        if expected_hashes.get(relative) != sha_file(path):
            raise RuntimeError(f"v1 acquisition hash mismatch: {path.name}")
        if path.stat().st_mtime_ns > report_mtime:
            raise RuntimeError(f"v1 acquisition modified after its immutable report: {path.name}")
        row = json.loads(path.read_text(encoding="utf-8"))
        identity = (str(row["task_id"]), int(row["seed"]), int(row["trial_id"]))
        if identity not in expected or "history" not in row or not row.get("history_sha256"):
            raise RuntimeError(f"v1 acquisition identity/history invalid: {path.name}")
        journal = V1 / "journals" / f"acquisition_shared_acquisition_{row['task_id']}_trial_{row['trial_id']}_seed_{row['seed']}.jsonl"
        events = rows(journal) if journal.exists() else []
        if not any(event.get("event") == "official_score" for event in events):
            raise RuntimeError(f"v1 acquisition lacks official scorer journal: {path.name}")
        instruction = next((str(item.get("content") or "") for item in row["history"] if item.get("role") == "user"), "")
        if not instruction:
            raise RuntimeError(f"v1 acquisition lacks public instruction: {path.name}")
        found.append({**row, "instruction": instruction, "source_artifact": str(path),
                      "source_artifact_sha256": sha_file(path),
                      "acquisition_identity": f"{row['task_id']}::seed={row['seed']}::trajectory={row['trial_id']}"})
    if {(row["task_id"], int(row["seed"]), int(row["trial_id"])) for row in found} != expected:
        raise RuntimeError("v1 carry-forward set is incomplete or contains an unexpected identity")
    if report["acquisition"]["completed_trajectories"] != 24 or report["execution_boundary"]["evaluation_trajectories"] != 0:
        raise RuntimeError("v1 NO-GO report is inconsistent with carry-forward protocol")
    return found


def verify_v1_evaluation_custody() -> None:
    progress = rows(V1 / "progress.jsonl")
    ledger = rows(V1 / "ledger.jsonl")
    if any(row.get("phase") == "evaluation" or "evaluation" in str(row.get("role", "")) for row in progress + ledger):
        raise RuntimeError("v1 evaluation allocation was used and cannot be reused")
    evaluation_dir = V1 / "evaluation"
    if evaluation_dir.exists() and any(evaluation_dir.rglob("*.json")):
        raise RuntimeError("v1 evaluation artifacts exist and cannot be reused")
    prior_families = {item.split("_", 1)[0] for item in historical_execution_ids(evaluation_only=True)}
    reused_families = {item.split("_", 1)[0] for item in V1_EVALUATION}
    if set(V1_EVALUATION) & historical_execution_ids(evaluation_only=True) or reused_families & prior_families:
        raise RuntimeError("v1 evaluation allocation overlaps a prior evaluation exposure")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hard-cap-usd", type=float, default=140.0)
    parser.add_argument("--amendment", action="store_true")
    args = parser.parse_args()
    if args.hard_cap_usd not in {140.0, 160.0}:
        raise SystemExit("only the immutable USD 140 record or authorized USD 160 amendment is permitted")
    if args.amendment != (args.hard_cap_usd == 160.0):
        raise SystemExit("USD 160 requires --amendment; USD 140 may not be overwritten as an amendment")
    carry = verify_v1()
    verify_v1_evaluation_custody()
    train = set((ROOT / "research/train_ids.txt").read_text(encoding="utf-8").split())
    test = set((ROOT / "research/test_normal_ids.txt").read_text(encoding="utf-8").split())
    if not set(NEW_ACQUISITION).issubset(train) or not set(V1_EVALUATION).issubset(test):
        raise RuntimeError("frozen allocation absent from ID-only inventory")
    if len(NEW_ACQUISITION) != 8 or len({item.split("_", 1)[0] for item in NEW_ACQUISITION}) < 4:
        raise RuntimeError("successor acquisition diversity invariant failed")
    if FULL_SUCCESS_FAMILIES_V1 & {item.split("_", 1)[0] for item in NEW_ACQUISITION}:
        raise RuntimeError("successor acquisition reused a successful v1 family")
    historical_ids = historical_execution_ids()
    if set(NEW_ACQUISITION) & historical_ids:
        raise RuntimeError("successor acquisition reuses a historically executed exact ID")
    cost = budget(len(V1_EVALUATION), hard_cap_usd=args.hard_cap_usd)
    if args.amendment:
        prior_manifest = RUN / "manifest.json"
        prior_hash = (RUN / "manifest.sha256").read_text(encoding="utf-8").strip()
        if not prior_manifest.is_file() or sha_file(prior_manifest) != prior_hash:
            raise RuntimeError("immutable USD 140 manifest is absent or modified")
        cost["ledger_dispatch_cap_usd"] = args.hard_cap_usd - cost["nondispatchable_contingency_usd"]
    manifest = {
        "protocol": "corrected_fixed_dynamic_appworld_v2",
        "git_commit": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "status": "budget_preflight_failed" if not cost["fits_hard_cap"] else "frozen",
        "selection_salt": SALT,
        "acquisition": {"carry_forward_v1_count": len(carry), "new_task_ids": NEW_ACQUISITION,
                        "new_seeds": [7301], "combined_count": 32},
        "evaluation": {"task_ids": V1_EVALUATION, "trial_ids": [1, 2, 3, 4], "custody": "v1 allocation reused after zero-evaluation audit"},
        "arms": ["no_memory", "official_upstream_reme_fixed", "official_upstream_reme_dynamic", "copromem_fixed", "copromem_dynamic"],
        "limits": {"actions": 30, "input_tokens": INPUT_TOKENS, "completion_tokens": OUTPUT_TOKENS, "temperature": 0.7, "top_p": 1.0},
        "route": {"model": "deepseek/deepseek-v4.1-flash", "provider_only": "deepseek", "fallbacks": False, "reasoning_effort": "none", "stream": False},
        "embedding": {"model": "openai/text-embedding-3-small", "provider_only": "azure", "dimensions": 1024},
        "budget": cost,
        "carry_forward": [{"identity": row["acquisition_identity"], "path": Path(row["source_artifact"]).relative_to(ROOT).as_posix(), "sha256": row["source_artifact_sha256"]} for row in carry],
        "historical_execution_id_count": len(historical_ids),
        "historical_execution_ids_sha256": canonical_sha(sorted(historical_ids)),
    }
    if args.amendment:
        manifest["budget_amendment"] = {"version": 1, "authorized_hard_cap_usd": 160.0,
                                          "preserved_prior_manifest_sha256": prior_hash,
                                          "reason": "explicit user authorization"}
    RUN.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    suffix = "-budget-160" if args.amendment else ""
    (RUN / f"manifest{suffix}.json").write_bytes(raw)
    (RUN / f"manifest{suffix}.sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n", encoding="utf-8")
    (RUN / f"budget-preflight{suffix}.json").write_text(json.dumps(cost, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if args.amendment:
        (RUN / "budget-amendment-v1.json").write_text(json.dumps(manifest["budget_amendment"], sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest_sha256": hashlib.sha256(raw).hexdigest(), "budget": cost}, sort_keys=True))


if __name__ == "__main__":
    main()
