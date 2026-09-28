#!/usr/bin/env python3
"""Restart-safe four-arm AppWorld runner with continuous CoProMem memory.

The runner deliberately contains no historical acquisition, task, result, or
report path.  A user supplies a run directory and a frozen acquisition export
through environment variables; those local evidence files stay out of Git.
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
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from multiprocessing import get_context
from typing import Any

ROOT = pathlib.Path(os.environ.get("COPROMEM_ROOT", pathlib.Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(ROOT))
from ...integrations.reme.lifecycle import dynamic_post_trial_update
from .runner import append, decomposition_json_call, digest, execute_trajectory, official_post, services, v5_budget_bound, write_json
from ...integrations.reme.transport import AppendOnlyLedger
from ...integrations.reme.bank import construct_once, load_clone
from ...benchmarks.appworld.adapter import CoProMemAppWorldAdapter, TrialInput
from .task_boundary import POLICY_VERSION

RUN = pathlib.Path(os.environ.get(
    "COPROMEM_RUN_DIR", ROOT / "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v5"
))
MANIFEST, MANIFEST_SHA = RUN / "manifest.json", RUN / "manifest.sha256"
PROGRESS, LEDGER, STATUS, SUMMARY = (RUN / "progress.jsonl", RUN / "ledger.jsonl",
                                     RUN / "runner-status.json", RUN / "live-summary.json")


def file_sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def c_free_gb() -> float:
    stat = os.statvfs(os.environ.get("COPROMEM_DISK_FLOOR_PATH", str(RUN)))
    return stat.f_bavail * stat.f_frsize / 1024 ** 3


def env_value(name: str) -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.split("=", 1)[0].strip() == name and "=" in line:
            value = line.split("=", 1)[1].strip().strip("'\"")
            if value:
                return value
    raise RuntimeError(f"required credential {name} is absent")


def frozen_acquisition_pool(value: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Load an explicitly supplied, already-frozen acquisition export.

    This keeps raw trajectories outside source control and prevents the
    maintained runner from reaching into any previous experiment directory.
    """
    source = os.environ.get("COPROMEM_ACQUISITION_POOL")
    if not source:
        raise RuntimeError("COPROMEM_ACQUISITION_POOL must name a frozen acquisition export")
    if value is not None and file_sha(pathlib.Path(source)) != value["acquisition"]["export_sha256"]:
        raise RuntimeError("frozen acquisition export hash mismatch")
    raw = json.loads(pathlib.Path(source).read_text(encoding="utf-8"))
    rows = raw.get("trajectories") if isinstance(raw, dict) else raw
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("frozen acquisition export must contain a non-empty trajectory list")
    required = {"acquisition_identity", "task_id", "history", "after_score"}
    if any(not isinstance(row, dict) or not required.issubset(row) for row in rows):
        raise RuntimeError("frozen acquisition export lacks required provenance fields")
    if len({row["acquisition_identity"] for row in rows}) != len(rows):
        raise RuntimeError("duplicate acquisition trajectory identity")
    if value is not None and set(row["task_id"] for row in rows) & set(value["evaluation"]["task_ids"]):
        raise RuntimeError("acquisition and evaluation task IDs overlap")
    return rows


