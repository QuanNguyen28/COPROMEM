"""Sanitized report generation for a completed frozen five-arm run."""
from __future__ import annotations

import hashlib
import json
import pathlib
from collections import defaultdict
from typing import Any


def _write(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def build_report(run: pathlib.Path) -> pathlib.Path:
    """Build aggregate reports without copying raw histories into Git.

    The report refuses partial result sets; callers retain raw evidence only in
    the local, ignored run directory.
    """
    manifest_path = run / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if manifest_hash != (run / "manifest.sha256").read_text(encoding="utf-8").strip():
        raise RuntimeError("manifest hash mismatch")
    arms, tasks, trials = list(manifest["arms"]), list(manifest["evaluation"]["task_ids"]), list(manifest["evaluation"]["trial_ids"])
    wanted = {(arm, task, trial) for arm in arms for task in tasks for trial in trials}
    rows: list[dict[str, Any]] = []
    for path in (run / "evaluation").glob("*/*/trial-*.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        key = (item.get("arm"), item.get("task_id"), item.get("trial_id"))
        if key not in wanted:
            raise RuntimeError("unregistered evaluation artifact")
        rows.append({"arm": key[0], "task_id": key[1], "trial_id": key[2],
                     "official_score": float(item["after_score"]), "actions": int(item["actions"]),
                     "termination": item.get("termination"),
                     "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    if {(row["arm"], row["task_id"], row["trial_id"]) for row in rows} != wanted:
        raise RuntimeError(f"incomplete evaluation: {len(rows)}/{len(wanted)}")
    lookup = {(row["arm"], row["task_id"], row["trial_id"]): row["official_score"] for row in rows}
    metrics: dict[str, dict[str, float | int]] = {}
    for arm in arms:
        selected = [row for row in rows if row["arm"] == arm]
        per_task = [[lookup[(arm, task, trial)] for trial in trials] for task in tasks]
        metrics[arm] = {"trajectory_denominator": len(selected), "task_denominator": len(tasks),
                        "avg_at_k": sum(sum(scores) / len(scores) for scores in per_task) / len(per_task),
                        "pass_at_k": sum(any(score == 1.0 for score in scores) for scores in per_task) / len(per_task),
                        "mean_actions": sum(row["actions"] for row in selected) / len(selected)}
    terminations: dict[str, int] = defaultdict(int)
    for row in rows:
        terminations[str(row["termination"])] += 1
    report = {"protocol": manifest["protocol"], "manifest_sha256": manifest_hash,
              "completion": {"evaluation": f"{len(rows)}/{len(wanted)}", "complete": True},
              "metrics": metrics, "termination_counts": dict(terminations), "official_scores": rows,
              "limitations": ["Reports aggregate only; raw task histories remain local and ignored.",
                              "ReMe integration is a faithful adaptation unless direct upstream parity is separately verified."]}
    json_path = run / "final-report.json"
    _write(json_path, json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    lines = ["# Frozen five-arm run report", "", f"Manifest SHA-256: `{manifest_hash}`", "",
             "| Arm | Avg@k | Pass@k | mean actions |", "|---|---:|---:|---:|"]
    for arm in arms:
        metric = metrics[arm]
        lines.append(f"| {arm} | {metric['avg_at_k']:.4f} | {metric['pass_at_k']:.4f} | {metric['mean_actions']:.2f} |")
    lines += ["", "## Limitations", ""] + [f"- {item}" for item in report["limitations"]]
    _write(run / "FINAL_REPORT.md", "\n".join(lines) + "\n")
    return json_path
