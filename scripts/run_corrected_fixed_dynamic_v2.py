#!/usr/bin/env python3
"""Resumable v2 corrected five-arm AppWorld pilot.

The v1 pool is read-only.  This runner adds the pre-registered eight shared
episodes, then uses the combined pool exactly once for both memory methods.
"""
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
from typing import Any, Callable

ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
sys.path.insert(0, str(ROOT))
from research.official_pilot.evaluation_lifecycle import dynamic_post_trial_update
from research.official_pilot.five_arm_runner import (
    acquisition_gate, acquisition_pool, append, construct_copromem, digest,
    execute_trajectory, official_post, raw_acquisition_trajectories, services, write_json,
)
from research.official_pilot.locked_openrouter import AppendOnlyLedger
from research.official_pilot.reme_bank import construct_once, load_clone
from research.scripts.freeze_corrected_fixed_dynamic_v2_manifest import verify_v1
from src.copromem.appworld_comparison_adapter import CoProMemAppWorldAdapter, TrialInput

RUN = ROOT / "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v2"
MANIFEST = RUN / "manifest-budget-160.json"
MANIFEST_SHA = RUN / "manifest-budget-160.sha256"
PROGRESS, LEDGER, STATUS, SUMMARY = (RUN / "progress.jsonl", RUN / "ledger.jsonl",
                                     RUN / "runner-status.json", RUN / "live-summary.json")


def env_value(name: str) -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and line.split("=", 1)[0].strip() == name:
            value = line.split("=", 1)[1].strip().strip("'\"")
            if value:
                return value
    raise RuntimeError(f"required credential {name} is absent")


def c_free_gb() -> float:
    stat = os.statvfs("/mnt/c")
    return stat.f_bavail * stat.f_frsize / 1024 ** 3


def read_manifest() -> dict[str, Any]:
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA.read_text(encoding="utf-8").strip():
        raise RuntimeError("USD 160 manifest hash mismatch")
    budget = value["budget"]
    if value.get("status") != "frozen" or budget["hard_cap_usd"] != 160.0 or not budget["fits_hard_cap"]:
        raise RuntimeError("authorized v2 amendment is not frozen and within cap")
    if len(value["evaluation"]["task_ids"]) != 16 or len(value["arms"]) != 5:
        raise RuntimeError("frozen five-arm minimum allocation mismatch")
    return value


def status(state: str, **extra: Any) -> None:
    write_json(STATUS, {"state": state, "pid": os.getpid(), "updated_ns": time.time_ns(),
                        "manifest_sha256": MANIFEST_SHA.read_text().strip(), **extra})


def acquire_lock() -> None:
    path = RUN / "runner.lock"
    if path.exists():
        try:
            previous = int(json.loads(path.read_text(encoding="utf-8"))["pid"])
            os.kill(previous, 0)
        except ProcessLookupError:
            path.unlink()
        except FileNotFoundError:
            pass
        else:
            raise RuntimeError(f"v2 runner already active (PID {previous})")
    write_json(path, {"pid": os.getpid(), "created_ns": time.time_ns()})
    def release() -> None:
        try:
            if json.loads(path.read_text(encoding="utf-8"))["pid"] == os.getpid():
                path.unlink()
        except Exception:
            pass
    atexit.register(release)


def bootstrap_ledger(spec: dict[str, Any]) -> AppendOnlyLedger:
    cap = float(spec["budget"]["ledger_dispatch_cap_usd"])
    ledger = AppendOnlyLedger(LEDGER, cap)
    carried = "carry-forward-fixed-dynamic-v1-usd-0.048008"
    known = LEDGER.read_text(encoding="utf-8") if LEDGER.exists() else ""
    if carried not in known:
        ledger.reserve(carried, float(spec["budget"]["carried_v1_exposure_usd"]),
                       {"role": "historical_carry_forward", "protocol": "fixed_dynamic_v1"})
    return ledger


def artifact(arm: str, task_id: str, trial: int) -> pathlib.Path:
    return RUN / "evaluation" / arm / task_id / f"trial-{trial}.json"


def update_marker(arm: str, task_id: str, trial: int) -> pathlib.Path:
    return RUN / "evaluation_updates" / arm / task_id / f"trial-{trial}.json"