def reme_input(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map frozen public trajectories into the pinned upstream ReMe contract."""
    return [{"trajectory_id": row["acquisition_identity"], "task_id": row["task_id"],
             "task_history": row["history"], "after_score": row["after_score"]} for row in rows]


def spec() -> dict[str, Any]:
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    raw = json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    if file_sha(MANIFEST) != MANIFEST_SHA.read_text().strip() or hashlib.sha256(raw).hexdigest() != file_sha(MANIFEST):
        raise RuntimeError("v5 frozen manifest hash mismatch")
    if (value.get("protocol") != "continuous_copromem_v5" or value.get("status") != "frozen_pre_payload"
            or not value.get("evaluation", {}).get("task_ids")
            or value.get("arms") != ["no_memory", "official_upstream_reme_fixed",
                                     "official_upstream_reme_dynamic", "copromem_dynamic"]
            or not value.get("budget", {}).get("fits_hard_cap")
            or float(value["budget"].get("hard_cap_usd", 0)) <= 0):
        raise RuntimeError("frozen protocol invariant failed")
    budget = value["budget"]
    bound = v5_budget_bound(call_limits=budget.get("call_limits", {}),
                            historical_usd=float(budget.get("historical_charged_or_reserved_usd", 0.0)))
    for key, expected in bound.items():
        if key not in budget or abs(float(budget[key]) - float(expected)) > 1e-12:
            raise RuntimeError(f"frozen v5 budget field is inconsistent: {key}")
    if (float(budget["ledger_dispatch_cap_usd"]) != float(bound["dispatchable_usd"])
            or bool(budget["fits_hard_cap"]) != (float(bound["all_in_usd"]) <= float(budget["hard_cap_usd"]))):
        raise RuntimeError("frozen v5 budget or non-dispatchable contingency is inconsistent")
    evaluation = value["evaluation"]
    if (len(evaluation.get("trial_ids", ())) != len(evaluation.get("seeds", ()))
            or evaluation.get("expected_trajectories") !=
            4 * len(evaluation["task_ids"]) * len(evaluation.get("trial_ids", ()))):
        raise RuntimeError("continuous run task, trial, seed, or arm count mismatch")
    source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if source_commit != value.get("git_commit"):
        raise RuntimeError("running source commit differs from frozen manifest")
    changed = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no", "--", "src", "scripts"],
        cwd=ROOT, text=True).strip()
    if changed:
        raise RuntimeError("tracked runtime source differs from frozen commit")
    dependencies = value.get("dependency_files_sha256")
    if not isinstance(dependencies, dict) or not dependencies:
        raise RuntimeError("v5 manifest must pin external dependency files")
    for path, expected in dependencies.items():
        if file_sha(pathlib.Path(path)) != expected:
            raise RuntimeError(f"dependency file hash mismatch: {path}")
    return value


def task_descriptor(value: dict[str, Any], task_id: str):
    """Only manifest-pinned, pre-execution structure may drive retrieval."""
    from ...learning import ActionObservation
    raw = value.get("evaluation", {}).get("descriptors", {}).get(task_id)
    if not isinstance(raw, list):
        raise RuntimeError(f"missing public structural descriptor for {task_id}")
    events = tuple(ActionObservation(**item) for item in raw)
    if any(event.check or event.parameters or not event.observed for event in events):
        raise RuntimeError("task descriptor contains post-execution evidence")
    return events


def descriptor_audit(value: dict[str, Any], state: dict[str, Any]) -> dict[str, str]:
    """Make initial exact-signature coverage explicit before paid evaluation."""
    adapter = CoProMemAppWorldAdapter(api_key="")
    adapter.clone_from_state(state)
    result = {}
    expectations = value.get("evaluation", {}).get("expected_initial_compatibility", {})
    for task_id in value["evaluation"]["task_ids"]:
        compatibility = adapter.module.learning.retrieve("appworld", task_descriptor(value, task_id)).compatibility
        result[task_id] = compatibility
        if task_id in expectations and compatibility != expectations[task_id]:
            raise RuntimeError(f"initial descriptor compatibility mismatch for {task_id}: {compatibility}")
    return result


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
    call_limits = value["budget"]["call_limits"]
    os.environ["OFFICIAL_PILOT_CALL_LIMITS"] = json.dumps(call_limits, sort_keys=True, separators=(",", ":"))
    ledger = AppendOnlyLedger(LEDGER, float(value["budget"]["ledger_dispatch_cap_usd"]), call_limits)
    carry = float(value["budget"]["historical_charged_or_reserved_usd"])
    identifier = f"historical-carry-forward-usd-{carry:.12f}"
    known = LEDGER.read_text(encoding="utf-8") if LEDGER.exists() else ""
    if identifier not in known:
        ledger.reserve(identifier, carry, {"role": "historical_carry_forward", "source": "prior_append_only_ledger"})
    return ledger


def artifact(arm: str, task_id: str, trial: int) -> pathlib.Path:
    return RUN / "evaluation" / arm / task_id / f"trial-{trial}.json"


def verify_existing_artifact(path: pathlib.Path, arm: str, task_id: str, trial: int) -> dict[str, Any]:
    """Validate a completed trajectory using the executor's single digest.

    This intentionally imports ``five_arm_runner.digest`` rather than
    restating JSON options at a recovery call site.
    """
    row = json.loads(path.read_text(encoding="utf-8"))
    if (row.get("arm"), row.get("task_id"), row.get("trial_id")) != (arm, task_id, trial):
        raise RuntimeError("completed trajectory artifact identity mismatch")
    history = row.get("history")
    if not isinstance(history, list) or digest(history) != row.get("history_sha256"):
        raise RuntimeError("completed trajectory canonical history hash mismatch")
    if not isinstance(row.get("after_score"), (int, float)):
        raise RuntimeError("completed trajectory lacks official scorer result")
    return row


def marker(arm: str, task_id: str, trial: int) -> pathlib.Path:
    return RUN / "evaluation_updates" / arm / task_id / f"trial-{trial}.json"


def verify_update_marker(path: pathlib.Path, result: dict[str, Any], scored_path: pathlib.Path) -> None:
    record = json.loads(path.read_text(encoding="utf-8"))
    if (record.get("trajectory_id") != result["trajectory_id"]
            or record.get("scored_artifact_sha256") != file_sha(scored_path)):
        raise RuntimeError("dynamic update marker does not match scored trajectory")


def _trajectory_cost(role: str) -> float:
    """Read settled provider cost for one registered executor trajectory."""
    if not LEDGER.exists():
        return 0.0
    roles, settled = {}, {}
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("event") == "reserve":
            roles[row["id"]] = row.get("role")
        elif row.get("event") == "settle":
            settled[row["id"]] = float(row["usd"])
    outstanding = {call_id for call_id, owner in roles.items()
                   if owner == role and call_id not in settled}
    if outstanding:
        raise RuntimeError(f"trajectory {role} has unsettled cost reservations")
    return sum(cost for call_id, cost in settled.items() if roles.get(call_id) == role)


def complete_copro_task(adapter: CoProMemAppWorldAdapter, task_id: str,
                        trials: list[int], seeds: list[int], descriptor: list[dict[str, Any]] | None = None,
                        policy_version: str = POLICY_VERSION, public_registry: dict[str, Any] | None = None) -> None:
    """Transactionally merge one scored winner after every trial is durable."""
    from ...benchmarks.appworld.adapter import AcquisitionIdentity, RawAcquisitionTrajectory, normalize_appworld_history
    from ...learning import ActionObservation
    from ...benchmarks.appworld.execution_evidence import journal_records, learning_events
    from .task_boundary import (POLICY_VERSION, commit_task_boundary_plan,
                                plan_task_boundary_update, validate_task_boundary_plan,
                                EXECUTION_EVIDENCE_POLICY_VERSION)
    pre_path = RUN / "copromem/task_pre_states" / f"{task_id}.json"
    pre = json.loads(pre_path.read_text(encoding="utf-8"))
    marker_path = RUN / "copromem/task_updates" / f"{task_id}.json"
    pending_path = RUN / "copromem/task_updates_pending" / f"{task_id}.json"
    if marker_path.exists():
        marker_row = json.loads(marker_path.read_text(encoding="utf-8"))
        if marker_row["before_state_sha256"] != digest(pre):
            raise RuntimeError("CoProMem task merge pre-state changed")
        if marker_row["scored_artifact_sha256"] != {
            str(trial): file_sha(artifact("copromem_dynamic", task_id, trial))
            for trial in trials
        }:
            raise RuntimeError("CoProMem scored artifact changed after task merge")
        if marker_row["retrieval_artifact_sha256"] != {
            str(trial): file_sha(RUN / "retrieval/copromem_dynamic" / task_id / f"trial-{trial}.json")
            for trial in trials
        }:
            raise RuntimeError("CoProMem retrieval provenance changed after task merge")
        if marker_row.get("state") == "rejected":
            if marker_row.get("after_state_sha256") != digest(pre):
                raise RuntimeError("rejected CoProMem task changed retrieval state")
            adapter.clone_from_state(pre)
            return
        saved = json.loads((RUN / "copromem/task_states" / f"{task_id}.json").read_text(encoding="utf-8"))
        if marker_row.get("state") != "committed" or marker_row["after_state_sha256"] != digest(saved):
            raise RuntimeError("CoProMem task merge marker changed")
        adapter.clone_from_state(saved)
        return
    # All scorer and retrieval inputs are durable before the state-changing
    # merge.  A separately retained pending record makes an interruption
    # between writing the state snapshot and committing the update marker
    # auditable and replay-free: reconstruction below is pure local state
    # work over those completed artifacts.
    adapter.clone_from_state(pre)
    trial_inputs = []
    artifact_hashes = {}
    retrieval_hashes = {}
    for trial, seed in zip(trials, seeds):
        scored_path = artifact("copromem_dynamic", task_id, trial)
        row = verify_existing_artifact(scored_path, "copromem_dynamic", task_id, trial)
        baseline = verify_existing_artifact(artifact("no_memory", task_id, trial), "no_memory", task_id, trial)
        retrieval_path = RUN / "retrieval/copromem_dynamic" / task_id / f"trial-{trial}.json"
        provenance = json.loads(retrieval_path.read_text(encoding="utf-8"))["provenance"]
        if provenance["pre_state_sha256"] != digest(pre):
            raise RuntimeError("parallel CoProMem trials used different task snapshots")
        intent = next(x["content"] for x in row["history"] if x["role"] == "user")
        actions = tuple(x["content"] for x in row["history"] if x["role"] == "assistant")
        success = float(row["after_score"]) == 1.0
        evidence_audit: dict[str, Any] | None = None
        if policy_version == EXECUTION_EVIDENCE_POLICY_VERSION:
            evidence_name = row.get("execution_evidence_path")
            if not isinstance(evidence_name, str) or not evidence_name:
                raise RuntimeError("execution-evidence task merge lacks durable telemetry path")
            records = journal_records(evidence_name)
            evidence_rows, evidence_audit = learning_events(records, str(public_registry["registry_sha256"]))
            events = tuple(ActionObservation(
                operation=str(event["operation"]), input_slots=tuple(event["input_slots"]),
                output_slots=tuple(event["output_slots"]), precondition=str(event.get("precondition", "")),
                check=str(event["check"]), parameters={}, observed=bool(event["observed"]))
                for event in evidence_rows)
        else:
            events = normalize_appworld_history(row["history"], success)
        trajectory = RawAcquisitionTrajectory(
            AcquisitionIdentity(task_id, seed, trial), intent, "appworld", success,
            actions, {"evaluation": True, "scored_artifact_sha256": file_sha(scored_path)},
            events=events)
        role = f"executor:copromem_dynamic:{task_id}:trial={trial}:seed={seed}"
        trial_inputs.append({"task_id": task_id, "seed": seed, "trajectory_index": trial,
            "intent": intent, "score": float(row["after_score"]), "no_memory_score": float(baseline["after_score"]),
            "cost_usd": _trajectory_cost(role), "actions": int(row["actions"]), "actions_text": list(actions),
            "task_state": {"evaluation": True, "scored_artifact_sha256": file_sha(scored_path),
                           **({"execution_evidence_audit": evidence_audit} if evidence_audit is not None else {})},
            "events": [asdict(event) for event in trajectory.events],
            "scored_artifact_sha256": file_sha(scored_path), "retrieval_artifact_sha256": file_sha(retrieval_path)})
        artifact_hashes[str(trial)] = file_sha(scored_path)
        retrieval_hashes[str(trial)] = file_sha(retrieval_path)
    plan = plan_task_boundary_update(pre, descriptor or [], trial_inputs, policy_version, public_registry)
    validation = validate_task_boundary_plan(plan)
    pending = {"state": "prepared", "task_id": task_id,
               "before_state_sha256": digest(pre),
               "scored_artifact_sha256": artifact_hashes,
               "retrieval_artifact_sha256": retrieval_hashes,
               "plan": plan, "plan_sha256": plan["plan_sha256"], "validation": validation}
    if pending_path.exists():
        prior_pending = json.loads(pending_path.read_text(encoding="utf-8"))
        if prior_pending != pending:
            raise RuntimeError("CoProMem pending task merge inputs changed")
    else:
        write_json(pending_path, pending)
    updated, validation = commit_task_boundary_plan(pre, plan)
    if not validation["passed"]:
        adapter.clone_from_state(pre)
        write_json(marker_path, {"state": "rejected", "task_id": task_id,
            "before_state_sha256": digest(pre), "after_state_sha256": digest(pre),
            "scored_artifact_sha256": artifact_hashes, "retrieval_artifact_sha256": retrieval_hashes,
            "pending_update_sha256": file_sha(pending_path), "plan_sha256": plan["plan_sha256"],
            "validation": validation, "winner_episode_id": None})
        return
    winner = validation["winner_episode_id"]
    # ``commit_task_boundary_plan`` is pure; make the caller's mutable stream
    # reflect the now-durable committed snapshot only after validation passed.
    adapter.clone_from_state(updated)
    state_path = RUN / "copromem/task_states" / f"{task_id}.json"
    if state_path.exists():
        if digest(json.loads(state_path.read_text(encoding="utf-8"))) != digest(updated):
            raise RuntimeError("CoProMem interrupted task merge state changed")
    else:
        write_json(state_path, updated)
    shared_path = RUN / "copromem/shared-state.json"
    if shared_path.exists():
        shared_hash = digest(json.loads(shared_path.read_text(encoding="utf-8")))
        if shared_hash not in {digest(pre), digest(updated)}:
            raise RuntimeError("CoProMem shared state is inconsistent with task merge")
    write_json(shared_path, updated)
    write_json(marker_path, {"state": "committed", "task_id": task_id, "before_state_sha256": digest(pre),
                             "after_state_sha256": digest(updated),
                             "scored_artifact_sha256": artifact_hashes,
                             "retrieval_artifact_sha256": retrieval_hashes,
                             "pending_update_sha256": file_sha(pending_path),
                             "plan_sha256": plan["plan_sha256"], "validation": validation,
                             "winner_episode_id": winner})


def copro_retrieval(arm: str, adapter: CoProMemAppWorldAdapter, task_id: str,
                   trial: int, descriptor=()):
    path = RUN / "retrieval" / arm / task_id / f"trial-{trial}.json"
    def call(intent: str, domain: str, _: dict[str, Any]) -> str:
        if path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            provenance = record.get("provenance")
            expected_input = {"task_id": task_id, "trial_stream": trial, "intent": intent,
                              "domain": domain, "sites": [], "start_url": "", "base_prompt": intent,
                              "structural_events": [asdict(event) for event in descriptor]}
            if (not isinstance(provenance, dict) or not isinstance(provenance.get("task_input"), dict) or
                    record.get("arm") != arm or record.get("task_id") != task_id or record.get("trial") != trial or
                    provenance["task_input"] != expected_input or
                    CoProMemAppWorldAdapter._digest(provenance["task_input"]) != provenance.get("task_input_sha256")):
                raise RuntimeError("persisted CoProMem retrieval provenance is invalid")
            if adapter.semantic_state_hash() != provenance.get("pre_state_sha256"):
                raise RuntimeError("CoProMem restart state does not match persisted retrieval pre-state")
            guidance = CoProMemAppWorldAdapter.reproduce_retrieval(provenance["pre_state"], provenance["task_input"], provenance)
            if hashlib.sha256(guidance.encode("utf-8")).hexdigest() != provenance.get("guidance_sha256"):
                raise RuntimeError("persisted CoProMem guidance hash mismatch")
            return guidance
        before = adapter.semantic_state_hash()
        guidance, provenance = adapter.retrieve_with_provenance(
            TrialInput(task_id, intent, domain, base_prompt=intent,
                       structural_events=tuple(descriptor)), trial)
        reproduced = CoProMemAppWorldAdapter.reproduce_retrieval(provenance["pre_state"], provenance["task_input"], provenance)
        if guidance != reproduced or hashlib.sha256(guidance.encode("utf-8")).hexdigest() != provenance["guidance_sha256"]:
            raise RuntimeError("CoProMem guidance cannot be reproduced offline")
        write_json(path, {"task_id": task_id, "trial": trial, "arm": arm, "pre_state_sha256": before,
                          "post_state_sha256": adapter.semantic_state_hash(), "guidance_sha256": provenance["guidance_sha256"],
                          "provenance": provenance})
        return guidance
    return call


def preflight(value: dict[str, Any]) -> dict[str, str]:
    if c_free_gb() < 5.0:
        raise RuntimeError("configured disk is below frozen 5 GiB floor")
    for name in ("COPROMEM_REME_PYTHON", "COPROMEM_REME_SOURCE",
                 "COPROMEM_APPWORLD_PYTHON", "COPROMEM_APPWORLD_ROOT"):
        configured = os.environ.get(name)
        if not configured or not pathlib.Path(configured).exists():
            raise RuntimeError(f"required v5 runtime path {name} is not configured or absent")
    acquisition = frozen_acquisition_pool(value)
    gate_path = RUN / "copromem/acquisition-retrieval-gate.json"
    if file_sha(gate_path) != value["acquisition"]["retrieval_gate_sha256"]:
        raise RuntimeError("warm-start audit hash mismatch")
    gate = json.loads(gate_path.read_text())
    state = json.loads((RUN / "copromem/initial-state.json").read_text())
    from .gate import build_gate
    expected = build_gate(state, acquisition)
    if (gate != expected or not expected["passed"]
            or digest(state) != value["acquisition"]["copromem_bank_sha256"]):
        raise RuntimeError("warm-start audit or bank hash mismatch")
    coverage = descriptor_audit(value, state)
    write_json(RUN / "copromem/descriptor-audit.json", coverage)
    append(PROGRESS, {"event": "warm_start_preflight_passed",
                      "manifest_sha256": MANIFEST_SHA.read_text().strip(),
                      "bank_sha256": digest(state), "c_free_gb": c_free_gb(),
                      "descriptor_compatibility": coverage})
    return coverage


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


def run_copro_trial(task_id: str, trial: int, seed: int, descriptor_raw: list[dict[str, Any]],
                    pre_state: dict[str, Any], all_ids: list[str], key: str,
                    cap: float) -> dict[str, Any]:
    """One process per trial: upstream agent construction mutates module globals."""
    from ...learning import ActionObservation
    adapter = CoProMemAppWorldAdapter(api_key="")
    adapter.clone_from_state(pre_state)
    scored_path = artifact("copromem_dynamic", task_id, trial)
    if scored_path.exists():
        return verify_existing_artifact(scored_path, "copromem_dynamic", task_id, trial)
    ledger = AppendOnlyLedger(LEDGER, cap)
    return execute_trajectory(
        run=RUN, progress=PROGRESS, ledger=ledger, api_key=key,
        all_task_ids=all_ids, arm="copromem_dynamic", task_id=task_id,
        trial_id=trial, seed=seed, max_actions=30, temperature=0.7,
        phase="evaluation", artifact_path=scored_path,
        memory_for_instruction=copro_retrieval(
            "copromem_dynamic", adapter, task_id, trial,
            tuple(ActionObservation(**item) for item in descriptor_raw)))


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--preflight", action="store_true"); args = parser.parse_args()
    value = spec(); RUN.mkdir(parents=True, exist_ok=True); acquire_lock(); ledger = bootstrap_ledger(value)
    coverage = preflight(value)
    status("preflight_passed", c_free_gb=c_free_gb(), budget=value["budget"],
           descriptor_compatibility=coverage)
    summary(value, "preflight_passed")
    if args.preflight: return
    key = env_value("OPENROUTER_API_KEY")
    combined = frozen_acquisition_pool(value)
    expected_acquisition = int(value.get("acquisition", {}).get("expected_trajectories", len(combined)))
    if len(combined) != expected_acquisition:
        raise RuntimeError("frozen acquisition source count does not match manifest")
    state = json.loads((RUN / "copromem/initial-state.json").read_text())
    bank_hash = digest(state)
    cap = float(value["budget"]["ledger_dispatch_cap_usd"])
    names = ["reme-builder", "reme-fixed"] + [f"reme-dynamic-{x}" for x in value["evaluation"]["trial_ids"]]
    with services(RUN, LEDGER, PROGRESS, cap, names, lifecycle_input_ceiling=131072) as svc:
        snapshot, checkpoint = RUN / "reme/shared-bank.jsonl", RUN / "reme/construction.jsonl"
        reme_hash, count = construct_once(official_post, svc["reme-builder"].base_url, reme_input(combined), checkpoint, snapshot,
                                          progress_event_callback(PROGRESS))
        if count != len(combined): raise RuntimeError("official ReMe construction did not consume every frozen input")
        if load_clone(official_post, svc["reme-fixed"].base_url, snapshot, reme_hash) != reme_hash: raise RuntimeError("ReMe fixed clone mismatch")
        for trial in value["evaluation"]["trial_ids"]:
            service = svc[f"reme-dynamic-{trial}"]
            if load_clone(official_post, service.base_url, snapshot, reme_hash) != reme_hash: raise RuntimeError("ReMe dynamic clone mismatch")
            saved = RUN / "reme" / f"dynamic-trial-{trial}.jsonl"
            if saved.exists(): official_post(service.base_url, "load_memory", {"load_file_path": str(saved), "clear_existing": True})
        shared = CoProMemAppWorldAdapter(api_key="")
        shared.clone_from_state(state)
        all_ids = value["evaluation"]["task_ids"]
        trials = list(value["evaluation"]["trial_ids"])
        seeds = list(value["evaluation"]["seeds"])
        if len(trials) != len(seeds):
            raise RuntimeError("trial and seed counts differ")
        for task_id in all_ids:
            descriptor = task_descriptor(value, task_id)
            pre_path = RUN / "copromem/task_pre_states" / f"{task_id}.json"
            before_task = shared.export_state()
            if pre_path.exists():
                if json.loads(pre_path.read_text(encoding="utf-8")) != before_task:
                    raise RuntimeError("CoProMem task snapshot changed on resume")
            else:
                write_json(pre_path, before_task)
            for trial, seed in zip(trials, seeds):
                base = dict(run=RUN, progress=PROGRESS, ledger=ledger, api_key=key,
                            all_task_ids=all_ids, task_id=task_id, trial_id=trial,
                            seed=seed, max_actions=30, temperature=0.7, phase="evaluation")
                jobs = [("no_memory", {}),
                        ("official_upstream_reme_fixed", {"memory_base_url": svc["reme-fixed"].base_url}),
                        ("official_upstream_reme_dynamic", {"memory_base_url": svc[f"reme-dynamic-{trial}"].base_url})]
                for arm, kwargs in jobs:
                    out = artifact(arm, task_id, trial)
                    if out.exists():
                        prior = verify_existing_artifact(out, arm, task_id, trial)
                        if arm == "official_upstream_reme_dynamic":
                            if not marker(arm, task_id, trial).exists():
                                raise RuntimeError(f"ReMe update side effect uncertain for {prior['trajectory_id']}")
                            verify_update_marker(marker(arm, task_id, trial), prior, out)
                        continue
                    if c_free_gb() < 5.0:
                        raise RuntimeError("configured disk floor would be breached before dispatch")
                    if arm == "official_upstream_reme_dynamic":
                        service = svc[f"reme-dynamic-{trial}"]
                        def update_reme(agent: Any, result: dict[str, Any], *, _service=service,
                                        _trial=trial, _out=out) -> None:
                            pre_snapshot = RUN / "update_pre_states/official_upstream_reme_dynamic" / task_id / f"trial-{_trial}.jsonl"
                            pre_snapshot.parent.mkdir(parents=True, exist_ok=True)
                            official_post(_service.base_url, "dump_memory", {"dump_file_path": str(pre_snapshot)})
                            write_json(pre_snapshot.with_suffix(".json"),
                                {"trajectory_id": result["trajectory_id"],
                                 "scored_artifact_sha256": file_sha(_out),
                                 "pre_snapshot_sha256": file_sha(pre_snapshot), "state": "prepared"})
                            outcome = dynamic_post_trial_update(agent, result["after_score"],
                                lambda event: append(PROGRESS, {**event, "trajectory_id": result["trajectory_id"]}))
                            saved = RUN / "reme" / f"dynamic-trial-{_trial}.jsonl"
                            official_post(_service.base_url, "dump_memory", {"dump_file_path": str(saved)})
                            write_json(marker("official_upstream_reme_dynamic", task_id, _trial),
                                {"trajectory_id": result["trajectory_id"],
                                 "scored_artifact_sha256": file_sha(_out),
                                 "outcome": outcome, "snapshot_sha256": file_sha(saved)})
                        kwargs = {**kwargs, "post_score_update": update_reme}
                    execute_trajectory(**base, arm=arm, artifact_path=out, **kwargs)
                    if arm == "official_upstream_reme_dynamic" and not marker(arm, task_id, trial).exists():
                        raise RuntimeError("scored ReMe dynamic trajectory lacks durable update marker")
                    summary(value, "evaluation")
            missing = [(trial, seed) for trial, seed in zip(trials, seeds)
                       if not artifact("copromem_dynamic", task_id, trial).exists()]
            if missing:
                if c_free_gb() < 5.0:
                    raise RuntimeError("configured disk floor would be breached before parallel dispatch")
                with ProcessPoolExecutor(max_workers=len(missing), mp_context=get_context("spawn")) as pool:
                    futures = [pool.submit(run_copro_trial, task_id, trial, seed,
                                           [asdict(event) for event in descriptor], before_task,
                                           all_ids, key, cap) for trial, seed in missing]
                    for future in futures:
                        future.result()
            complete_copro_task(shared, task_id, trials, seeds)
            summary(value, "evaluation")
    from .reporting import build_report
    final = build_report(RUN)
    if not final.is_file(): raise RuntimeError("final report was not durably created")
    status("completed", c_free_gb=c_free_gb(), final_report_sha256=file_sha(final)); summary(value, "completed")


if __name__ == "__main__":
    try: main()
    except BaseException as exc:
        RUN.mkdir(parents=True, exist_ok=True); append(PROGRESS, {"event": "runner_failed", "error_type": type(exc).__name__})
        if MANIFEST.exists(): status("failed", error_type=type(exc).__name__)
        raise
