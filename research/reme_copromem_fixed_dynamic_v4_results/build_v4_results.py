#!/usr/bin/env python3
"""Build a sanitized, read-only publication package for fixed_dynamic_v4.

The input directory is immutable local evidence.  This program performs no
network, provider, model, embedding, AppWorld, or benchmark operation.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import pathlib
import random
import subprocess
from collections import Counter, defaultdict
from itertools import combinations
from typing import Any, Iterable


EXPECTED_MANIFEST = "ded3741ee2c03bd0b54be1d9326121af113ed28595ea32c396facc8aff8a4460"
EXPECTED_FINAL_REPORT = "ce92a1b4ebd718845461708723bde0add6b6337c1781f88fcafdcb8e588e28af"
ARMS = ("copromem_dynamic", "copromem_fixed", "no_memory", "official_upstream_reme_dynamic", "official_upstream_reme_fixed")
EXPERIMENT_COMMIT = "28d3dab36cb12ea03572376ab1fee35423c50871"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_digest(value: Any) -> str:
    return sha256_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def read_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def percentile(values: list[float], p: float) -> float:
    if not values:
        raise ValueError("empty percentile input")
    ordered = sorted(values)
    index = (len(ordered) - 1) * p
    low, high = math.floor(index), math.ceil(index)
    return ordered[low] if low == high else ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def clustered_bootstrap(cluster_values: dict[str, list[float]], iterations: int = 10_000) -> list[float]:
    """Task-cluster bootstrap: sample complete task clusters with replacement."""
    tasks = sorted(cluster_values)
    if not tasks:
        raise ValueError("no task clusters")
    rng = random.Random(20260927)
    samples: list[float] = []
    for _ in range(iterations):
        selected = [rng.choice(tasks) for _ in tasks]
        flattened = [value for task in selected for value in cluster_values[task]]
        samples.append(sum(flattened) / len(flattened))
    return [percentile(samples, 0.025), percentile(samples, 0.975)]


def exact_cluster_signflip(cluster_values: dict[str, list[float]]) -> float:
    """Two-sided exact sign-flip test on task-level paired mean differences."""
    means = [sum(values) / len(values) for _, values in sorted(cluster_values.items())]
    observed = abs(sum(means) / len(means))
    extreme = 0
    for signs in itertools.product((-1.0, 1.0), repeat=len(means)):
        statistic = abs(sum(sign * value for sign, value in zip(signs, means)) / len(means))
        extreme += statistic >= observed - 1e-15
    return extreme / (2 ** len(means))


def cohen_dz(cluster_values: dict[str, list[float]]) -> float | None:
    means = [sum(values) / len(values) for values in cluster_values.values()]
    mean = sum(means) / len(means)
    if len(means) < 2:
        return None
    variance = sum((item - mean) ** 2 for item in means) / (len(means) - 1)
    return None if variance == 0 else mean / math.sqrt(variance)


def holm_adjust(p_values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    result: dict[str, float] = {}
    running = 0.0
    total = len(ordered)
    for index, (name, p_value) in enumerate(ordered):
        running = max(running, min(1.0, (total - index) * p_value))
        result[name] = running
    return result


def runner_is_active(status: dict[str, Any]) -> bool:
    pid = status.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        completed = subprocess.run(["wsl.exe", "-d", "Ubuntu", "--", "kill", "-0", str(pid)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("cannot verify completed runner process state") from exc
    return completed.returncode == 0


def verify_ledger(run: pathlib.Path) -> dict[str, Any]:
    ledger_path = run / "ledger.jsonl"
    progress_path = run / "progress.jsonl"
    events = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line]
    reserves = {item["id"]: item for item in events if item.get("event") == "reserve"}
    settled = {item["id"]: item for item in events if item.get("event") == "settle"}
    progress = [json.loads(line) for line in progress_path.read_text(encoding="utf-8").splitlines() if line]
    unresolved = []
    for call_id, reserve in reserves.items():
        if call_id in settled:
            continue
        if reserve.get("role") == "historical_carry_forward":
            unresolved.append({"id": call_id, "classification": "historical_carried_exposure", "role": reserve.get("role")})
        elif any(item.get("event") == "call_failed" and item.get("id") == call_id for item in progress):
            unresolved.append({"id": call_id, "classification": "retained_after_recorded_failure", "role": reserve.get("role")})
        else:
            raise RuntimeError(f"unclassified unresolved reservation: {call_id}")
    latest = {call_id: float(settled.get(call_id, reserve)["usd"]) for call_id, reserve in reserves.items()}
    return {"path": "ledger.jsonl", "sha256": sha256_bytes(ledger_path.read_bytes()),
            "reserve_count": len(reserves), "settle_count": len(settled),
            "charged_or_retained_usd": sum(latest.values()),
            "settled_count": len(settled), "unresolved_classifications": unresolved,
            "unresolved_count": len(unresolved)}


def load_evidence(run: pathlib.Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    status_path, manifest_path, final_path = run / "runner-status.json", run / "manifest.json", run / "final-report.json"
    status, manifest = read_json(status_path), read_json(manifest_path)
    if status.get("state") != "completed" or runner_is_active(status):
        raise RuntimeError("runner is not durably completed and inactive")
    if sha256_bytes(manifest_path.read_bytes()) != EXPECTED_MANIFEST:
        raise RuntimeError("manifest SHA-256 mismatch")
    if sha256_bytes(final_path.read_bytes()) != EXPECTED_FINAL_REPORT:
        raise RuntimeError("final report SHA-256 mismatch")
    if status.get("manifest_sha256") != EXPECTED_MANIFEST or status.get("final_report_sha256") != EXPECTED_FINAL_REPORT:
        raise RuntimeError("runner status hash mismatch")
    if set(manifest.get("arms", ())) != set(ARMS) or len(manifest.get("arms", ())) != len(ARMS):
        raise RuntimeError("manifest arm allocation mismatch")
    tasks = list(manifest["evaluation"]["task_ids"])
    trials, seeds = list(manifest["evaluation"]["trial_ids"]), list(manifest["evaluation"]["seeds"])
    if len(tasks) != 16 or len(trials) != 4 or len(seeds) != 4 or len(tasks) * len(trials) * len(ARMS) != 320:
        raise RuntimeError("unexpected fixed_dynamic_v4 allocation")
    seed_for_trial = dict(zip(trials, seeds))
    wanted = {(arm, task, trial) for arm in ARMS for task in tasks for trial in trials}
    rows: list[dict[str, Any]] = []
    checksums: list[dict[str, str]] = []
    seen = set()
    for path in sorted((run / "evaluation").glob("*/*/trial-*.json")):
        item = read_json(path)
        key = (item.get("arm"), item.get("task_id"), item.get("trial_id"))
        if key not in wanted or key in seen or item.get("seed") != seed_for_trial[key[2]]:
            raise RuntimeError("invalid or duplicate evaluation key")
        history = item.get("history")
        if not isinstance(history, list) or canonical_digest(history) != item.get("history_sha256"):
            raise RuntimeError("stored history hash mismatch")
        if not isinstance(item.get("after_score"), (int, float)) or not isinstance(item.get("actions"), int):
            raise RuntimeError("incomplete scorer/action record")
        seen.add(key)
        relative = path.relative_to(run).as_posix()
        checksums.append({"path": relative, "sha256": sha256_bytes(path.read_bytes())})
        rows.append({"arm": key[0], "task_id": key[1], "trial_id": key[2], "seed": item["seed"],
                     "score": float(item["after_score"]), "success": float(item["after_score"]) == 1.0,
                     "actions": item["actions"], "termination": item.get("termination"),
                     "history_sha256": item["history_sha256"], "artifact_sha256": checksums[-1]["sha256"]})
    if seen != wanted or len(rows) != 320:
        raise RuntimeError(f"evaluation evidence incomplete: {len(rows)}/320")
    for path in (status_path, manifest_path, final_path, run / "progress.jsonl", run / "ledger.jsonl"):
        checksums.append({"path": path.relative_to(run).as_posix(), "sha256": sha256_bytes(path.read_bytes())})
    return manifest, rows, {"checksums": checksums, "ledger": verify_ledger(run)}


def aggregates(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result = {}
    for arm in ARMS:
        selected = [row for row in rows if row["arm"] == arm]
        successful = [row for row in selected if row["success"]]
        result[arm] = {"completed": len(selected), "successes": len(successful),
                       "avg_score": sum(row["score"] for row in selected) / len(selected),
                       "success_rate": len(successful) / len(selected),
                       "avg_actions_all": sum(row["actions"] for row in selected) / len(selected),
                       "success_conditioned_action_denominator": len(successful),
                       "avg_actions_successful": (sum(row["actions"] for row in successful) / len(successful) if successful else None)}
    return result


def verify_display_reconciliation(aggregate: dict[str, Any]) -> None:
    """Treat the requested rounded table as an audit target, never as input."""
    target = {
        "copromem_dynamic": (48, 0.859, 0.750, 15.9),
        "copromem_fixed": (43, 0.847, 0.672, 17.8),
        "no_memory": (49, 0.875, 0.766, 17.3),
        "official_upstream_reme_dynamic": (42, 0.799, 0.656, 16.7),
        "official_upstream_reme_fixed": (50, 0.874, 0.781, 17.8),
    }
    for arm, (successes, score, rate, actions) in target.items():
        observed = aggregate[arm]
        if (observed["successes"] != successes or round(observed["avg_score"], 3) != score
                or round(observed["success_rate"], 3) != rate or round(observed["avg_actions_all"], 1) != actions):
            raise RuntimeError(f"aggregate reconciliation target mismatch: {arm}")


def paired_analysis(rows: list[dict[str, Any]]) -> dict[str, Any]:
    lookup = {(row["arm"], row["task_id"], row["seed"], row["trial_id"]): row for row in rows}
    comparisons = {}
    score_p, success_p = {}, {}
    for left, right in combinations(ARMS, 2):
        key = f"{left}__minus__{right}"
        clusters_score: dict[str, list[float]] = defaultdict(list)
        clusters_success: dict[str, list[float]] = defaultdict(list)
        all_action, success_action = [], []
        for task in sorted({row["task_id"] for row in rows}):
            task_rows = [row for row in rows if row["task_id"] == task and row["arm"] == left]
            for row in task_rows:
                paired = lookup.get((right, task, row["seed"], row["trial_id"]))
                if paired is None:
                    raise RuntimeError("missing matched pair")
                clusters_score[task].append(row["score"] - paired["score"])
                clusters_success[task].append(float(row["success"]) - float(paired["success"]))
                all_action.append(row["actions"] - paired["actions"])
                if row["success"] and paired["success"]:
                    success_action.append(row["actions"] - paired["actions"])
        score_mean = sum(value for values in clusters_score.values() for value in values) / 64
        success_mean = sum(value for values in clusters_success.values() for value in values) / 64
        item = {"left": left, "right": right, "matched_pairs": 64, "missing_pairs": 0,
                "task_clusters": len(clusters_score),
                "score": {"mean_difference": score_mean, "bootstrap_95_ci": clustered_bootstrap(clusters_score),
                          "exact_signflip_p": exact_cluster_signflip(clusters_score), "clustered_cohen_dz": cohen_dz(clusters_score)},
                "success": {"mean_difference": success_mean, "bootstrap_95_ci": clustered_bootstrap(clusters_success),
                            "exact_signflip_p": exact_cluster_signflip(clusters_success), "clustered_cohen_dz": cohen_dz(clusters_success)},
                "actions_all_trajectories": {"matched_pairs": len(all_action), "mean_difference": sum(all_action) / len(all_action)},
                "actions_conditioned_on_both_successes": {"matched_pairs": len(success_action),
                                                           "mean_difference": sum(success_action) / len(success_action) if success_action else None}}
        comparisons[key] = item
        score_p[key], success_p[key] = item["score"]["exact_signflip_p"], item["success"]["exact_signflip_p"]
    for key, value in comparisons.items():
        value["score"]["holm_adjusted_p"] = holm_adjust(score_p)[key]
        value["success"]["holm_adjusted_p"] = holm_adjust(success_p)[key]
    return {"label": "exploratory; tests were not preregistered", "method": "task-cluster bootstrap (10,000 resamples) and exact task-level sign-flip tests",
            "multiplicity": "Holm adjustment separately across the ten score and ten success comparisons", "comparisons": comparisons}


def markdown(aggregate: dict[str, Any], analysis: dict[str, Any]) -> str:
    lines = ["# fixed_dynamic_v4 final report", "", "**Exploratory analysis of a completed fixed-dynamic experiment.**", "",
             "| Arm | Completed | Successes | AvgScore | SuccessRate | AvgActions |",
             "|---|---:|---:|---:|---:|---:|"]
    for arm in ARMS:
        row = aggregate[arm]
        lines.append(f"| {arm} | {row['completed']} | {row['successes']} | {row['avg_score']:.3f} | {row['success_rate']:.3f} | {row['avg_actions_all']:.1f} |")
    lines += ["", "All 320/320 registered trajectories completed. A success is an official AppWorld score of 1.0; AvgScore retains fractional official scores.",
              "", "## Paired exploratory analysis", "", "Every arm pair has 64 matched task/seed/trial records. Confidence intervals are task-cluster bootstrap 95% intervals; p-values are exact task-level sign-flip tests with Holm correction.",
              "", "| Pair (left - right) | Score difference [95% CI] | score dz / Holm p | Success difference [95% CI] | success dz / Holm p |",
              "|---|---:|---:|---:|---:|"]
    for key, item in analysis["comparisons"].items():
        score, success = item["score"], item["success"]
        score_dz = "n/a" if score["clustered_cohen_dz"] is None else f"{score['clustered_cohen_dz']:.3f}"
        success_dz = "n/a" if success["clustered_cohen_dz"] is None else f"{success['clustered_cohen_dz']:.3f}"
        lines.append(f"| {key} | {score['mean_difference']:.4f} [{score['bootstrap_95_ci'][0]:.4f}, {score['bootstrap_95_ci'][1]:.4f}] | {score_dz} / {score['holm_adjusted_p']:.4f} | {success['mean_difference']:.4f} [{success['bootstrap_95_ci'][0]:.4f}, {success['bootstrap_95_ci'][1]:.4f}] | {success_dz} / {success['holm_adjusted_p']:.4f} |")
    lines += ["", "## Action analysis", "", "All-trajectory action means and success-conditioned action means are reported separately; conditioning changes the population and is not an efficacy estimate.", "",
              "| Arm | all trajectories | successful trajectories (n) | successful-only mean actions |",
              "|---|---:|---:|---:|"]
    for arm in ARMS:
        item = aggregate[arm]
        success_mean = "n/a" if item["avg_actions_successful"] is None else f"{item['avg_actions_successful']:.2f}"
        lines.append(f"| {arm} | {item['avg_actions_all']:.2f} | {item['success_conditioned_action_denominator']} | {success_mean} |")
    lines += ["", "Pairwise all-trajectory and both-successes-conditioned action differences, with their pair denominators, are in `statistical-analysis.json`; no action-only comparison is treated as evidence of efficacy."]
    lines += ["", "## Conclusions", "",
              "- ReMe Fixed had the largest number of full successes.",
              "- No Memory had the highest mean score, approximately tied with ReMe Fixed.",
              "- CoProMem Dynamic improved over CoProMem Fixed and used the fewest mean actions.",
              "- CoProMem Dynamic did not outperform No Memory or ReMe Fixed on raw efficacy.",
              "- ReMe Dynamic underperformed ReMe Fixed in this run.",
              "- No superiority claim is made: corrected paired exploratory tests govern any inferential interpretation.",
              "", "## Limitations", "",
              "- This is an exploratory faithful adaptation, not an exact ReMe paper reproduction.",
              "- Results are exact-ID holdout only; they do not establish task-family or benchmark-wide generalization.",
              "- Raw trajectories, prompts, memory text, provider responses, and local evidence remain excluded from Git."]
    return "\n".join(lines) + "\n"


def readme() -> str:
    return """# fixed_dynamic_v4: sanitized review package

