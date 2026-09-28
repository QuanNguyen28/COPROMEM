"""Create the immutable, development-only template for task-boundary 006.

Selection reads the already-recorded public development inventory only.  It
does not start a task, inspect a scorer, or read any test-normal task.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess

from copromem.experiments.reme_copromem.runner import (AppendOnlyLedger, construct_copromem, digest,
    raw_acquisition_trajectories, v5_budget_bound, write_json)
from copromem.benchmarks.appworld.adapter import CoProMemAppWorldAdapter
from copromem.learning import ActionObservation, LearningCore


ROOT = pathlib.Path(__file__).resolve().parents[2]

# Public API-shape descriptor for the same-family, single-question Spotify
# tasks. It contains neither account values nor task-instance values.
FLAT_SPOTIFY_DESCRIPTOR = [
    {"operation": "apis.api_docs.show_api_descriptions", "input_slots": ["app_name"], "output_slots": ["observation"]},
    {"operation": "apis.api_docs.show_api_doc", "input_slots": ["api_name", "app_name"], "output_slots": ["observation"]},
    {"operation": "apis.supervisor.show_account_passwords", "input_slots": [], "output_slots": ["var_1"]},
    {"operation": "apis.spotify.login", "input_slots": ["password", "username", "var_1"], "output_slots": ["var_2"]},
    {"operation": "apis.spotify.show_current_song", "input_slots": ["access_token"], "output_slots": ["var_3"]},
    {"operation": "apis.spotify.show_artist", "input_slots": ["artist_id"], "output_slots": ["var_4"]},
    {"operation": "apis.supervisor.complete_task", "input_slots": [], "output_slots": ["observation"]},
]


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--run", type=pathlib.Path, required=True)
    parser.add_argument("--acquisition", type=pathlib.Path, required=True)
    parser.add_argument("--initial-state", type=pathlib.Path)
    args = parser.parse_args()
    inventory = ROOT / "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v5_engineering_001/public-dev-descriptors.json"
    public = json.loads(inventory.read_text(encoding="utf-8"))
    selected = ("6bdbc26_1", "6bdbc26_2")
    public_ids = {row["task_id"] for row in public["tasks"]}
    if not set(selected) <= public_ids:
        raise RuntimeError("selected IDs are not recorded development tasks")
    raw = json.loads(args.acquisition.read_text(encoding="utf-8")); rows = raw.get("trajectories", raw)
    acquisition_ids = {row["task_id"] for row in rows}
    if len(rows) != 32 or set(selected) & acquisition_ids:
        raise RuntimeError("006 acquisition disjointness failed")
    # This check proves both public descriptors are structurally identical and
    # currently uncovered by the fresh acquisition-only bank.
    events = tuple(ActionObservation(**item) for item in FLAT_SPOTIFY_DESCRIPTOR)
    if not LearningCore.signature(events): raise RuntimeError("flat descriptor is not structurally valid")
    initial_state = args.initial_state or (args.run / "copromem" / "initial-state.json")
    if initial_state.exists():
        state = json.loads(initial_state.read_text(encoding="utf-8"))
    else:
        # This is a fresh, local-only construction from the immutable export;
        # call_cap=0 prohibits any decomposition/provider dispatch.
        ledger = AppendOnlyLedger(args.run / "ledger.jsonl", 100.0,
            {"executor": 240, "reme_lifecycle": 0, "reme_embedding": 0, "copromem_decomposition": 0})
        state, _ = construct_copromem(run=args.run, progress=args.run / "progress.jsonl", ledger=ledger,
            api_key="", raw=raw_acquisition_trajectories(rows), call_cap=0)
    adapter = CoProMemAppWorldAdapter(api_key=""); adapter.clone_from_state(state)
    compatibility = adapter.module.learning.retrieve("appworld", events).compatibility
    if compatibility != "unknown": raise RuntimeError("selected descriptor is not initially unknown")
    historical = 0.168808788
    limits = {"executor": 240, "reme_lifecycle": 0, "reme_embedding": 0, "copromem_decomposition": 0}
    budget = v5_budget_bound(call_limits=limits, historical_usd=historical)
    budget.update({"hard_cap_usd": 100.0, "fits_hard_cap": budget["all_in_usd"] <= 100.0,
                   "ledger_dispatch_cap_usd": budget["dispatchable_usd"], "call_limits": limits})
    if not budget["fits_hard_cap"]: raise RuntimeError("006 conservative budget exceeds hard cap")
    task_public = {row["task_id"]: row for row in public["tasks"] if row["task_id"] in selected}
    template = {"protocol": "v5_engineering_006_task_boundary", "engineering_only_exposed": True,
      "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
      "acquisition": {"source_export": str(args.acquisition.resolve()), "export_sha256": sha(args.acquisition),
                      "expected_trajectories": 32, "fresh_state_required": True},
      "arms": ["no_memory", "copromem_dynamic"],
      "execution": {"max_actions": 30, "temperature": 0.7, "top_p": 1.0, "c_floor_gib": 5.0,
                    "model": "deepseek/deepseek-v4.1-flash", "provider": "deepseek", "fallbacks": False,
                    "reasoning_effort": "none", "stream": False, "completion_token_ceiling": 2048},
      "evaluation": {"split": "dev", "task_ids": list(selected), "a_task_id": selected[0], "b_task_id": selected[1],
        "trial_ids": [1, 2], "seeds": [7601, 7602], "expected_trajectories": 8,
        "descriptors": {selected[0]: FLAT_SPOTIFY_DESCRIPTOR, selected[1]: FLAT_SPOTIFY_DESCRIPTOR},
        "descriptor_sha256": digest(FLAT_SPOTIFY_DESCRIPTOR),
        "public_instruction_sha256": {task: hashlib.sha256(task_public[task]["instruction"].encode()).hexdigest() for task in selected},
        "initial_compatibility": {task: compatibility for task in selected}},
      "budget": budget,
      "selection": {"public_inventory_sha256": sha(inventory), "task_family": "6bdbc26",
        "public_only": True, "test_normal_excluded": True, "excluded_acquisition_ids_sha256": digest(sorted(acquisition_ids)),
        "descriptor_rule": "same documented ordered public API-shape descriptor; instance values omitted"}}
    args.run.mkdir(parents=True, exist_ok=True)
    write_json(args.run / "template.json", template)
    write_json(args.run / "descriptor-audit.json", {"a": selected[0], "b": selected[1], "compatibility": compatibility,
      "descriptor_sha256": template["evaluation"]["descriptor_sha256"], "public_only": True, "test_normal_used": False})
    print(json.dumps({"a": selected[0], "b": selected[1], "compatibility": compatibility, "all_in_usd": budget["all_in_usd"]}, sort_keys=True))


if __name__ == "__main__": main()
