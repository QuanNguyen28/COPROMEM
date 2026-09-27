#!/usr/bin/env python3
"""Resumable corrected five-arm AppWorld pilot; historical runs are untouched."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time
from typing import Any

ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
sys.path.insert(0, str(ROOT))
from research.official_pilot.evaluation_lifecycle import dynamic_post_trial_update
from research.official_pilot.five_arm_runner import (ROOT as _, acquisition_gate, acquisition_pool, append,
    construct_copromem, digest, execute_trajectory, official_post, raw_acquisition_trajectories, services, write_json)
from research.official_pilot.locked_openrouter import AppendOnlyLedger
from research.official_pilot.reme_bank import construct_once, load_clone
from src.copromem.appworld_comparison_adapter import CoProMemAppWorldAdapter, TrialInput

RUN = ROOT / "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v1"
MANIFEST, PROGRESS, LEDGER, STATUS = RUN / "manifest.json", RUN / "progress.jsonl", RUN / "ledger.jsonl", RUN / "runner-status.json"
CAP = 140.0


def env_value(name: str) -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.split("=", 1)[0].strip() == name and "=" in line:
            value = line.split("=", 1)[1].strip().strip("'\"")
            if value: return value
    raise RuntimeError(f"required credential {name} is absent")


def c_free_gb() -> float:
    stat = os.statvfs("/mnt/c")
    return stat.f_bavail * stat.f_frsize / 1024 ** 3


def manifest() -> dict[str, Any]:
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    if hashlib.sha256(raw).hexdigest() != (RUN / "manifest.sha256").read_text(encoding="utf-8").strip():
        raise RuntimeError("frozen manifest hash mismatch")
    if value["budget"]["hard_cap_usd"] != CAP or len(value["arms"]) != 5:
        raise RuntimeError("registered cap or five-arm allocation mismatch")
    return value


def status(state: str, **extra: Any) -> None:
    write_json(STATUS, {"state": state, "pid": os.getpid(), "updated_ns": time.time_ns(),
                        "manifest_sha256": (RUN / "manifest.sha256").read_text().strip(), **extra})


def artifact(arm: str, task_id: str, trial_id: int) -> pathlib.Path:
    return RUN / "evaluation" / arm / task_id / f"trial-{trial_id}.json"


def load_or_run(*, kwargs: dict[str, Any], path: pathlib.Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if c_free_gb() < 5:
        raise RuntimeError("Windows C storage floor would be breached before dispatch")
    return execute_trajectory(**kwargs, artifact_path=path)


def reme_input(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"trajectory_id": row["acquisition_identity"], "task_id": row["task_id"],
             "task_history": row["history"], "after_score": row["after_score"]} for row in rows]


def make_copro(state: dict[str, Any]) -> CoProMemAppWorldAdapter:
    adapter = CoProMemAppWorldAdapter(api_key="", model="deepseek/deepseek-v4.1-flash",
                                      provider_only="deepseek", reasoning_effort="none", decomposition_call_cap=320)
    adapter.clone_from_state(state)
    return adapter


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--preflight", action="store_true"); args = parser.parse_args()
    spec = manifest()
    if c_free_gb() < 5: raise RuntimeError("Windows C storage floor is below 5 GB")
    RUN.mkdir(parents=True, exist_ok=True)
    ledger = AppendOnlyLedger(LEDGER, CAP)
    api_key = env_value("OPENROUTER_API_KEY")
    status("preflight", c_free_gb=c_free_gb(), registered_bound=spec["budget"]["registered_conservative_usd"])
    append(PROGRESS, {"event": "runner_preflight", "c_free_gb": c_free_gb(), "manifest_sha256": (RUN / "manifest.sha256").read_text().strip()})
    if args.preflight:
        # Route/service launch uses no task payload and no provider request.
        with services(RUN, LEDGER, PROGRESS, CAP, ["preflight"]): pass
        status("preflight_passed", c_free_gb=c_free_gb()); return

    all_ids = spec["acquisition"]["task_ids"] + spec["evaluation"]["task_ids"]
    rows = acquisition_pool(run=RUN, progress=PROGRESS, ledger=ledger, api_key=api_key,
        acquisition_ids=spec["acquisition"]["task_ids"], evaluation_ids=spec["evaluation"]["task_ids"],
        seeds=spec["acquisition"]["seeds"], max_actions=spec["limits"]["actions"],
        temperature=spec["limits"]["temperature"])
    gate = acquisition_gate(rows)
    write_json(RUN / "acquisition" / "gate.json", gate)
    append(PROGRESS, {"event": "acquisition_gate_passed", **gate})

    # Build ReMe once, then later load hash-identical fixed/dynamic clones.
    snapshot = RUN / "reme" / "shared-bank.jsonl"
    checkpoint = RUN / "reme" / "construction.jsonl"
    with services(RUN, LEDGER, PROGRESS, CAP, ["reme-builder"]) as svc:
        bank_hash, count = construct_once(official_post, svc["reme-builder"].base_url, reme_input(rows),
                                           checkpoint, snapshot, lambda row: append(PROGRESS, row))
    if count != 24: raise RuntimeError("ReMe shared bank did not consume every acquisition trajectory")
    copro_state, copro_hash = construct_copromem(run=RUN, progress=PROGRESS, ledger=ledger, api_key=api_key,
                                                  raw=raw_acquisition_trajectories(rows))
    write_json(RUN / "lifecycle" / "initial-state.json", {"reme_bank_sha256": bank_hash, "copromem_state_sha256": copro_hash})

    names = ["reme-fixed", "reme-dynamic-1", "reme-dynamic-2", "reme-dynamic-3", "reme-dynamic-4"]
    with services(RUN, LEDGER, PROGRESS, CAP, names) as svc:
        if load_clone(official_post, svc["reme-fixed"].base_url, snapshot, bank_hash) != bank_hash: raise RuntimeError("fixed clone mismatch")
        for name in names[1:]:
            if load_clone(official_post, svc[name].base_url, snapshot, bank_hash) != bank_hash: raise RuntimeError("dynamic clone mismatch")
        copro_fixed = make_copro(copro_state)
        copro_dynamic = {trial: make_copro(copro_state) for trial in spec["evaluation"]["trial_ids"]}
        if copro_fixed.semantic_state_hash() != copro_hash or any(x.semantic_state_hash() != copro_hash for x in copro_dynamic.values()):
            raise RuntimeError("CoProMem initial clone mismatch")
        for task_id in spec["evaluation"]["task_ids"]:
            for trial_id in spec["evaluation"]["trial_ids"]:
                seed = 8000 + trial_id
                base = {"run": RUN, "progress": PROGRESS, "ledger": ledger, "api_key": api_key, "all_task_ids": all_ids,
                        "task_id": task_id, "trial_id": trial_id, "seed": seed, "max_actions": spec["limits"]["actions"],
                        "temperature": spec["limits"]["temperature"], "phase": "evaluation"}
                load_or_run(kwargs={**base, "arm": "no_memory"}, path=artifact("no_memory", task_id, trial_id))
                load_or_run(kwargs={**base, "arm": "official_upstream_reme_fixed", "memory_base_url": svc["reme-fixed"].base_url},
                            path=artifact("official_upstream_reme_fixed", task_id, trial_id))
                dynamic = svc[f"reme-dynamic-{trial_id}"]
                def reme_update(agent: Any, result: dict[str, Any]) -> None:
                    dynamic_post_trial_update(agent, result["after_score"], lambda e: append(PROGRESS, {**e, "trajectory_id": result["trajectory_id"]}))
                load_or_run(kwargs={**base, "arm": "official_upstream_reme_dynamic", "memory_base_url": dynamic.base_url,
                                    "post_score_update": reme_update}, path=artifact("official_upstream_reme_dynamic", task_id, trial_id))
                def fixed_memory(intent: str, domain: str, meta: dict[str, Any]) -> str:
                    return copro_fixed.prepare_trial(TrialInput(task_id, intent, domain, base_prompt=intent), trial_id)
                load_or_run(kwargs={**base, "arm": "copromem_fixed", "memory_for_instruction": fixed_memory},
                            path=artifact("copromem_fixed", task_id, trial_id))
                dynamic_copro = copro_dynamic[trial_id]
                def dynamic_memory(intent: str, domain: str, meta: dict[str, Any]) -> str:
                    return dynamic_copro.prepare_trial(TrialInput(task_id, intent, domain, base_prompt=intent), trial_id)
                def copro_update(agent: Any, result: dict[str, Any]) -> None:
                    intent = next(m["content"] for m in result["history"] if m["role"] == "user")
                    trial = TrialInput(task_id, intent, "appworld", base_prompt=intent)
                    actions = [m["content"] for m in result["history"] if m["role"] == "assistant"]
                    dynamic_copro.record_scored_trial(trial, trial_id, success=result["after_score"] == 1.0,
                        actions=actions, state_hash=dynamic_copro.semantic_state_hash(), seed=seed)
                    append(PROGRESS, {"event": "copromem_dynamic_update", "trajectory_id": result["trajectory_id"],
                                      "state_sha256": dynamic_copro.semantic_state_hash()})
                load_or_run(kwargs={**base, "arm": "copromem_dynamic", "memory_for_instruction": dynamic_memory,
                                    "post_score_update": copro_update}, path=artifact("copromem_dynamic", task_id, trial_id))
    report = ROOT / "research" / "scripts" / "build_corrected_fixed_dynamic_report.py"
    subprocess.run([sys.executable, str(report)],
                   cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)}, check=True)
    final = RUN / "final-report.json"
    if not final.exists(): raise RuntimeError("final report was not durably produced")
    status("completed", c_free_gb=c_free_gb(), final_report=str(final), final_report_sha256=hashlib.sha256(final.read_bytes()).hexdigest())


if __name__ == "__main__": main()
