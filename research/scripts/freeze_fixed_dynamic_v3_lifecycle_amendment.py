#!/usr/bin/env python3
"""Freeze the v3 lifecycle-only ceiling amendment without opening evaluation data."""
from __future__ import annotations
import hashlib, json, pathlib, subprocess

ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
V2 = ROOT / "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v2"
V3 = ROOT / "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v3"
INPUT_PRICE, OUTPUT_PRICE = 0.30 / 1_000_000, 1.20 / 1_000_000

def sha(path: pathlib.Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def canon(value: object) -> bytes: return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

def main() -> None:
    measured = json.loads((V3 / "lifecycle-prompt-measurement.json").read_text())
    if measured["combined_trajectories"] != 32 or measured["selected_lifecycle_input_ceiling"] != 65_536:
        raise SystemExit("the exact measured 32-trajectory v3 ceiling evidence is required")
    gate = json.loads((V2 / "acquisition/combined-gate.json").read_text())
    if not gate.get("passed") or gate["full_successes"] < 8 or gate["successful_families"] < 6:
        raise SystemExit("immutable combined acquisition gate did not pass")
    v2_manifest = V2 / "manifest-budget-160.json"
    if sha(v2_manifest) != (V2 / "manifest-budget-160.sha256").read_text().strip():
        raise SystemExit("v2 amended manifest integrity failure")
    original = json.loads(v2_manifest.read_text())
    eval_ids = original["evaluation"]["task_ids"]
    # Only availability is read from the ID-only inventory; no payload is opened.
    inventory = set((ROOT / "research/test_normal_ids.txt").read_text().split())
    if not set(eval_ids).issubset(inventory): raise SystemExit("frozen evaluation IDs absent from ID-only inventory")
    previous = json.loads((V2 / "final-report.json").read_text())
    carried = float(previous["ledger"]["charged_or_retained_exposure_usd"])
    per_executor = 32_768 * INPUT_PRICE + 2_048 * OUTPUT_PRICE
    per_lifecycle = 65_536 * INPUT_PRICE + 2_048 * OUTPUT_PRICE
    executor_calls, copro_calls, reme_calls, embedding_calls = 16*4*5*30, 320, 96, 216
    dispatchable = executor_calls*per_executor + copro_calls*per_executor + reme_calls*per_lifecycle + embedding_calls*8192*(0.02/1_000_000)
    contingency = dispatchable * .15
    budget = {"hard_cap_usd":160.0,"carried_prior_exposure_usd":carried,"executor_calls":executor_calls,
              "copromem_decomposition_calls":copro_calls,"reme_lifecycle_calls":reme_calls,"embedding_calls":embedding_calls,
              "executor_usd":executor_calls*per_executor,"copromem_decomposition_usd":copro_calls*per_executor,
              "reme_lifecycle_usd":reme_calls*per_lifecycle,"embedding_usd":embedding_calls*8192*(0.02/1_000_000),
              "dispatchable_usd":dispatchable,"nondispatchable_contingency_fraction":.15,
              "nondispatchable_contingency_usd":contingency,"all_in_usd":carried+dispatchable+contingency,
              "ledger_dispatch_cap_usd":160.0-contingency,"fits_hard_cap":carried+dispatchable+contingency <= 160.0}
    if not budget["fits_hard_cap"]: raise SystemExit("v3 all-inclusive conservative bound exceeds USD 160")
    manifest={"protocol":"corrected_fixed_dynamic_appworld_v3","status":"frozen","git_commit":subprocess.check_output(["git","-C",str(ROOT),"rev-parse","HEAD"],text=True).strip(),
              "predecessor":{"v2_manifest_sha256":sha(v2_manifest),"v2_terminal_report_sha256":sha(V2/"final-report.json"),"partial_reme_checkpoint_sha256":sha(V2/"reme/construction.jsonl"),"partial_reme_bank_excluded_from_analysis":True},
              "acquisition":{"frozen_combined_count":32,"combined_gate_sha256":sha(V2/"acquisition/combined-gate.json"),"no_replay":True},
              "evaluation":{"task_ids":eval_ids,"trial_ids":[1,2,3,4],"not_opened_before_manifest":True},"arms":original["arms"],
              "limits":{"actions":30,"executor_input_tokens":32768,"lifecycle_input_tokens":65536,"completion_tokens":2048,"temperature":.7,"top_p":1.0},
              "route":original["route"],"embedding":original["embedding"],"lifecycle_prompt_measurement_sha256":sha(V3/"lifecycle-prompt-measurement.json"),"budget":budget,
              "amendment":{"version":1,"scope":"lifecycle-only input ceiling","reason":"offline direct-upstream prompt measurement exceeded 32768; executor ceiling unchanged","prior_cap_usd":160.0}}
    V3.mkdir(parents=True,exist_ok=True); raw=canon(manifest)
    (V3/"manifest.json").write_bytes(raw); (V3/"manifest.sha256").write_text(hashlib.sha256(raw).hexdigest()+"\n")
    (V3/"budget-preflight.json").write_text(json.dumps(budget,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"manifest_sha256":hashlib.sha256(raw).hexdigest(),"all_in_usd":budget["all_in_usd"],"fits":True},sort_keys=True))
if __name__ == "__main__": main()