def update_live_summary(spec: dict[str, Any], stage: str, last_error: str | None = None) -> None:
    acq = list((RUN / "acquisition").glob("*.json"))
    eval_rows: list[dict[str, Any]] = []
    for path in (RUN / "evaluation").glob("*/*/*.json"):
        try: eval_rows.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception: continue
    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in eval_rows: by_arm[str(row.get("arm"))].append(row)
    calls = defaultdict(lambda: {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0, "latency_seconds": 0.0})
    if PROGRESS.exists():
        for line in PROGRESS.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("event") != "call_settled": continue
            role = str(row.get("role", "")); arm = next((name for name in spec["arms"] if name in role), "acquisition_or_lifecycle")
            item = calls[arm]; item["calls"] += 1; item["prompt_tokens"] += int(row.get("prompt_tokens") or 0)
            item["completion_tokens"] += int(row.get("completion_tokens") or 0); item["cost_usd"] += float(row.get("cost") or 0); item["latency_seconds"] += float(row.get("latency") or 0)
    write_json(SUMMARY, {"stage": stage, "status": "running", "acquisition_completed": len(acq),
        "acquisition_expected": 8, "evaluation_completed": len(eval_rows), "evaluation_expected": 320,
        "per_arm_completed": {name: len(by_arm[name]) for name in spec["arms"]},
        "per_arm_avg_score": {name: (sum(float(x["after_score"]) for x in by_arm[name]) / len(by_arm[name]) if by_arm[name] else None) for name in spec["arms"]},
        "calls_tokens_latency_cost": dict(calls), "c_free_gb": c_free_gb(), "last_recoverable_error": last_error})


def load_or_run(*, spec: dict[str, Any], ledger: AppendOnlyLedger, api_key: str, kwargs: dict[str, Any], path: pathlib.Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if c_free_gb() < 5.0:
        raise RuntimeError("C-drive floor would be breached before dispatch")
    return execute_trajectory(**kwargs, artifact_path=path)


def reme_input(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"trajectory_id": row["acquisition_identity"], "task_id": row["task_id"],
             "task_history": row["history"], "after_score": row["after_score"]} for row in rows]


def make_copro(state: dict[str, Any]) -> CoProMemAppWorldAdapter:
    value = CoProMemAppWorldAdapter(api_key="", model="deepseek/deepseek-v4.1-flash",
                                    provider_only="deepseek", reasoning_effort="none", decomposition_call_cap=320)
    value.clone_from_state(state)
    return value


def nonempty_memory_list(response: dict[str, Any]) -> list[dict[str, Any]]:
    value = response.get("memory_list") or (response.get("metadata") or {}).get("memory_list") or []
    return value if isinstance(value, list) and all(isinstance(item, dict) for item in value) else []