## Research question

The experiment compares no memory, official-upstream ReMe Fixed, official-upstream ReMe Dynamic, CoProMem Fixed, and CoProMem Dynamic under a common AppWorld executor and official scorer.

**Acquisition** is the shared collection of 32 trajectories used to construct memory. **Evaluation** is the held-out execution phase. The completed run evaluated 16 tasks, four seeds/trials per task, five arms, and therefore 320 trajectories (64 per arm).

The executor route was OpenRouter `deepseek/deepseek-v4.1-flash`, pinned to the DeepSeek provider with fallback and reasoning disabled. ReMe embeddings used OpenRouter Azure `openai/text-embedding-3-small` at 1024 dimensions.

`AvgScore` is the mean official AppWorld score, including fractional scores. `SuccessRate` is the proportion with full official score 1.0. `Successes` is the corresponding full-score count. `AvgActions` is the mean executor action count. All 320/320 registered trajectories completed.

Read [FINAL_REPORT.md](FINAL_REPORT.md) with [statistical-analysis.json](statistical-analysis.json). The inference is exploratory: it cannot support a superiority, task-family-generalization, or exact-paper-reproduction claim without supporting paired corrected evidence.
"""


def walkthrough() -> str:
    base = "https://github.com/QuanNguyen28/COPROMEM/blob/"
    historical = base + EXPERIMENT_COMMIT + "/"
    rows = [
        ("Entry point and control flow", "../../src/copromem/experiments/reme_copromem/config.py", "scripts/run_fixed_dynamic_v4.py"),
        ("Common AppWorld executor and scorer", "../../src/copromem/experiments/reme_copromem/runner.py", "research/official_pilot/five_arm_runner.py"),
        ("Official-upstream ReMe integration", "../../src/copromem/integrations/reme/upstream_executor.py", "research/official_pilot/upstream_executor.py"),
        ("ReMe Fixed lifecycle", "../../src/copromem/integrations/reme/lifecycle.py", "research/official_pilot/evaluation_lifecycle.py"),
        ("ReMe Dynamic lifecycle and update timing", "../../src/copromem/integrations/reme/lifecycle.py", "research/official_pilot/evaluation_lifecycle.py"),
        ("CoProMem bank and retrieval", "../../src/copromem/benchmarks/appworld/adapter.py", "src/copromem/appworld_comparison_adapter.py"),
        ("CoProMem Fixed lifecycle", "../../src/copromem/benchmarks/appworld/adapter.py", "src/copromem/appworld_comparison_adapter.py"),
        ("CoProMem Dynamic lifecycle and update timing", "../../src/copromem/benchmarks/appworld/adapter.py", "src/copromem/appworld_comparison_adapter.py"),
        ("Retrieval provenance", "../../src/copromem/benchmarks/appworld/adapter.py", "scripts/run_fixed_dynamic_v4.py"),
        ("Journaling, restart, integrity", "../../src/copromem/experiments/reme_copromem/runner.py", "research/official_pilot/five_arm_runner.py"),
        ("Report generation", "build_v4_results.py", "research/scripts/build_fixed_dynamic_v4_report.py"),
    ]
    lines = ["# v4 code walkthrough", "", "Read canonical review code first. Historical links are immutable and identify behavior of the exact experiment commit.", ""]
    for number, (title, canonical, old) in enumerate(rows, 1):
        lines.append(f"{number}. **{title}:** [canonical review source]({canonical}); [exact v4 source]({historical + old}).")
    return "\n".join(lines) + "\n"


def reproducibility_map(review_commit: str) -> str:
    return f"""# v4 reproducibility map

