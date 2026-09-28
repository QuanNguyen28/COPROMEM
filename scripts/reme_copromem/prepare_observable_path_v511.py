"""Freeze the v5.2 engineering-only public-registry A/B probe.

Selection uses only the already-public development instruction inventory and
the frozen public OpenAPI registry.  It intentionally does not inspect task
payloads, histories, scorer state, or results from prior runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess

from copromem.benchmarks.appworld.adapter import CoProMemAppWorldAdapter
from copromem.experiments.reme_copromem.public_path_registry import canonical_digest, operation_index, verify_public_registry
from copromem.experiments.reme_copromem.runner import AppendOnlyLedger, construct_copromem, digest, raw_acquisition_trajectories, v5_budget_bound, write_json
from copromem.learning import ActionObservation, LearningCore


ROOT = pathlib.Path(__file__).resolve().parents[2]
PAIR = ("df61dc5_1", "df61dc5_2")
PATH_OPERATIONS = ("apis.venmo.show_transactions", "apis.venmo.like_transaction")
REGISTRY_RELATIVE_PATH = "research/reme_copromem_fixed_dynamic_review/appworld_public_path_registry_v5_2.json"
ACQUISITION_RELATIVE_PATH = "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v5_engineering_001/acquisition/scored-train-acquisition.json"
INVENTORY_RELATIVE_PATH = "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v5_engineering_001/public-dev-descriptors.json"


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prior_ids() -> set[str]:
    result: set[str] = set()
    for path in (ROOT / "artifacts/research/official_reme_copromem_pilot").glob("**/manifest.json"):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        # A frozen but preflight-only manifest never opens its task payloads.
        # Count evaluation IDs only once an immutable evaluation artifact
        # exists; acquisition IDs are always historical evidence and remain
        # excluded regardless of later evaluation state.
        if any((path.parent / "evaluation").glob("**/trial-*.json")):
            result.update(str(item) for item in manifest.get("evaluation", {}).get("task_ids", ()) if item)
        result.update(str(item) for item in manifest.get("acquisition", {}).get("task_ids", ()) if item)
    return result


def historical_settled_usd() -> float:
    """Conservative carry-forward from immutable local ledgers (settles only)."""
    total = 0.0
    for path in (ROOT / "artifacts/research/official_reme_copromem_pilot").glob("**/ledger.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                raise RuntimeError(f"malformed historical ledger: {path}")
            if item.get("event") == "settle":
                total += float(item["usd"])
    return total


def source_commit() -> str:
    """Ignore cross-OS worktree variables inherited by launcher shells."""
    env = dict(os.environ)
    env.pop("GIT_DIR", None); env.pop("GIT_WORK_TREE", None); env.pop("GIT_INDEX_FILE", None)
    pointer = ROOT / ".git"
    if pointer.is_file():
        match = re.match(r"gitdir:\s*([A-Za-z]):/(.+)", pointer.read_text(encoding="utf-8").strip())
        if match:
            env["GIT_DIR"] = f"/mnt/{match.group(1).lower()}/{match.group(2)}"
            env["GIT_WORK_TREE"] = str(ROOT)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, env=env).strip()


def descriptor(registry: dict) -> list[dict]:
    index = operation_index(registry)
    rows = []
    for operation in PATH_OPERATIONS:
        meta = index.get(operation)
        if meta is None:
            raise RuntimeError("selected public operation absent from frozen registry")
        rows.append({"operation": meta["operation"], "input_slots": meta["input_slots"], "output_slots": meta["output_slots"]})
    edge = {"from_operation": PATH_OPERATIONS[0], "to_operation": PATH_OPERATIONS[1], "via_slot": "transaction_id", "kind": "public_schema_flow"}
    if edge not in registry["dependency_edges"]:
        raise RuntimeError("selected descriptor is not a frozen public registry path")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=pathlib.Path)
    args = parser.parse_args()
    if args.run.exists() and any(args.run.iterdir()):
        raise RuntimeError("v5.2 run directory already exists")
    registry_path = ROOT / REGISTRY_RELATIVE_PATH
    registry = json.loads(registry_path.read_text(encoding="utf-8")); verify_public_registry(registry)
    public = json.loads((ROOT / INVENTORY_RELATIVE_PATH).read_text(encoding="utf-8"))
    by_id = {row["task_id"]: row for row in public["tasks"]}
    used = prior_ids()
    if not set(PAIR).issubset(by_id) or set(PAIR) & used:
        raise RuntimeError("v5.2 pair is not fresh in the public development inventory")
    acquisition = ROOT / ACQUISITION_RELATIVE_PATH
    raw = json.loads(acquisition.read_text(encoding="utf-8")); rows = raw.get("trajectories", raw)
    if len(rows) != 32 or set(PAIR) & {row["task_id"] for row in rows}:
        raise RuntimeError("v5.2 acquisition provenance/disjointness failure")
    path_descriptor = descriptor(registry)
    events = tuple(ActionObservation(**row) for row in path_descriptor)
    if LearningCore.signature(events) is None:
        raise RuntimeError("invalid public path descriptor")
    args.run.mkdir(parents=True, exist_ok=False)
    limits = {"executor": 240, "reme_lifecycle": 0, "reme_embedding": 0, "copromem_decomposition": 0}
    ledger = AppendOnlyLedger(args.run / "ledger.jsonl", 100.0, limits)
    initial, _ = construct_copromem(run=args.run, progress=args.run / "progress.jsonl", ledger=ledger,
                                    api_key="", raw=raw_acquisition_trajectories(rows), call_cap=0)
    bank = CoProMemAppWorldAdapter(api_key=""); bank.clone_from_state(initial)
    if bank.module.learning.retrieve("appworld", events).compatibility != "unknown":
        raise RuntimeError("v5.2 A/B path must be initially unknown")
    historical = historical_settled_usd()
    budget = v5_budget_bound(call_limits=limits, historical_usd=historical)
    budget.update({"call_limits": limits, "hard_cap_usd": 100.0,
                   "fits_hard_cap": budget["all_in_usd"] <= 100.0,
                   "ledger_dispatch_cap_usd": budget["dispatchable_usd"]})
    manifest = {
        "protocol": "v5_2_engineering_011_observable_path", "engineering_only_exposed": True,
        "method_amendment": "observable_supported_path_v5_2", "git_commit": source_commit(),
        "acquisition": {"source_export": str(acquisition.resolve()), "export_sha256": sha(acquisition),
                        "expected_trajectories": 32, "fresh_state_required": True},
        "arms": ["no_memory", "copromem_dynamic"],
        "execution": {"max_actions": 30, "temperature": 0.7, "top_p": 1.0, "c_floor_gib": 5.0,
                      "model": "deepseek/deepseek-v4.1-flash", "provider": "deepseek", "fallbacks": False,
                      "reasoning_effort": "none", "stream": False, "completion_token_ceiling": 2048},
        "evaluation": {"split": "dev", "task_ids": list(PAIR), "a_task_id": PAIR[0], "b_task_id": PAIR[1],
                       "trial_ids": [1, 2], "seeds": [8201, 8202], "expected_trajectories": 8,
                       "descriptors": {PAIR[0]: path_descriptor, PAIR[1]: path_descriptor},
                       "descriptor_sha256": digest(path_descriptor),
                       "public_instruction_sha256": {key: hashlib.sha256(by_id[key]["instruction"].encode("utf-8")).hexdigest() for key in PAIR},
                       "initial_compatibility": {key: "unknown" for key in PAIR},
                       "public_registry_relative_path": REGISTRY_RELATIVE_PATH,
                       "public_registry_file_sha256": sha(registry_path), "public_registry_sha256": registry["registry_sha256"]},
        "budget": budget,
        "selection": {"public_only": True, "test_normal_excluded": True,
                      "selection_basis": "frozen public instruction hashes plus frozen OpenAPI registry path",
                      "inventory_sha256": sha(ROOT / INVENTORY_RELATIVE_PATH), "prior_ids_sha256": digest(sorted(used)),
                      "selected_path_sha256": canonical_digest(path_descriptor)},
        "task_boundary_policy": "observable_supported_path_v5_2",
    }
    write_json(args.run / "template.json", manifest)
    write_json(args.run / "descriptor-audit.json", {"a": PAIR[0], "b": PAIR[1], "public_only": True,
        "test_normal_used": False, "descriptor_sha256": manifest["evaluation"]["descriptor_sha256"],
        "registry_sha256": registry["registry_sha256"], "path_sha256": canonical_digest(path_descriptor),
        "initial_compatibility": manifest["evaluation"]["initial_compatibility"]})
    print(json.dumps({"a": PAIR[0], "b": PAIR[1], "all_in_usd": budget["all_in_usd"],
                      "registry_sha256": registry["registry_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
