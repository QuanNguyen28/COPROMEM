"""Frozen descriptive analysis for the failure-informed exploratory pilot."""
from __future__ import annotations

import json
import random
import statistics
import argparse
from collections import defaultdict
from pathlib import Path

import sys
sys.path.insert(0, "src")
from copromem.checkpoints import RunStore, digest


ROOT = Path("artifacts/research/reme_copromem_comparison/openrouter_failure_informed_exploratory_pilot")
ARMS = ("no_memory", "reme_fixed", "reme_dynamic", "copromem_v2")
BOOTSTRAP_SEED = 20260926
BOOTSTRAP_REPLICATES = 2000


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    index = (len(ordered) - 1) * probability
    lower, upper = int(index), min(int(index) + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest-key", default="failure_informed_exploratory_v1")
    args = parser.parse_args()
    root = args.root
    store = RunStore(root)
    manifest = store.read("manifest", args.manifest_key)
    terminal = store.read("pilot_terminal", "complete")
    if manifest is None or terminal is None or terminal.get("status") != "exploratory_complete":
        raise RuntimeError("exploratory evaluation is not complete")
    rows = []
    for path in sorted((root / "evaluation_scores").glob("*.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        rows.append({"task_id": item["task_id"], "seed": item["seed"], "arm": item["arm"], "success": bool(item["official_score"]["success"])})
    expected = len(manifest["evaluation"]["task_ids"]) * len(manifest["evaluation"]["seeds"]) * len(ARMS)
    if len(rows) != expected:
        raise RuntimeError(f"incomplete evaluation rows: {len(rows)}/{expected}")
    keyed = {(row["task_id"], row["seed"], row["arm"]): row["success"] for row in rows}
    per_arm = {arm: {"n": sum(row["arm"] == arm for row in rows), "successes": sum(row["arm"] == arm and row["success"] for row in rows)} for arm in ARMS}
    for item in per_arm.values(): item["success_rate"] = item["successes"] / item["n"]
    rng = random.Random(BOOTSTRAP_SEED)
    tasks = list(manifest["evaluation"]["task_ids"])
    seeds = list(manifest["evaluation"]["seeds"])
    paired = {}
    for arm in ARMS[1:]:
        by_task = {task: statistics.mean(float(keyed[task, seed, arm]) - float(keyed[task, seed, "no_memory"]) for seed in seeds) for task in tasks}
        estimate = statistics.mean(by_task.values())
        draws = [statistics.mean(by_task[rng.choice(tasks)] for _ in tasks) for _ in range(BOOTSTRAP_REPLICATES)]
        paired[arm] = {"estimand": "mean paired official-success difference versus No Memory, clustered by task", "estimate": estimate, "clustered_bootstrap_95_ci": [percentile(draws, .025), percentile(draws, .975)], "task_cluster_count": len(tasks), "seed_count": len(seeds)}
    lifecycle = {arm: store.read("lifecycle_outputs", arm) for arm in ARMS[1:]}
    input_dir = root / "exploratory_memory_inputs"
    if not input_dir.is_dir():
        input_dir = root / "memory_inputs"
    inputs = [json.loads(path.read_text(encoding="utf-8")) for path in input_dir.glob("*.json")]
    memory_summary = {arm: {"n": sum(item["arm"] == arm for item in inputs), "empty": sum(item["arm"] == arm and item["empty"] for item in inputs), "nonempty": sum(item["arm"] == arm and not item["empty"] for item in inputs)} for arm in ARMS}
    report = {"label": "exploratory, failure-informed, exact-ID-held-out", "manifest_content_sha256": digest(manifest), "per_arm": per_arm, "paired": paired, "lifecycle_outputs": lifecycle, "memory_input_summary": memory_summary, "interpretation": "Descriptive only. The protocol was created after a 0/48 acquisition outcome and does not support confirmatory efficacy, superiority, or task-family generalization claims."}
    store.write("analysis", "exploratory_paired_analysis", report)
    print(json.dumps({"status": "analysis_complete", "report_sha256": digest(report)}))


if __name__ == "__main__":
    main()