- Experiment branch: `experiment-reme-copromem-fixed-dynamic-v4`
- Exact experiment code: [`{EXPERIMENT_COMMIT}`](https://github.com/QuanNguyen28/COPROMEM/tree/{EXPERIMENT_COMMIT})
- Review branch: `reme-copromem-fixed-dynamic-review`
- Review package commit at generation: `{review_commit}`
- Manifest SHA-256: `{EXPECTED_MANIFEST}`
- Final report SHA-256: `{EXPECTED_FINAL_REPORT}`

| Exact v4 runtime file | Canonical review replacement | Difference |
|---|---|---|
| `scripts/run_fixed_dynamic_v4.py` | `src/copromem/experiments/reme_copromem/config.py` | explicit local run/acquisition input configuration; no historical artifact lookup |
| `research/official_pilot/five_arm_runner.py` | `src/copromem/experiments/reme_copromem/runner.py` | canonical digest, journaling and common executor boundary |
| `research/official_pilot/upstream_executor.py` | `src/copromem/integrations/reme/upstream_executor.py` | reviewed native-worker path and environment configuration |
| `research/official_pilot/reme_bank.py` / `evaluation_lifecycle.py` | `src/copromem/integrations/reme/bank.py` / `lifecycle.py` | same maintained ReMe integration boundary |
| `src/copromem/appworld_comparison_adapter.py` | `src/copromem/benchmarks/appworld/adapter.py` | compatibility shim removed except for test-reachable public import |

## Required local environments

Keep AppWorld and pinned ReMe in separate environments. Configure `COPROMEM_RUN_DIR`, `COPROMEM_ACQUISITION_POOL`, `COPROMEM_REME_PYTHON`, `COPROMEM_REME_SOURCE`, `COPROMEM_APPWORLD_PYTHON`, `COPROMEM_APPWORLD_ROOT`, and `OPENROUTER_API_KEY` without committing values. The pinned review package declares `agentscope==1.0.20`, `flowllm[reme]==0.2.0.10`, and `ray==2.58.0` in its ReMe optional group.

## Zero-paid-call verification

```powershell
$env:PYTHONPATH = "$PWD\\src;$PWD"
python -m pytest -q tests\\appworld tests\\webarena tests\\reme_copromem
python research\\reme_copromem_fixed_dynamic_v4_results\\build_v4_results.py --evidence <local-run-dir> --output research\\reme_copromem_fixed_dynamic_v4_results
```

A future run uses `scripts/reme_copromem/launch_fixed_dynamic.sh` after placing a frozen manifest and frozen acquisition export under the ignored `COPROMEM_RUN_DIR`; do not run that command merely to regenerate this report.

Excluded by design: raw artifacts, task payloads, prompts, completions, memory text, journals, ledgers, logs, environments, caches, datasets, and credentials.
"""


def build(evidence: pathlib.Path, output: pathlib.Path, review_commit: str) -> dict[str, Any]:
    manifest, rows, evidence_data = load_evidence(evidence)
    aggregate = aggregates(rows)
    verify_display_reconciliation(aggregate)
    analysis = paired_analysis(rows)
    package = {"protocol": manifest.get("protocol"), "manifest_sha256": EXPECTED_MANIFEST,
               "final_report_sha256": EXPECTED_FINAL_REPORT, "experiment_code_commit": EXPERIMENT_COMMIT,
               "route": manifest.get("route"), "embedding": manifest.get("embedding"), "controls": manifest.get("controls"),
               "aggregate": aggregate, "trajectories": rows}
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "aggregate-results.json", package)
    write_json(output / "statistical-analysis.json", analysis)
    write_json(output / "evidence-checksums.json", evidence_data)
    (output / "README.md").write_text(readme(), encoding="utf-8")
    (output / "FINAL_REPORT.md").write_text(markdown(aggregate, analysis), encoding="utf-8")
    (output / "V4_CODE_WALKTHROUGH.md").write_text(walkthrough(), encoding="utf-8")
    (output / "V4_REPRODUCIBILITY_MAP.md").write_text(reproducibility_map(review_commit), encoding="utf-8")
    return {"aggregate": aggregate, "analysis": analysis, "evidence": evidence_data}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--review-commit", default="uncommitted-review-package")
    args = parser.parse_args()
    result = build(args.evidence, args.output, args.review_commit)
    print(json.dumps({"completed": sum(item["completed"] for item in result["aggregate"].values()),
                      "unresolved_ledger_entries": result["evidence"]["ledger"]["unresolved_count"]}, sort_keys=True))


if __name__ == "__main__":
    main()
