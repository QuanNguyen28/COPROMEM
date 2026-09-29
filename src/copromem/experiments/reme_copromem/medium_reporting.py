"""Sanitized task-level reporting for the v6.2 medium exploratory run."""
from __future__ import annotations

import hashlib
import json
import math
import pathlib
import random
from collections import defaultdict
from typing import Any, Iterable, Mapping


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _mean(items: Iterable[float]) -> float:
    values = list(items)
    return sum(values) / len(values) if values else 0.0


def _bootstrap(values: list[float], *, seed_material: str, draws: int = 4000) -> Mapping[str, float | int]:
    if not values:
        return {"n": 0, "mean": 0.0, "ci95_low": 0.0, "ci95_high": 0.0}
    rng = random.Random(int(_digest({"seed": seed_material, "values": values})[:16], 16))
    sampled = sorted(_mean(rng.choice(values) for _ in values) for _ in range(draws))
    return {"n": len(values), "mean": _mean(values),
            "ci95_low": sampled[int(0.025 * (draws - 1))],
            "ci95_high": sampled[int(0.975 * (draws - 1))]}


def build_report(*, artifact_root: pathlib.Path, manifest: Mapping[str, Any], live_summary: Mapping[str, Any]) -> Mapping[str, Any]:
    arms, tasks, seeds = list(manifest["arms"]), list(manifest["evaluation"]["task_ids"]), list(manifest["evaluation"]["seeds"])
    rows: list[dict[str, Any]] = []
    for task in tasks:
        for arm in arms:
            for trial, seed in enumerate(seeds, 1):
                path = artifact_root / task / arm / f"trial-{trial}.json"
                if not path.is_file():
                    raise RuntimeError("medium report requires every frozen scored artifact")
                value = json.loads(path.read_text(encoding="utf-8"))
                rows.append({"task_id": task, "arm": arm, "trial": trial, "seed": seed,
                             "score": float(value["after_score"]), "actions": int(value["actions"]),
                             "termination": str(value.get("termination", "")),
                             "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    per_arm: dict[str, Any] = {}
    task_arm: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows: task_arm[(row["task_id"], row["arm"])].append(row)
    for arm in arms:
        task_means = [_mean(item["score"] for item in task_arm[(task, arm)]) for task in tasks]
        pass_at_2 = [float(any(item["score"] == 1.0 for item in task_arm[(task, arm)])) for task in tasks]
        per_arm[arm] = {"AvgAt2": _bootstrap(task_means, seed_material=f"{manifest['protocol']}:{arm}:avg"),
                        "PassAt2": _bootstrap(pass_at_2, seed_material=f"{manifest['protocol']}:{arm}:pass"),
                        "AvgActions": _mean(row["actions"] for row in rows if row["arm"] == arm),
                        "trajectory_count": sum(row["arm"] == arm for row in rows)}
    primary = "copromem_v6_2_dynamic"
    comparisons: dict[str, Any] = {}
    for other in arms:
        if other == primary: continue
        deltas = [_mean(item["score"] for item in task_arm[(task, primary)]) -
                  _mean(item["score"] for item in task_arm[(task, other)]) for task in tasks]
        comparisons[f"{primary}_minus_{other}"] = {**_bootstrap(deltas, seed_material=f"{manifest['protocol']}:{other}"),
            "wins": sum(value > 0 for value in deltas), "losses": sum(value < 0 for value in deltas),
            "ties": sum(value == 0 for value in deltas), "unit": "task-level mean over two ordered stochastic trials"}
    return {"version": "v6.2-medium-exploratory-report-v1", "manifest_sha256": _digest(manifest),
            "exploratory_compatibility_conditioned_only": True, "expected_trajectories": len(tasks) * len(seeds) * len(arms),
            "rows": rows, "per_arm": per_arm, "paired_task_level_comparisons": comparisons,
            "ledger_summary": dict(live_summary),
            "limitations": ["test_normal allocation is compatibility-conditioned, not an unbiased benchmark sample",
                            "ReMe Dynamic trials are sequential online observations, not independent replicates",
                            "this exploratory diagnostic run cannot establish superiority or generalization"]}


def write_report(run: pathlib.Path, report: Mapping[str, Any]) -> None:
    destination = run / "final-report.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    lines = ["# v6.2 medium held-out exploratory report", "",
             "Compatibility-conditioned exploratory sampling; not a confirmatory efficacy or superiority result.", "",
             "| Arm | Avg@2 | Pass@2 |", "|---|---:|---:|"]
    for arm, metrics in report["per_arm"].items():
        lines.append(f"| {arm} | {metrics['AvgAt2']['mean']:.3f} | {metrics['PassAt2']['mean']:.3f} |")
    (run / "FINAL_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

