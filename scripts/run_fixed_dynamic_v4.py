#!/usr/bin/env python3
"""Restart-safe v4 five-arm executor; v3 evaluation evidence is never read."""
from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time
from collections import defaultdict
from typing import Any

ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
sys.path.insert(0, str(ROOT))
from research.official_pilot.evaluation_lifecycle import dynamic_post_trial_update
from research.official_pilot.five_arm_runner import append, digest, execute_trajectory, official_post, services, write_json
from research.official_pilot.locked_openrouter import AppendOnlyLedger
from research.official_pilot.reme_bank import construct_once, load_clone
from scripts.run_corrected_fixed_dynamic_v2 import frozen_v3_acquisition_pool, reme_input
from src.copromem.appworld_comparison_adapter import CoProMemAppWorldAdapter, TrialInput

RUN = ROOT / "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v4"
MANIFEST, MANIFEST_SHA = RUN / "manifest.json", RUN / "manifest.sha256"
PROGRESS, LEDGER, STATUS, SUMMARY = (RUN / "progress.jsonl", RUN / "ledger.jsonl",
                                     RUN / "runner-status.json", RUN / "live-summary.json")


def file_sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def c_free_gb() -> float:
    stat = os.statvfs("/mnt/c")
    return stat.f_bavail * stat.f_frsize / 1024 ** 3


def env_value(name: str) -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.split("=", 1)[0].strip() == name and "=" in line:
            value = line.split("=", 1)[1].strip().strip("'\"")
            if value:
                return value
    raise RuntimeError(f"required credential {name} is absent")


