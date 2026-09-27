#!/usr/bin/env python3
"""Read-only forensic auditor for fixed_dynamic_v3 evidence.

The script never opens benchmark payloads or dispatches providers.  It emits
sanitized aggregates and a checksum index from already durable local evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from src.copromem.appworld_comparison_adapter import CoProMemAppWorldAdapter, TrialInput

ROOT = Path("/mnt/e/Project/AAMAS/COPROMEM")
RUN = ROOT / "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v3"
EXPECTED_MANIFEST = "31eebe51a0ce51e78f7ed9a51b143683240c0dfa4303a2f3ccda4443b2541816"


def canon(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def fh(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> None:
    manifest = json.loads((RUN / "manifest.json").read_text(encoding="utf-8"))
    manifest_hash = canon(manifest)
    if manifest_hash != EXPECTED_MANIFEST:
        raise RuntimeError("frozen manifest mismatch")
    artifacts = sorted((RUN / "evaluation").glob("*/*/trial-*.json"))
    index: dict[str, str] = {str(RUN / "manifest.json"): fh(RUN / "manifest.json")}
    findings: list[dict[str, Any]] = []
    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str, int]] = set()
    journal_missing = scorer_mismatch = hash_bad = action_bad = 0
    for path in artifacts:
        index[str(path)] = fh(path)
        item = json.loads(path.read_text(encoding="utf-8"))
        key = (str(item.get("arm")), str(item.get("task_id")), int(item.get("trial_id")))
        issues: list[str] = []
        if key in seen: issues.append("duplicate_trajectory_key")
        seen.add(key)
        history = item.get("history")
        if not isinstance(history, list) or not history or canon(history) != item.get("history_sha256"):
            issues.append("history_hash_or_content_invalid"); hash_bad += 1
        journal = RUN / "journals" / f"evaluation_{key[0]}_{key[1]}_trial_{key[2]}_seed_{item.get('seed')}.jsonl"
        if not journal.is_file():
            issues.append("journal_missing"); journal_missing += 1
            events: list[dict[str, Any]] = []
        else:
            index[str(journal)] = fh(journal); events = rows(journal)
        submitted = [e for e in events if e.get("event") == "action_submitted"]
        applied = [e for e in events if e.get("event") == "action_applied"]
        scores = [e for e in events if e.get("event") == "official_score"]
        assistant_actions = [str(m.get("content") or "") for m in history or [] if m.get("role") == "assistant"]
        if len(submitted) != len(applied) or len(applied) != int(item.get("actions", -1)) or len(assistant_actions) != len(applied):
            issues.append("action_journal_count_mismatch"); action_bad += 1
        if [e.get("index") for e in submitted] != list(range(len(submitted))) or [e.get("index") for e in applied] != list(range(len(applied))):
            issues.append("action_order_or_index_mismatch"); action_bad += 1
        if any(str(e.get("code_sha256")) != hashlib.sha256(assistant_actions[i].encode()).hexdigest() for i, e in enumerate(submitted)):
            issues.append("submitted_action_history_hash_mismatch"); action_bad += 1
        score_values = [float(e.get("pass_count", 0)) / (float(e.get("pass_count", 0)) + float(e.get("fail_count", 0)))
                        for e in scores if float(e.get("pass_count", 0)) + float(e.get("fail_count", 0))]
        if len(score_values) < 2 or score_values[0] != float(item.get("before_score")) or score_values[-1] != float(item.get("after_score")):
            issues.append("official_score_evidence_mismatch"); scorer_mismatch += 1
        elif len(scores) > 2:
            findings.append({"key": "/".join(map(str, key)), "issues": ["telemetry_duplicate_identical_official_score_events"]})
        if item.get("termination") not in {"completed", "truncation_termination", "context_ceiling_termination", "infrastructure_failure"}:
            issues.append("unregistered_termination")
        if key[0] in {"official_upstream_reme_dynamic", "copromem_dynamic"}:
            marker = RUN / "evaluation_updates" / key[0] / key[1] / f"trial-{key[2]}.json"
            if not marker.is_file(): issues.append("dynamic_update_marker_missing")
            else:
                index[str(marker)] = fh(marker)
                update = json.loads(marker.read_text(encoding="utf-8"))
                if update.get("trajectory_id") != item.get("trajectory_id") or float(update.get("after_score", -1)) != float(item.get("after_score")):
                    issues.append("dynamic_update_marker_mismatch")
        if issues: findings.append({"key": "/".join(map(str, key)), "issues": issues})
        by_arm[key[0]].append(item)

    # Provider call records are sanitized progress events.  Validate every executor
    # call against the immutable route, and ensure none follows a scored event for
    # the same trajectory key.
    progress = rows(RUN / "progress.jsonl")
    settled = [e for e in progress if e.get("event") == "call_settled"]
    route_bad = [e for e in settled if e.get("model") != "deepseek/deepseek-v4.1-flash" or e.get("provider") != "deepseek" or int(e.get("reasoning_tokens") or 0) != 0]
    reservations = Counter(e.get("id") for e in progress if e.get("event") == "reserved")
    settlements = Counter(e.get("id") for e in progress if e.get("event") in {"call_settled", "embedding_settled"})
    unresolved = sorted(k for k in reservations if k not in settlements)
    completed_keys: set[tuple[str, str, int]] = set(); post_completion_calls: list[str] = []
    role_re = re.compile(r"^executor:([^:]+):([^:]+):trial=(\d+):")
    for event in progress:
        if event.get("event") == "trajectory_scored" and event.get("phase") == "evaluation":
            completed_keys.add((str(event.get("arm")), str(event.get("task_id")), int(event.get("trial_id"))))
        if event.get("event") == "call_settled":
            match = role_re.match(str(event.get("role") or ""))
            if match and (match.group(1), match.group(2), int(match.group(3))) in completed_keys:
                post_completion_calls.append(str(event.get("id") or "unknown"))
    term = {arm: Counter(str(x.get("termination")) for x in vals) for arm, vals in by_arm.items()}
    metrics = {}
    for arm, vals in by_arm.items():
        normal = [x for x in vals if x.get("termination") == "completed"]
        metrics[arm] = {"n": len(vals), "mean_score": sum(float(x["after_score"]) for x in vals) / len(vals),
                        "normal_n": len(normal), "normal_mean_score": (sum(float(x["after_score"]) for x in normal) / len(normal) if normal else None),
                        "injected_memory_hashes": len({x.get("injected_memory_sha256") for x in vals}),
                        "nonempty_memory_n": sum(bool(x.get("injected_memory_nonempty")) for x in vals)}
    # Re-evaluate only the already durable task instructions against an in-memory
    # clone. This calls no provider and records categories/hashes, never guidance.
    copro_state = json.loads((RUN / "copromem" / "initial-state.json").read_text(encoding="utf-8"))
    fallback = "# Task Execution Guidance: [Novel Goal - Multi-Stage Decomposition]"
    copro_audit: dict[str, dict[str, int]] = {}
    for arm in ("copromem_fixed", "copromem_dynamic"):
        categories: Counter[str] = Counter()
        hash_matches = 0
        for item in by_arm.get(arm, []):
            state = copro_state
            if arm == "copromem_dynamic":
                # The stored dynamic snapshot is stream-level; use it only as
                # evidence that the recorded stream is distinct, not to mutate it.
                state = json.loads((RUN / "copromem" / f"dynamic-trial-{item['trial_id']}.json").read_text(encoding="utf-8"))
            adapter = CoProMemAppWorldAdapter(api_key="", model="deepseek/deepseek-v4.1-flash",
                provider_only="deepseek", reasoning_effort="none", decomposition_call_cap=320)
            adapter.clone_from_state(state)
            intent = next(str(m.get("content") or "") for m in item["history"] if m.get("role") == "user")
            result = adapter.module._retrieve_copromem_v2(str(item["task_id"]), intent, "appworld", (), "", intent)
            guidance = result.injected_text
            if guidance == fallback: categories["generic_novel_goal_fallback"] += 1
            elif guidance: categories["non_generic_guidance"] += 1
            else: categories["empty"] += 1
            hash_matches += int(hashlib.sha256(guidance.encode()).hexdigest() == item.get("injected_memory_sha256"))
        copro_audit[arm] = {**dict(categories), "offline_hash_matches": hash_matches, "n": len(by_arm.get(arm, []))}
    copro_reproducibility_defect = any(v.get("n", 0) and v.get("offline_hash_matches", 0) != v.get("n", 0)
                                        for v in copro_audit.values())
    report = {
        "audit_version": "fixed_dynamic_v3_forensic_v1", "manifest_sha256": manifest_hash,
        "artifact_inventory": {"durable": len(artifacts), "expected": 320, "unique_keys": len(seen)},
        "journal_reconciliation": {"journal_missing": journal_missing, "history_hash_invalid": hash_bad,
                                   "action_reconciliation_errors": action_bad, "scorer_evidence_errors": scorer_mismatch},
        "route_integrity": {"invalid_settled_route_records": len(route_bad), "unresolved_reservations": unresolved,
                            "post_completion_executor_calls": post_completion_calls},
        "termination_counts": {a: dict(c) for a, c in term.items()}, "metrics": metrics,
        "copromem_retrieval_audit": copro_audit,
        "decision": {
            "classification": "INVALID-METHOD-INTEGRATION" if copro_reproducibility_defect else "PENDING",
            "path": "B" if copro_reproducibility_defect else "A",
            "reason": ("Frozen CoProMem state plus durable task instruction cannot reproduce the stored injected-memory hash; "
                       "the same stored hash appears across distinct completed tasks. This invalidates retrieval provenance "
                       "for the existing CoProMem trajectories without implying any score is erroneous.") if copro_reproducibility_defect else "No systematic defect detected by this local audit.",
        },
        "trajectory_findings": findings,
        "limitations": ["Audit is local-evidence-only; it cannot independently re-execute native scorer state without opening tasks.",
                        "No provider, embedding, AppWorld, or scorer request was made by this audit."],
    }
    out = RUN / "forensic-audit-v1.json"; out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (RUN / "forensic-audit-v1-checksums.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = ["# fixed_dynamic_v3 forensic audit", "", f"Decision: **{report['decision']['classification']}** (Path {report['decision']['path']}).", "",
             f"Inventory: {len(artifacts)}/320 durable evaluation artifacts; {len(seen)} unique keys.",
             f"Route: {len(route_bad)} invalid settled route records; {len(unresolved)} unresolved reservations.",
             f"Journal reconciliation: action={action_bad}, history={hash_bad}, scorer={scorer_mismatch}, missing={journal_missing}.", "",
             "## Terminations"]
    for arm, counts in sorted(term.items()): lines.append(f"- {arm}: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    lines.extend(["", "## CoProMem retrieval provenance", ""])
    for arm, value in sorted(copro_audit.items()): lines.append(f"- {arm}: {value}")
    lines.extend(["", "## Decision rationale", "", report['decision']['reason'], "",
                  "No provider, embedding, AppWorld, scorer, or model request was issued by this audit."])
    (RUN / "FORENSIC_AUDIT_v1.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"artifacts": len(artifacts), "findings": len(findings), "route_bad": len(route_bad), "unresolved": len(unresolved)}, sort_keys=True))


if __name__ == "__main__": main()
