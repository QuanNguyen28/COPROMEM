"""Sanitized report generation for a continuous four-arm run."""
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
    observed = {(row["arm"], row["task_id"], row["trial_id"]) for row in rows}
    if observed != wanted or len(rows) != len(wanted):
        raise RuntimeError(f"incomplete evaluation: {len(rows)}/{len(wanted)}")
    learning_timeline = []
    for task_id in tasks:
        path = run / "copromem/task_updates" / f"{task_id}.json"
        if not path.exists():
            raise RuntimeError(f"missing CoProMem task-boundary update for {task_id}")
        marker = json.loads(path.read_text(encoding="utf-8"))
        if marker.get("task_id") != task_id or not marker.get("pending_update_sha256"):
            raise RuntimeError("CoProMem task update identity mismatch")
        learning_timeline.append(marker)
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
    retrieval: dict[str, dict[str, int]] = {}
    retrieval_outcomes: dict[str, dict[str, dict[str, float | int]]] = {}
    for arm in ("copromem_dynamic",):
        records = list((run / "retrieval" / arm).glob("*/trial-*.json"))
        if len(records) != len(tasks) * len(trials):
            raise RuntimeError(f"incomplete {arm} retrieval provenance")
        counts = {"total": len(records), "learned": 0, "fallback": 0, "veto": 0}
        outcomes = {"learned": {"count": 0, "score_sum": 0.0, "successes": 0},
                    "fallback": {"count": 0, "score_sum": 0.0, "successes": 0}}
        seen = set()
        for path in records:
            record = json.loads(path.read_text(encoding="utf-8"))
            task_id, trial_id = record["task_id"], record["trial"]
            if (record.get("arm") != arm or task_id not in tasks or trial_id not in trials
                    or (task_id, trial_id) in seen):
                raise RuntimeError("retrieval record has an unregistered or duplicate identity")
            seen.add((task_id, trial_id))
            provenance = record["provenance"]
            if provenance.get("version") != "copromem_retrieval_provenance_v5":
                raise RuntimeError("legacy retrieval provenance cannot enter v5 report")
            if provenance["task_input"]["task_id"] != task_id:
                raise RuntimeError("retrieval provenance task identity mismatch")
            category = "learned" if provenance.get("selected_schema_id") else "fallback"
            counts[category] += 1
            counts["veto"] += bool(provenance.get("should_veto"))
            score = lookup[(arm, task_id, trial_id)]
            outcomes[category]["count"] += 1
            outcomes[category]["score_sum"] += score
            outcomes[category]["successes"] += score == 1.0
        retrieval[arm] = counts
        retrieval_outcomes[arm] = outcomes
    usage: dict[str, dict[str, float | int]] = defaultdict(lambda: {
        "calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0, "latency_seconds": 0.0})
    progress = run / "progress.jsonl"
    if progress.exists():
        for line in progress.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event.get("event") not in {"call_settled", "embedding_settled"}:
                continue
            role = str(event.get("role", ""))
            if role.startswith("executor:"):
                owner = role.split(":", 2)[1]
            elif role.startswith("copromem_decomposition:"):
                owner = role.split(":", 2)[1]
            elif role.endswith(":reme-fixed"):
                owner = "official_upstream_reme_fixed"
            elif ":reme-dynamic-" in role:
                owner = "official_upstream_reme_dynamic"
            else:
                owner = "acquisition_or_unattributed"
            item = usage[owner]
            item["calls"] += 1
            item["prompt_tokens"] += int(event.get("prompt_tokens") or event.get("input_tokens") or 0)
            item["completion_tokens"] += int(event.get("completion_tokens") or 0)
            item["cost_usd"] += float(event.get("cost") or 0)
            item["latency_seconds"] += float(event.get("latency") or 0)
    report = {"protocol": manifest["protocol"], "manifest_sha256": manifest_hash,
              "completion": {"evaluation": f"{len(rows)}/{len(wanted)}", "complete": True},
              "metrics": metrics, "termination_counts": dict(terminations), "retrieval": retrieval,
              "retrieval_outcomes_diagnostic_only": retrieval_outcomes,
              "copromem_learning_timeline": learning_timeline,
              "calls_tokens_latency_cost": dict(usage),
              "official_scores": rows,
              "limitations": ["CoProMem scores are measured before the same task updates memory; this is an online learning curve.",
                              "Reports aggregate only; raw task histories remain local and ignored.",
                              "The procedural memory guidance is soft; no AppWorld milestone verifier is executed.",
                              "ReMe integration is a faithful adaptation unless direct upstream parity is separately verified."]}
    json_path = run / "final-report.json"
    _write(json_path, json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    lines = ["# Continuous four-arm run report", "", f"Manifest SHA-256: `{manifest_hash}`", "",
             "| Arm | Avg@k | Pass@k | mean actions |", "|---|---:|---:|---:|"]
    for arm in arms:
        metric = metrics[arm]
        lines.append(f"| {arm} | {metric['avg_at_k']:.4f} | {metric['pass_at_k']:.4f} | {metric['mean_actions']:.2f} |")
    lines += ["", "## CoProMem retrieval provenance", "", "| Arm | Retrieved | Learned | Fallback | Veto |", "|---|---:|---:|---:|---:|"]
    for arm, counts in retrieval.items():
        lines.append(f"| {arm} | {counts['total']} | {counts['learned']} | {counts['fallback']} | {counts['veto']} |")
    lines += ["", "Selected-schema outcomes below are diagnostic only; the primary denominator is all registered task/trial pairs.",
              "", "| Arm | Guidance | n | Mean official score | Full successes |", "|---|---|---:|---:|---:|"]
    for arm, buckets in retrieval_outcomes.items():
        for category, item in buckets.items():
            mean = item["score_sum"] / item["count"] if item["count"] else 0.0
            lines.append(f"| {arm} | {category} | {item['count']} | {mean:.4f} | {item['successes']} |")
    lines += ["", "## Settled usage", "", "| Owner | Calls | Input tokens | Output tokens | USD |", "|---|---:|---:|---:|---:|"]
    for owner, item in sorted(usage.items()):
        lines.append(f"| {owner} | {item['calls']} | {item['prompt_tokens']} | {item['completion_tokens']} | {item['cost_usd']:.6f} |")
    lines += ["", "## Limitations", ""] + [f"- {item}" for item in report["limitations"]]
    _write(run / "FINAL_REPORT.md", "\n".join(lines) + "\n")
    return json_path