def spec() -> dict[str, Any]:
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    raw = json.dumps(value, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    if file_sha(MANIFEST) != MANIFEST_SHA.read_text().strip() or hashlib.sha256(raw).hexdigest() != file_sha(MANIFEST):
        raise RuntimeError("v4 frozen manifest hash mismatch")
    if (value.get("protocol") != "corrected_fixed_dynamic_v4" or value.get("status") != "frozen_pre_payload"
            or len(value["evaluation"]["task_ids"]) != 16 or len(value["arms"]) != 5
            or not value["budget"].get("fits_hard_cap") or value["budget"].get("hard_cap_usd") != 160.0):
        raise RuntimeError("v4 frozen protocol invariant failed")
    return value


def status(state: str, **extra: Any) -> None:
    write_json(STATUS, {"state": state, "pid": os.getpid(), "manifest_sha256": MANIFEST_SHA.read_text().strip(),
                        "updated_ns": time.time_ns(), **extra})


def progress_event_callback(path: pathlib.Path):
    """Adapt unary lifecycle events to the durable JSONL progress sink."""
    return lambda record: append(path, record)


def acquire_lock() -> None:
    lock = RUN / "runner.lock"
    if lock.exists():
        prior = json.loads(lock.read_text(encoding="utf-8"))
        try:
            os.kill(int(prior["pid"]), 0)
        except ProcessLookupError:
            lock.unlink()
        else:
            raise RuntimeError(f"v4 runner already active (PID {prior['pid']})")
    write_json(lock, {"pid": os.getpid(), "manifest_sha256": MANIFEST_SHA.read_text().strip(), "created_ns": time.time_ns()})
    def release() -> None:
        try:
            if json.loads(lock.read_text(encoding="utf-8"))["pid"] == os.getpid(): lock.unlink()
        except Exception: pass
    atexit.register(release)


def bootstrap_ledger(value: dict[str, Any]) -> AppendOnlyLedger:
    ledger = AppendOnlyLedger(LEDGER, float(value["budget"]["ledger_dispatch_cap_usd"]))
    carry = float(value["budget"]["historical_charged_or_reserved_usd"])
    identifier = f"carry-forward-fixed-dynamic-v4-usd-{carry:.12f}"
    known = LEDGER.read_text(encoding="utf-8") if LEDGER.exists() else ""
    if identifier not in known:
        ledger.reserve(identifier, carry, {"role": "historical_carry_forward", "source": "fixed_dynamic_v3_ledger"})
    return ledger


def artifact(arm: str, task_id: str, trial: int) -> pathlib.Path:
    return RUN / "evaluation" / arm / task_id / f"trial-{trial}.json"


def marker(arm: str, task_id: str, trial: int) -> pathlib.Path:
    return RUN / "evaluation_updates" / arm / task_id / f"trial-{trial}.json"


def copro_retrieval(arm: str, adapter: CoProMemAppWorldAdapter, task_id: str, trial: int):
    path = RUN / "retrieval" / arm / task_id / f"trial-{trial}.json"
    def call(intent: str, domain: str, _: dict[str, Any]) -> str:
        if path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            provenance = record.get("provenance")
            if (not isinstance(provenance, dict) or not isinstance(provenance.get("task_input"), dict) or
                    CoProMemAppWorldAdapter._digest(provenance["task_input"]) != provenance.get("task_input_sha256")):
                raise RuntimeError("persisted CoProMem retrieval provenance is invalid")
            if adapter.semantic_state_hash() != provenance.get("pre_state_sha256"):
                raise RuntimeError("CoProMem restart state does not match persisted retrieval pre-state")
            guidance = CoProMemAppWorldAdapter.reproduce_retrieval(provenance["pre_state"], provenance["task_input"], provenance)
            if hashlib.sha256(guidance.encode("utf-8")).hexdigest() != provenance.get("guidance_sha256"):
                raise RuntimeError("persisted CoProMem guidance hash mismatch")
            return guidance
        before = adapter.semantic_state_hash()
        guidance, provenance = adapter.retrieve_with_provenance(TrialInput(task_id, intent, domain, base_prompt=intent), trial)
        reproduced = CoProMemAppWorldAdapter.reproduce_retrieval(provenance["pre_state"], provenance["task_input"], provenance)
        if guidance != reproduced or hashlib.sha256(guidance.encode("utf-8")).hexdigest() != provenance["guidance_sha256"]:
            raise RuntimeError("CoProMem guidance cannot be reproduced offline")
        write_json(path, {"task_id": task_id, "trial": trial, "arm": arm, "pre_state_sha256": before,
                          "post_state_sha256": adapter.semantic_state_hash(), "guidance_sha256": provenance["guidance_sha256"],
                          "provenance": provenance})
        return guidance
    return call


def preflight(value: dict[str, Any]) -> None:
    if c_free_gb() < 5.0: raise RuntimeError("C-drive is below frozen 5 GiB floor")
    gate = json.loads((RUN / "copromem/acquisition-retrieval-gate.json").read_text())
    state = json.loads((RUN / "copromem/initial-state.json").read_text())
    if not gate.get("passed") or digest(state) != value["acquisition"]["copromem_bank_sha256"]:
        raise RuntimeError("passed acquisition retrieval gate/bank hash mismatch")
    # The stored gate records are a complete zero-call proof of byte-stable replay.
    for record in gate["records"]:
        provenance = record["provenance"]
        if CoProMemAppWorldAdapter.reproduce_retrieval(state, provenance["task_input"], provenance).encode() != provenance["guidance_bytes"].encode():
            raise RuntimeError("acquisition retrieval reproduction mismatch")
    for trial in value["evaluation"]["trial_ids"]:
        if digest(state) != value["acquisition"]["copromem_bank_sha256"]:
            raise RuntimeError(f"CoProMem clone mismatch for trial {trial}")
    append(PROGRESS, {"event": "zero_cost_preflight_passed", "manifest_sha256": MANIFEST_SHA.read_text().strip(),
                      "bank_sha256": digest(state), "provider_calls": 0, "c_free_gb": c_free_gb()})


def summary(value: dict[str, Any], stage: str) -> None:
    completed = []
    for path in (RUN / "evaluation").glob("*/*/*.json"):
        try: completed.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception: continue
    by_arm = defaultdict(int)
    for row in completed: by_arm[str(row.get("arm"))] += 1
    write_json(SUMMARY, {"state": stage, "evaluation_completed": len(completed),
        "evaluation_expected": value["evaluation"]["expected_trajectories"], "per_arm_completed": dict(by_arm),
        "c_free_gb": c_free_gb(), "manifest_sha256": MANIFEST_SHA.read_text().strip()})


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--preflight", action="store_true"); args = parser.parse_args()
    value = spec(); RUN.mkdir(parents=True, exist_ok=True); acquire_lock(); ledger = bootstrap_ledger(value)
    preflight(value); status("preflight_passed", c_free_gb=c_free_gb(), budget=value["budget"]); summary(value, "preflight_passed")
    if args.preflight: return
    key = env_value("OPENROUTER_API_KEY")
    combined = frozen_v3_acquisition_pool()
    if len(combined) != 32: raise RuntimeError("immutable v4 acquisition source is incomplete")
    state = json.loads((RUN / "copromem/initial-state.json").read_text())
    bank_hash = digest(state)
    cap = float(value["budget"]["ledger_dispatch_cap_usd"])
    names = ["reme-builder", "reme-fixed"] + [f"reme-dynamic-{x}" for x in value["evaluation"]["trial_ids"]]
    with services(RUN, LEDGER, PROGRESS, cap, names, lifecycle_input_ceiling=131072) as svc:
        snapshot, checkpoint = RUN / "reme/shared-bank.jsonl", RUN / "reme/construction.jsonl"
        reme_hash, count = construct_once(official_post, svc["reme-builder"].base_url, reme_input(combined), checkpoint, snapshot,
                                          progress_event_callback(PROGRESS))
        if count != 32: raise RuntimeError("official ReMe construction did not consume 32 immutable inputs")
        if load_clone(official_post, svc["reme-fixed"].base_url, snapshot, reme_hash) != reme_hash: raise RuntimeError("ReMe fixed clone mismatch")
        for trial in value["evaluation"]["trial_ids"]:
            service = svc[f"reme-dynamic-{trial}"]
            if load_clone(official_post, service.base_url, snapshot, reme_hash) != reme_hash: raise RuntimeError("ReMe dynamic clone mismatch")
            saved = RUN / "reme" / f"dynamic-trial-{trial}.jsonl"
            if saved.exists(): official_post(service.base_url, "load_memory", {"load_file_path": str(saved), "clear_existing": True})
        fixed = CoProMemAppWorldAdapter(api_key=""); fixed.clone_from_state(state)
        dynamic = {}
        for trial in value["evaluation"]["trial_ids"]:
            instance = CoProMemAppWorldAdapter(api_key=""); saved = RUN / "copromem" / f"dynamic-trial-{trial}.json"
            instance.clone_from_state(json.loads(saved.read_text()) if saved.exists() else state); dynamic[trial] = instance
        all_ids = value["evaluation"]["task_ids"]
        for task_id in all_ids:
            for trial, seed in zip(value["evaluation"]["trial_ids"], value["evaluation"]["seeds"]):
                base = dict(run=RUN, progress=PROGRESS, ledger=ledger, api_key=key, all_task_ids=all_ids, task_id=task_id,
                            trial_id=trial, seed=seed, max_actions=30, temperature=0.7, phase="evaluation")
                jobs = [("no_memory", {}), ("official_upstream_reme_fixed", {"memory_base_url": svc["reme-fixed"].base_url}),
                        ("official_upstream_reme_dynamic", {"memory_base_url": svc[f"reme-dynamic-{trial}"].base_url}),
                        ("copromem_fixed", {"memory_for_instruction": copro_retrieval("copromem_fixed", fixed, task_id, trial)}),
                        ("copromem_dynamic", {"memory_for_instruction": copro_retrieval("copromem_dynamic", dynamic[trial], task_id, trial)})]
                for arm, kwargs in jobs:
                    out = artifact(arm, task_id, trial)
                    if out.exists():
                        if arm in {"official_upstream_reme_dynamic", "copromem_dynamic"} and not marker(arm, task_id, trial).exists():
                            raise RuntimeError("completed dynamic trajectory lacks durable update marker; replay is forbidden")
                        continue
                    if c_free_gb() < 5.0: raise RuntimeError("C-drive floor would be breached before dispatch")
                    if arm == "official_upstream_reme_dynamic":
                        service = svc[f"reme-dynamic-{trial}"]
                        def update_reme(agent: Any, result: dict[str, Any], *, _service=service, _trial=trial) -> None:
                            outcome = dynamic_post_trial_update(agent, result["after_score"],
                                lambda event: append(PROGRESS, {**event, "trajectory_id": result["trajectory_id"]}))
                            saved = RUN / "reme" / f"dynamic-trial-{_trial}.jsonl"
                            official_post(_service.base_url, "dump_memory", {"dump_file_path": str(saved)})
                            write_json(marker("official_upstream_reme_dynamic", task_id, _trial),
                                {"trajectory_id": result["trajectory_id"], "outcome": outcome, "snapshot_sha256": file_sha(saved)})
                        kwargs = {**kwargs, "post_score_update": update_reme}
                    result = execute_trajectory(**base, arm=arm, artifact_path=out, **kwargs)
                    if arm == "official_upstream_reme_dynamic":
                        if not marker(arm, task_id, trial).exists():
                            raise RuntimeError("scored ReMe dynamic trajectory lacks durable update marker")
                    elif arm == "copromem_dynamic":
                        intent = next(x["content"] for x in result["history"] if x["role"] == "user")
                        before = dynamic[trial].semantic_state_hash(); actions = [x["content"] for x in result["history"] if x["role"] == "assistant"]
                        dynamic[trial].record_scored_trial(TrialInput(task_id, intent, "appworld", base_prompt=intent), trial,
                            success=result["after_score"] == 1.0, actions=actions, state_hash=before, seed=seed)
                        write_json(RUN / "copromem" / f"dynamic-trial-{trial}.json", dynamic[trial].export_state())
                        write_json(marker(arm, task_id, trial), {"trajectory_id": result["trajectory_id"], "before_state_sha256": before,
                            "after_state_sha256": dynamic[trial].semantic_state_hash()})
                    summary(value, "evaluation")
    report = ROOT / "research/scripts/build_fixed_dynamic_v4_report.py"
    subprocess.run([sys.executable, str(report)], cwd=ROOT, check=True)
    final = RUN / "final-report.json"
    if not final.is_file(): raise RuntimeError("final report was not durably created")
    status("completed", c_free_gb=c_free_gb(), final_report_sha256=file_sha(final)); summary(value, "completed")


if __name__ == "__main__":
    try: main()
    except BaseException as exc:
        RUN.mkdir(parents=True, exist_ok=True); append(PROGRESS, {"event": "runner_failed", "error_type": type(exc).__name__})
        if MANIFEST.exists(): status("failed", error_type=type(exc).__name__)
        raise
