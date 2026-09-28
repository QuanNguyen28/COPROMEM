#!/usr/bin/env python3
"""Prepare v5.3's one fresh public-metadata-selected engineering pair.

This script never opens an AppWorld task payload.  It derives one candidate
read/write path from the frozen callable registry and public development
instruction metadata, then freezes only hashes and public structural names.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import pathlib
import re
import subprocess
from typing import Any

from copromem.benchmarks.appworld.adapter import CoProMemAppWorldAdapter
from copromem.experiments.reme_copromem.public_tool_schema_registry import (
    canonical_digest, public_tool_path_audit, tool_operation_index, verify_public_tool_schema_registry,
)
from copromem.experiments.reme_copromem.runner import (
    AppendOnlyLedger, construct_copromem, digest, raw_acquisition_trajectories, v5_budget_bound, write_json,
)
from copromem.learning import ActionObservation


ROOT = pathlib.Path(__file__).resolve().parents[2]
REGISTRY_RELATIVE_PATH = "research/reme_copromem_fixed_dynamic_review/appworld_public_tool_schema_registry_v5_3.json"
ACQUISITION_RELATIVE_PATH = "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v5_engineering_001/acquisition/scored-train-acquisition.json"
INVENTORY_RELATIVE_PATH = "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v5_engineering_001/public-dev-descriptors.json"
OPENAPI_ROOT = "/home/xiqhq/copromem-appworld/data/api_docs/openapi"
FUNCTION_ROOT = "/home/xiqhq/copromem-appworld/data/api_docs/function_calling"


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(key, None)
    pointer = ROOT / ".git"
    if pointer.is_file():
        match = re.match(r"gitdir:\s*([A-Za-z]):/(.+)", pointer.read_text(encoding="utf-8").strip())
        if match:
            env["GIT_DIR"] = f"/mnt/{match.group(1).lower()}/{match.group(2)}"
            env["GIT_WORK_TREE"] = str(ROOT)
    return env


def source_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, env=_git_env()).strip()


def prior_ids() -> set[str]:
    """Conservatively exclude every ID named in a prior manifest or artifact."""
    result: set[str] = set()
    for path in (ROOT / "artifacts/research/official_reme_copromem_pilot").glob("**/manifest.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for section in ("acquisition", "evaluation"):
            result.update(str(item) for item in value.get(section, {}).get("task_ids", ()) if item)
    for path in (ROOT / "artifacts/research/official_reme_copromem_pilot").glob("**/evaluation/**/trial-*.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8")); task_id = value.get("task_id")
        except (OSError, json.JSONDecodeError):
            continue
        if task_id: result.add(str(task_id))
    return result


def historical_settled_usd() -> float:
    total = 0.0
    for path in (ROOT / "artifacts/research/official_reme_copromem_pilot").glob("**/ledger.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            value = json.loads(line)
            if value.get("event") == "settle": total += float(value["usd"])
    return total


def _tokens(text: str) -> set[str]:
    result = set()
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        # Deterministic morphology is a public-instruction *selection* aid,
        # not an operation alias and never enters the frozen registry.
        if token.endswith("ies") and len(token) > 3: token = token[:-3] + "y"
        elif token.endswith("s") and len(token) > 3: token = token[:-1]
        result.add(token)
    return result


def _operation_words(meta: dict[str, Any]) -> set[str]:
    # Callable names are public metadata.  The app prefix avoids treating a
    # generic verb alone as task compatibility.
    return _tokens(meta["function_name"]) - {"api", meta["app"], "show", "get", "list", "search"}


def _descriptor(index: dict[str, dict[str, Any]], operations: tuple[str, ...]) -> list[dict[str, Any]]:
    rows = []
    for operation in operations:
        meta = index[operation]
        rows.append({"operation": operation, "input_slots": meta["required_parameters"], "output_slots": meta["output_slots"]})
    return rows


def _candidate_paths(registry: dict[str, Any], instruction: str) -> list[tuple[str, ...]]:
    index, tokens = tool_operation_index(registry), _tokens(instruction)
    eligible = {operation for operation, meta in index.items() if _operation_words(meta).issubset(tokens)}
    adjacency: dict[str, set[str]] = {operation: set() for operation in index}
    for edge in registry["dependency_edges"]: adjacency[edge["from_operation"]].add(edge["to_operation"])
    def signature(operation: str) -> dict[str, Any]:
        meta = index[operation]
        return {"application": meta["app"], "callable_name": meta["function_name"], "operation": operation,
                "public_required": meta["required_parameters"], "public_optional_present": [],
                "runtime_context_present": [], "output_slots": meta["output_slots"]}
    candidates: list[tuple[str, ...]] = []
    def visit(path: tuple[str, ...]) -> None:
        current = path[-1]
        if (index[current]["access_mode"] == "write" and len(path) >= 2 and
                public_tool_path_audit(registry, [signature(operation) for operation in path])["passed"]):
            candidates.append(path)
        if len(path) == 4: return
        for child in sorted(adjacency[current]):
            if child in eligible and child not in path: visit(path + (child,))
    for operation in sorted(index):
        if operation not in eligible or index[operation]["access_mode"] != "read": continue
        visit((operation,))
    return sorted(set(candidates))


def select_pair(registry: dict[str, Any], inventory: dict[str, Any], excluded: set[str]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    fresh = [row for row in inventory["tasks"] if str(row["task_id"]) not in excluded]
    by_id = {str(row["task_id"]): row for row in fresh}
    per_task = {task_id: _candidate_paths(registry, str(row["instruction"])) for task_id, row in by_id.items()}
    candidates = []
    for left, right in itertools.combinations(sorted(per_task), 2):
        for path in sorted(set(per_task[left]) & set(per_task[right])):
            descriptor = _descriptor(tool_operation_index(registry), path)
            candidates.append({"a_family": left.rsplit("_", 1)[0], "b_family": right.rsplit("_", 1)[0],
                               "a": left, "b": right, "operations": list(path), "descriptor": descriptor,
                               "descriptor_sha256": canonical_digest(descriptor),
                               "a_instruction_sha256": hashlib.sha256(str(by_id[left]["instruction"]).encode("utf-8")).hexdigest(),
                               "b_instruction_sha256": hashlib.sha256(str(by_id[right]["instruction"]).encode("utf-8")).hexdigest()})
    candidates.sort(key=lambda row: (row["a_instruction_sha256"] != row["b_instruction_sha256"],
                                     row["descriptor_sha256"], row["a"], row["b"]))
    if not candidates: raise RuntimeError("no fresh public-registry-compatible development pair")
    return candidates[0], by_id, candidates


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--run", type=pathlib.Path, required=True); args = parser.parse_args()
    if args.run.exists() and any(args.run.iterdir()): raise RuntimeError("v5.3 run directory already exists")
    registry_path = ROOT / REGISTRY_RELATIVE_PATH
    registry = json.loads(registry_path.read_text(encoding="utf-8")); verify_public_tool_schema_registry(registry)
    inventory_path, acquisition = ROOT / INVENTORY_RELATIVE_PATH, ROOT / ACQUISITION_RELATIVE_PATH
    inventory = json.loads(inventory_path.read_text(encoding="utf-8")); excluded = prior_ids()
    selected, by_id, candidates = select_pair(registry, inventory, excluded)
    rows = json.loads(acquisition.read_text(encoding="utf-8")); rows = rows.get("trajectories", rows)
    pair = [selected["a"], selected["b"]]
    if len(rows) != 32 or set(pair) & {row["task_id"] for row in rows}: raise RuntimeError("v5.3 acquisition/disjointness failure")
    args.run.mkdir(parents=True, exist_ok=False)
    limits = {"executor": 240, "reme_lifecycle": 0, "reme_embedding": 0, "copromem_decomposition": 0}
    ledger = AppendOnlyLedger(args.run / "ledger.jsonl", 100.0, limits)
    initial, _ = construct_copromem(run=args.run, progress=args.run / "progress.jsonl", ledger=ledger,
                                    api_key="", raw=raw_acquisition_trajectories(rows), call_cap=0)
    bank = CoProMemAppWorldAdapter(api_key=""); bank.clone_from_state(initial)
    events = tuple(ActionObservation(**item) for item in selected["descriptor"])
    if bank.module.learning.retrieve("appworld", events).compatibility != "unknown":
        raise RuntimeError("v5.3 fresh pair is not initially unknown")
    budget = v5_budget_bound(call_limits=limits, historical_usd=historical_settled_usd())
    budget.update({"call_limits": limits, "hard_cap_usd": 100.0, "fits_hard_cap": budget["all_in_usd"] <= 100.0,
                   "ledger_dispatch_cap_usd": budget["dispatchable_usd"]})
    manifest = {"protocol": "v5_3_engineering_012_tool_schema", "engineering_only_exposed": True,
        "method_amendment": "observable_tool_schema_path_v5_3", "git_commit": source_commit(),
        "acquisition": {"source_export": str(acquisition.resolve()), "export_sha256": sha(acquisition), "expected_trajectories": 32, "fresh_state_required": True},
        "arms": ["no_memory", "copromem_dynamic"],
        "execution": {"max_actions": 30, "temperature": 0.7, "top_p": 1.0, "c_floor_gib": 5.0,
                      "model": "deepseek/deepseek-v4.1-flash", "provider": "deepseek", "fallbacks": False,
                      "reasoning_effort": "none", "stream": False, "completion_token_ceiling": 2048},
        "evaluation": {"split": "dev", "task_ids": pair, "a_task_id": pair[0], "b_task_id": pair[1],
                       "trial_ids": [1, 2], "seeds": [8301, 8302], "expected_trajectories": 8,
                       "descriptors": {pair[0]: selected["descriptor"], pair[1]: selected["descriptor"]},
                       "descriptor_sha256": selected["descriptor_sha256"],
                       "public_instruction_sha256": {pair[0]: selected["a_instruction_sha256"], pair[1]: selected["b_instruction_sha256"]},
                       "initial_compatibility": {pair[0]: "unknown", pair[1]: "unknown"},
                       "public_registry_relative_path": REGISTRY_RELATIVE_PATH, "public_registry_file_sha256": sha(registry_path),
                       "public_registry_sha256": registry["registry_sha256"],
                       "runtime_public_schema": {"openapi_root": OPENAPI_ROOT, "function_calling_root": FUNCTION_ROOT}},
        "budget": budget, "selection": {"public_only": True, "test_normal_excluded": True,
                       "selection_basis": "frozen public callable registry plus public lexical callable match",
                       "inventory_sha256": sha(inventory_path), "prior_ids_sha256": canonical_digest(sorted(excluded)),
                       "candidate_inventory_sha256": canonical_digest([{key: value for key, value in item.items() if key not in {"a_instruction_sha256", "b_instruction_sha256"}} for item in candidates]),
                       "selected_path_sha256": canonical_digest(selected["descriptor"])},
        "task_boundary_policy": "observable_tool_schema_path_v5_3"}
    write_json(args.run / "template.json", manifest)
    write_json(args.run / "descriptor-audit.json", {"a": pair[0], "b": pair[1], "public_only": True, "test_normal_used": False,
        "descriptor_sha256": selected["descriptor_sha256"], "registry_sha256": registry["registry_sha256"],
        "operations": selected["operations"], "candidate_count": len(candidates), "initial_compatibility": manifest["evaluation"]["initial_compatibility"]})
    print(json.dumps({"a": pair[0], "b": pair[1], "all_in_usd": budget["all_in_usd"], "registry_sha256": registry["registry_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