def validate_retrieval(*, rows: list[dict[str, Any]], reme_url: str, copro: CoProMemAppWorldAdapter) -> dict[str, Any]:
    selected: dict[str, dict[str, Any]] = {}
    for row in rows:
        selected.setdefault(str(row["task_id"])[:7], row)
    reme_hashes, copro_hashes, reme_nonempty, copro_nonempty = set(), set(), set(), set()
    for family, row in list(selected.items())[:8]:
        result = official_post(reme_url, "retrieve_task_memory", {"query": row["instruction"], "enable_llm_rerank": False,
                      "enable_score_filter": False, "top_k": 5, "enable_llm_rewrite": False})
        memories = nonempty_memory_list(result)
        if memories:
            reme_nonempty.add(family); reme_hashes.add(digest(memories))
        guidance = copro.prepare_trial(TrialInput(str(row["task_id"]), str(row["instruction"]), "appworld", base_prompt=str(row["instruction"])), 0)
        if guidance.strip():
            copro_nonempty.add(family); copro_hashes.add(hashlib.sha256(guidance.encode()).hexdigest())
    audit = {"reme_nonempty_families": sorted(reme_nonempty), "copromem_nonempty_families": sorted(copro_nonempty),
             "reme_distinct_hashes": len(reme_hashes), "copromem_distinct_hashes": len(copro_hashes)}
    if len(reme_nonempty) < 2 or len(copro_nonempty) < 2 or len(reme_hashes) < 2 or len(copro_hashes) < 2:
        raise RuntimeError("retrieval coverage gate failed")
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--preflight", action="store_true"); args = parser.parse_args()
    spec = read_manifest()
    if c_free_gb() < 5.0: raise RuntimeError("C-drive floor is below 5 GB")
    RUN.mkdir(parents=True, exist_ok=True); acquire_lock(); ledger = bootstrap_ledger(spec)
    api_key = env_value("OPENROUTER_API_KEY")
    append(PROGRESS, {"event": "runner_preflight", "manifest_sha256": MANIFEST_SHA.read_text().strip(), "c_free_gb": c_free_gb()})
    status("preflight", c_free_gb=c_free_gb(), registered_bound=spec["budget"]["all_in_usd"]); update_live_summary(spec, "preflight")
    if args.preflight:
        with services(RUN, LEDGER, PROGRESS, float(spec["budget"]["ledger_dispatch_cap_usd"]), ["preflight"]): pass
        status("preflight_passed", c_free_gb=c_free_gb()); update_live_summary(spec, "preflight_passed"); return

    carry = verify_v1()
    new_rows: list[dict[str, Any]] = []
    for task_id in spec["acquisition"]["new_task_ids"]:
        new_rows.extend(acquisition_pool(run=RUN, progress=PROGRESS, ledger=ledger, api_key=api_key,
            acquisition_ids=[task_id], evaluation_ids=spec["evaluation"]["task_ids"], seeds=spec["acquisition"]["new_seeds"],
            max_actions=spec["limits"]["actions"], temperature=spec["limits"]["temperature"]))
        update_live_summary(spec, "acquisition")
    combined = carry + new_rows
    gate = acquisition_gate(combined, expected_records=32, fail_closed=False)
    write_json(RUN / "acquisition" / "combined-gate.json", gate); append(PROGRESS, {"event": "acquisition_gate", **gate})
    update_live_summary(spec, "acquisition_gate")
    if not gate["passed"]:
        status("no_go_acquisition", **gate); raise RuntimeError("preregistered combined acquisition gate failed")

    all_ids = spec["acquisition"]["new_task_ids"] + spec["evaluation"]["task_ids"]
    snapshot, checkpoint = RUN / "reme/shared-bank.jsonl", RUN / "reme/construction.jsonl"
    cap = float(spec["budget"]["ledger_dispatch_cap_usd"])
    names = ["reme-builder", "reme-fixed", "reme-dynamic-1", "reme-dynamic-2", "reme-dynamic-3", "reme-dynamic-4"]
    with services(RUN, LEDGER, PROGRESS, cap, names) as svc:
        bank_hash, count = construct_once(official_post, svc["reme-builder"].base_url, reme_input(combined), checkpoint, snapshot, lambda event: append(PROGRESS, event))
        if count != 32: raise RuntimeError("ReMe initial bank did not consume all 32 frozen trajectories")
        copro_state, copro_hash = construct_copromem(run=RUN, progress=PROGRESS, ledger=ledger, api_key=api_key, raw=raw_acquisition_trajectories(combined))
        write_json(RUN / "lifecycle/initial-state.json", {"reme_bank_sha256": bank_hash, "copromem_state_sha256": copro_hash})
        if load_clone(official_post, svc["reme-fixed"].base_url, snapshot, bank_hash) != bank_hash: raise RuntimeError("ReMe fixed clone mismatch")
        for trial in spec["evaluation"]["trial_ids"]:
            if load_clone(official_post, svc[f"reme-dynamic-{trial}"].base_url, snapshot, bank_hash) != bank_hash: raise RuntimeError("ReMe dynamic clone mismatch")
            dynamic_snapshot = RUN / "reme" / f"dynamic-trial-{trial}.jsonl"
            if dynamic_snapshot.exists():
                official_post(svc[f"reme-dynamic-{trial}"].base_url, "load_memory", {"load_file_path": str(dynamic_snapshot), "clear_existing": True})
        copro_fixed = make_copro(copro_state); copro_dynamic = {trial: make_copro(copro_state) for trial in spec["evaluation"]["trial_ids"]}
        for trial, adapter in copro_dynamic.items():
            dynamic_snapshot = RUN / "copromem" / f"dynamic-trial-{trial}.json"
            if dynamic_snapshot.exists():
                adapter.clone_from_state(json.loads(dynamic_snapshot.read_text(encoding="utf-8")))
        if copro_fixed.semantic_state_hash() != copro_hash or any(x.semantic_state_hash() != copro_hash for x in copro_dynamic.values()): raise RuntimeError("CoProMem initial clone mismatch")
        retrieval = validate_retrieval(rows=combined, reme_url=svc["reme-fixed"].base_url, copro=copro_fixed)
        write_json(RUN / "lifecycle/retrieval-gate.json", retrieval); append(PROGRESS, {"event": "retrieval_gate_passed", **retrieval})
        for task_id in spec["evaluation"]["task_ids"]:
            for trial in spec["evaluation"]["trial_ids"]:
                seed = 9100 + trial
                base = {"run": RUN, "progress": PROGRESS, "ledger": ledger, "api_key": api_key, "all_task_ids": all_ids, "task_id": task_id, "trial_id": trial, "seed": seed, "max_actions": spec["limits"]["actions"], "temperature": spec["limits"]["temperature"], "phase": "evaluation"}
                load_or_run(spec=spec, ledger=ledger, api_key=api_key, kwargs={**base, "arm": "no_memory"}, path=artifact("no_memory", task_id, trial))
                load_or_run(spec=spec, ledger=ledger, api_key=api_key, kwargs={**base, "arm": "official_upstream_reme_fixed", "memory_base_url": svc["reme-fixed"].base_url}, path=artifact("official_upstream_reme_fixed", task_id, trial))
                dynamic_service = svc[f"reme-dynamic-{trial}"]
                marker = update_marker("official_upstream_reme_dynamic", task_id, trial)
                reme_path = artifact("official_upstream_reme_dynamic", task_id, trial)
                if reme_path.exists() and not marker.exists():
                    raise RuntimeError("scored ReMe dynamic trajectory lacks durable update marker; replay is forbidden")
                def reme_update(agent: Any, result: dict[str, Any]) -> None:
                    outcome = dynamic_post_trial_update(agent, result["after_score"], lambda event: append(PROGRESS, {**event, "trajectory_id": result["trajectory_id"]}))
                    snapshot_path = RUN / "reme" / f"dynamic-trial-{trial}.jsonl"
                    official_post(dynamic_service.base_url, "dump_memory", {"dump_file_path": str(snapshot_path)})
                    write_json(marker, {"trajectory_id": result["trajectory_id"], "outcome": outcome, "after_score": result["after_score"], "snapshot_sha256": hashlib.sha256(snapshot_path.read_bytes()).hexdigest()})
                reme_result = load_or_run(spec=spec, ledger=ledger, api_key=api_key, kwargs={**base, "arm": "official_upstream_reme_dynamic", "memory_base_url": dynamic_service.base_url, "post_score_update": reme_update}, path=reme_path)
                if not marker.exists(): raise RuntimeError("ReMe dynamic post-score update did not finish")
                def fixed_memory(intent: str, domain: str, meta: dict[str, Any]) -> str:
                    return copro_fixed.prepare_trial(TrialInput(task_id, intent, domain, base_prompt=intent), trial)
                load_or_run(spec=spec, ledger=ledger, api_key=api_key, kwargs={**base, "arm": "copromem_fixed", "memory_for_instruction": fixed_memory}, path=artifact("copromem_fixed", task_id, trial))
                dynamic_copro = copro_dynamic[trial]
                def dynamic_memory(intent: str, domain: str, meta: dict[str, Any]) -> str:
                    return dynamic_copro.prepare_trial(TrialInput(task_id, intent, domain, base_prompt=intent), trial)
                marker = update_marker("copromem_dynamic", task_id, trial)
                copro_path = artifact("copromem_dynamic", task_id, trial)
                if copro_path.exists() and not marker.exists():
                    raise RuntimeError("scored CoProMem dynamic trajectory lacks durable update marker; replay is forbidden")
                def copro_update(agent: Any, result: dict[str, Any]) -> None:
                    intent = next(item["content"] for item in result["history"] if item["role"] == "user")
                    trial_input = TrialInput(task_id, intent, "appworld", base_prompt=intent)
                    actions = [item["content"] for item in result["history"] if item["role"] == "assistant"]
                    before = dynamic_copro.semantic_state_hash(); dynamic_copro.record_scored_trial(trial_input, trial, success=result["after_score"] == 1.0, actions=actions, state_hash=before, seed=seed)
                    snapshot_path = RUN / "copromem" / f"dynamic-trial-{trial}.json"
                    write_json(snapshot_path, dynamic_copro.export_state())
                    write_json(marker, {"trajectory_id": result["trajectory_id"], "before_state_sha256": before, "after_state_sha256": dynamic_copro.semantic_state_hash(), "after_score": result["after_score"]})
                copro_result = load_or_run(spec=spec, ledger=ledger, api_key=api_key, kwargs={**base, "arm": "copromem_dynamic", "memory_for_instruction": dynamic_memory, "post_score_update": copro_update}, path=copro_path)
                if not marker.exists(): raise RuntimeError("CoProMem dynamic post-score update did not finish")
                update_live_summary(spec, "evaluation")
    update_live_summary(spec, "reporting")
    report = ROOT / "research/scripts/build_corrected_fixed_dynamic_report.py"
    subprocess.run([sys.executable, str(report)], cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT), "CORRECTED_FIXED_DYNAMIC_RUN": str(RUN)}, check=True)
    final = RUN / "final-report.json"
    if not final.exists(): raise RuntimeError("final report missing")
    status("completed", final_report=str(final), final_report_sha256=hashlib.sha256(final.read_bytes()).hexdigest(), c_free_gb=c_free_gb())
    update_live_summary(spec, "completed")


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        RUN.mkdir(parents=True, exist_ok=True)
        append(PROGRESS, {"event": "runner_failed", "error_type": type(exc).__name__, "error": str(exc)[:240]})
        if MANIFEST.exists(): status("failed", error_type=type(exc).__name__, error=str(exc)[:240])
        raise
