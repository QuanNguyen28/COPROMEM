#!/usr/bin/env python3
"""Freeze the fresh, public-metadata-only v5.3 execution-evidence pair.

This program deliberately enumerates only public development descriptors.  It
does not create an AppWorld task, load a task payload, or contact a provider.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import pathlib
import re
from typing import Any

from copromem.benchmarks.appworld.adapter import CoProMemAppWorldAdapter
from copromem.experiments.reme_copromem.public_tool_schema_registry import canonical_digest, tool_operation_index, verify_public_tool_schema_registry
from copromem.experiments.reme_copromem.runner import AppendOnlyLedger, construct_copromem, raw_acquisition_trajectories, v5_budget_bound, write_json
from copromem.learning import ActionObservation
from scripts.reme_copromem.prepare_tool_schema_v53 import (
    ACQUISITION_RELATIVE_PATH, FUNCTION_ROOT, INVENTORY_RELATIVE_PATH,
    OPENAPI_ROOT, REGISTRY_RELATIVE_PATH, ROOT, _candidate_paths, _descriptor,
    historical_settled_usd, sha, source_commit,
)


TASK_ID = re.compile(r"\b[a-f0-9]{7}_[0-9]+\b")
EVIDENCE_RELATIVE_PATH = "src/copromem/benchmarks/appworld/execution_evidence.py"


def all_prior_task_ids() -> set[str]:
    """Conservatively collect IDs from every durable record, without parsing tasks."""
    result: set[str] = set()
    roots = [ROOT / "artifacts", ROOT / "research"]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl", ".md", ".txt", ".log"}:
                continue
            try:
                # IDs are public opaque labels; no parsed task payload or action
                # history is retained by this inventory operation.
                result.update(TASK_ID.findall(path.read_text(encoding="utf-8", errors="ignore")))
            except OSError:
                continue
    return result


def select_pair(registry: dict[str, Any], inventory: dict[str, Any], excluded: set[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    fresh = {str(row["task_id"]): row for row in inventory["tasks"] if str(row["task_id"]) not in excluded}
    per_task = {task_id: _candidate_paths(registry, str(row["instruction"])) for task_id, row in fresh.items()}
    index = tool_operation_index(registry)
    candidates: list[dict[str, Any]] = []
    for left, right in itertools.combinations(sorted(per_task), 2):
        if left.rsplit("_", 1)[0] != right.rsplit("_", 1)[0]:
            continue
        for path in sorted(set(per_task[left]) & set(per_task[right])):
            descriptor = _descriptor(index, path)
            candidates.append({"a_task_id": left, "b_task_id": right, "family": left.rsplit("_", 1)[0],
                               "operations": list(path), "descriptor": descriptor,
                               "descriptor_sha256": canonical_digest(descriptor),
                               "a_public_instruction_sha256": hashlib.sha256(str(fresh[left]["instruction"]).encode("utf-8")).hexdigest(),
                               "b_public_instruction_sha256": hashlib.sha256(str(fresh[right]["instruction"]).encode("utf-8")).hexdigest()})
    candidates.sort(key=lambda row: (row["descriptor_sha256"], row["a_task_id"], row["b_task_id"]))
    if not candidates:
        raise RuntimeError("no fresh sibling development pair has a complete registry-supported public path")
    return candidates[0], candidates


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--run", type=pathlib.Path, required=True); args = parser.parse_args()
    if args.run.exists() and any(args.run.iterdir()):
        raise RuntimeError("013 run directory already exists")
    registry_path = ROOT / REGISTRY_RELATIVE_PATH
    registry = json.loads(registry_path.read_text(encoding="utf-8")); verify_public_tool_schema_registry(registry)
    inventory_path = ROOT / INVENTORY_RELATIVE_PATH
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    excluded = all_prior_task_ids()
    selected, candidates = select_pair(registry, inventory, excluded)
    acquisition_path = ROOT / ACQUISITION_RELATIVE_PATH
    acquisition = json.loads(acquisition_path.read_text(encoding="utf-8")); acquisition = acquisition.get("trajectories", acquisition)
    pair = [selected["a_task_id"], selected["b_task_id"]]
    if len(acquisition) != 32 or set(pair) & {str(row["task_id"]) for row in acquisition}:
        raise RuntimeError("frozen acquisition export is not disjoint from selected evaluation pair")
    args.run.mkdir(parents=True, exist_ok=False)
    limits = {"executor": 240, "reme_lifecycle": 0, "reme_embedding": 0, "copromem_decomposition": 0}
    ledger = AppendOnlyLedger(args.run / "ledger.jsonl", 100.0, limits)
    state, _ = construct_copromem(run=args.run, progress=args.run / "progress.jsonl", ledger=ledger,
                                  api_key="", raw=raw_acquisition_trajectories(acquisition), call_cap=0)
    bank = CoProMemAppWorldAdapter(api_key=""); bank.clone_from_state(state)
    events = tuple(ActionObservation(**item) for item in selected["descriptor"])
    initial = {task_id: bank.module.learning.retrieve("appworld", events).compatibility for task_id in pair}
    if set(initial.values()) != {"unknown"}:
        raise RuntimeError("fresh pair is not initially unknown under the immutable warm-start bank")
    budget = v5_budget_bound(call_limits=limits, historical_usd=historical_settled_usd())
    budget.update({"call_limits": limits, "hard_cap_usd": 100.0, "fits_hard_cap": budget["all_in_usd"] <= 100.0,
                   "ledger_dispatch_cap_usd": budget["dispatchable_usd"]})
    evidence_path = ROOT / EVIDENCE_RELATIVE_PATH
    manifest = {
        "protocol": "v5_3_engineering_013_execution_evidence", "engineering_only_exposed": True,
        "method_amendment": "public_execution_evidence_v1", "git_commit": source_commit(),
        "acquisition": {"source_export": str(acquisition_path.resolve()), "export_sha256": sha(acquisition_path),
                        "expected_trajectories": 32, "fresh_state_required": True},
        "arms": ["no_memory", "copromem_dynamic"],
        "execution": {"max_actions": 30, "temperature": 0.7, "top_p": 1.0, "c_floor_gib": 10.0,
                      "model": "deepseek/deepseek-v4.1-flash", "provider": "deepseek", "fallbacks": False,
                      "reasoning_effort": "none", "stream": False, "completion_token_ceiling": 2048},
        "evaluation": {"split": "dev", "task_ids": pair, "a_task_id": pair[0], "b_task_id": pair[1],
                       "trial_ids": [1, 2], "seeds": [8301, 8302], "expected_trajectories": 8,
                       "descriptors": {pair[0]: selected["descriptor"], pair[1]: selected["descriptor"]},
                       "descriptor_sha256": selected["descriptor_sha256"], "initial_compatibility": initial,
                       "public_instruction_sha256": {pair[0]: selected["a_public_instruction_sha256"], pair[1]: selected["b_public_instruction_sha256"]},
                       "public_registry_relative_path": REGISTRY_RELATIVE_PATH, "public_registry_file_sha256": sha(registry_path),
                       "public_registry_sha256": registry["registry_sha256"],
                       "runtime_public_schema": {"openapi_root": OPENAPI_ROOT, "function_calling_root": FUNCTION_ROOT},
                       "execution_evidence": {"version": "public-execution-evidence-v1", "registry_relative_path": REGISTRY_RELATIVE_PATH,
                                              "registry_sha256": registry["registry_sha256"], "implementation_relative_path": EVIDENCE_RELATIVE_PATH,
                                              "implementation_sha256": sha(evidence_path)}},
        "budget": budget,
        "selection": {"public_only": True, "test_normal_excluded": True, "development_only": True,
                      "ordering_rule": "(descriptor_sha256, a_task_id, b_task_id)", "inventory_sha256": sha(inventory_path),
                      "exclusion_set_sha256": canonical_digest(sorted(excluded)), "exclusion_count": len(excluded),
                      "candidate_list_sha256": canonical_digest(candidates), "candidate_count": len(candidates),
                      "selected_descriptor_sha256": selected["descriptor_sha256"]},
        "task_boundary_policy": "observable_tool_schema_execution_evidence_v1",
    }
    write_json(args.run / "template.json", manifest)
    write_json(args.run / "descriptor-audit.json", {"provider_calls": 0, "test_normal_used": False,
        "exclusion_set_sha256": manifest["selection"]["exclusion_set_sha256"], "candidate_list_sha256": manifest["selection"]["candidate_list_sha256"],
        "ordering_rule": manifest["selection"]["ordering_rule"], "selected": {key: selected[key] for key in ("a_task_id", "b_task_id", "family", "descriptor_sha256", "operations")},
        "registry_sha256": registry["registry_sha256"], "telemetry_implementation_sha256": sha(evidence_path), "initial_compatibility": initial})
    print(json.dumps({"a": pair[0], "b": pair[1], "all_in_usd": budget["all_in_usd"], "candidate_count": len(candidates)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
