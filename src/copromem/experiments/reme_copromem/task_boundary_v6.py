"""Two-arm, fail-closed task-boundary engineering runner.

This deliberately does not import or start the official ReMe service.  It is
an engineering probe for CoProMem's documented flat, fully-observable task
boundary rule, not a comparative method experiment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import time
from dataclasses import asdict
from typing import Any

from ...benchmarks.appworld.adapter import CoProMemAppWorldAdapter, TrialInput
from ...integrations.reme.transport import AppendOnlyLedger
from ...learning import ActionObservation, LearningCore
from .runner import append, construct_copromem, digest, execute_trajectory, raw_acquisition_trajectories, write_json, v5_budget_bound
from .public_path_registry import verify_public_registry


ROOT = pathlib.Path(__file__).resolve().parents[4]
RUN = pathlib.Path(os.environ["COPROMEM_RUN_DIR"])
MANIFEST = RUN / "manifest.json"
MANIFEST_SHA = RUN / "manifest.sha256"
PROGRESS = RUN / "progress.jsonl"
LEDGER = RUN / "ledger.jsonl"
STATUS = RUN / "runner-status.json"
SUMMARY = RUN / "live-summary.json"


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def c_free_gb() -> float:
    stat = os.statvfs(os.environ.get("COPROMEM_DISK_FLOOR_PATH", str(RUN)))
    return stat.f_bavail * stat.f_frsize / 1024 ** 3


def _env(name: str) -> str:
    env_file = ROOT / ".env"
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if "=" in line and line.split("=", 1)[0].strip() == name:
            value = line.split("=", 1)[1].strip().strip("'\"")
            if value:
                return value
    raise RuntimeError(f"required credential {name} is absent")


def _git_env() -> dict[str, str]:
    """Resolve a Windows worktree pointer when the runner is launched in WSL."""
    env = dict(os.environ)
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(name, None)
    pointer = ROOT / ".git"
    if pointer.is_file():
        match = re.match(r"gitdir:\s*([A-Za-z]):/(.+)", pointer.read_text(encoding="utf-8").strip())
        if match:
            env["GIT_DIR"] = f"/mnt/{match.group(1).lower()}/{match.group(2)}"
            env["GIT_WORK_TREE"] = str(ROOT)
    return env


def _status(state: str, **extra: Any) -> None:
    write_json(STATUS, {"state": state, "pid": os.getpid(), "updated_ns": time.time_ns(),
                        "manifest_sha256": MANIFEST_SHA.read_text(encoding="utf-8").strip(), **extra})


def _load() -> dict[str, Any]:
    raw = MANIFEST.read_bytes()
    if sha(MANIFEST) != MANIFEST_SHA.read_text(encoding="utf-8").strip():
        raise RuntimeError("006 manifest checksum mismatch")
    value = json.loads(raw)
    if value.get("protocol") not in {"v5_engineering_006_task_boundary", "v5_engineering_007_task_boundary", "v5_engineering_008_task_boundary", "v5_1_engineering_009_observable_subgraph", "v5_2_engineering_011_observable_path"}:
        raise RuntimeError("wrong protocol")
    if value.get("arms") != ["no_memory", "copromem_dynamic"]:
        raise RuntimeError("task-boundary run must have exactly the two registered arms")
    evaluation = value.get("evaluation", {})
    if evaluation.get("expected_trajectories") != 8 or len(evaluation.get("task_ids", [])) != 2:
        raise RuntimeError("006 task or trajectory count mismatch")
    if len(evaluation.get("seeds", [])) != 2 or len(evaluation.get("trial_ids", [])) != 2:
        raise RuntimeError("006 seed/trial count mismatch")
    if value.get("git_commit") != subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, env=_git_env()).strip():
        raise RuntimeError("running source differs from frozen manifest")
    changed = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no", "--", "src", "scripts"], cwd=ROOT, text=True, env=_git_env()).strip()
    if changed:
        raise RuntimeError("tracked runtime source differs from frozen commit")
    expected = v5_budget_bound(call_limits=value["budget"]["call_limits"],
                               historical_usd=float(value["budget"]["historical_charged_or_reserved_usd"]))
    for key, item in expected.items():
        if abs(float(value["budget"][key]) - float(item)) > 1e-12:
            raise RuntimeError(f"006 budget mismatch: {key}")
    if not value["budget"].get("fits_hard_cap"):
        raise RuntimeError("006 budget does not fit hard cap")
    if value.get("task_boundary_policy") == "observable_supported_path_v5_2":
        registry_path = ROOT / value["evaluation"]["public_registry_relative_path"]
        if not registry_path.is_file() or sha(registry_path) != value["evaluation"].get("public_registry_file_sha256"):
            raise RuntimeError("v5.2 public registry file mismatch")
        registry = json.loads(registry_path.read_text(encoding="utf-8")); verify_public_registry(registry)
        if registry["registry_sha256"] != value["evaluation"].get("public_registry_sha256"):
            raise RuntimeError("v5.2 public registry content mismatch")
    return value


def _lock() -> None:
    lock = RUN / "runner.lock"
    if lock.exists():
        prior = json.loads(lock.read_text(encoding="utf-8"))
        try:
            os.kill(int(prior["pid"]), 0)
        except ProcessLookupError:
            lock.unlink()
        else:
            raise RuntimeError(f"006 runner already active: {prior['pid']}")
    write_json(lock, {"pid": os.getpid(), "manifest_sha256": MANIFEST_SHA.read_text().strip()})


def _artifact(arm: str, task_id: str, trial: int) -> pathlib.Path:
    return RUN / "evaluation" / arm / task_id / f"trial-{trial}.json"


def _verify_artifact(path: pathlib.Path, arm: str, task_id: str, trial: int) -> dict[str, Any]:
    row = json.loads(path.read_text(encoding="utf-8"))
    if (row.get("arm"), row.get("task_id"), row.get("trial_id")) != (arm, task_id, trial):
        raise RuntimeError("trajectory artifact identity mismatch")
    if not isinstance(row.get("history"), list) or digest(row["history"]) != row.get("history_sha256"):
        raise RuntimeError("trajectory history integrity mismatch")
    if not isinstance(row.get("after_score"), (float, int)):
        raise RuntimeError("trajectory has no official score")
    return row


def _retrieval(adapter: CoProMemAppWorldAdapter, task_id: str, trial: int,
               descriptor: tuple[ActionObservation, ...]):
    path = RUN / "retrieval" / "copromem_dynamic" / task_id / f"trial-{trial}.json"
    def call(intent: str, domain: str, _: dict[str, Any]) -> str:
        expected_input = {"task_id": task_id, "trial_stream": trial, "intent": intent,
                          "domain": domain, "sites": [], "start_url": "", "base_prompt": intent,
                          "structural_events": [asdict(event) for event in descriptor]}
        if path.exists():
            record = json.loads(path.read_text(encoding="utf-8")); provenance = record.get("provenance")
            if not isinstance(provenance, dict) or provenance.get("task_input") != expected_input:
                raise RuntimeError("retrieval input provenance mismatch")
            if adapter.semantic_state_hash() != provenance.get("pre_state_sha256"):
                raise RuntimeError("retrieval restart state mismatch")
            guidance = CoProMemAppWorldAdapter.reproduce_retrieval(provenance["pre_state"], provenance["task_input"], provenance)
            if hashlib.sha256(guidance.encode()).hexdigest() != provenance.get("guidance_sha256"):
                raise RuntimeError("retrieval restart guidance mismatch")
            return guidance
        before = adapter.semantic_state_hash()
        guidance, provenance = adapter.retrieve_with_provenance(
            TrialInput(task_id, intent, domain, base_prompt=intent, structural_events=descriptor), trial)
        reproduced = CoProMemAppWorldAdapter.reproduce_retrieval(provenance["pre_state"], provenance["task_input"], provenance)
        if guidance != reproduced or hashlib.sha256(guidance.encode()).hexdigest() != provenance["guidance_sha256"]:
            raise RuntimeError("retrieval cannot be reproduced offline")
        write_json(path, {"arm": "copromem_dynamic", "task_id": task_id, "trial": trial,
                          "pre_state_sha256": before, "post_state_sha256": adapter.semantic_state_hash(),
                          "guidance_sha256": provenance["guidance_sha256"], "provenance": provenance})
        return guidance
    return call


def _task_state_path(task_id: str) -> pathlib.Path:
    return RUN / "copromem" / "task_states" / f"{task_id}.json"


def _complete_task(adapter: CoProMemAppWorldAdapter, task_id: str, trials: list[int], seeds: list[int],
                   descriptor: list[dict[str, Any]], policy_version: str, public_registry: dict[str, Any] | None = None) -> dict[str, Any]:
    """Use the maintained task-boundary implementation without ReMe imports."""
    # The maintained helper is parameterized entirely by COPROMEM_RUN_DIR; it
    # does not initialize any ReMe service or transport.
    from . import config as maintained
    maintained.complete_copro_task(adapter, task_id, trials, seeds, descriptor=descriptor, policy_version=policy_version,
                                   public_registry=public_registry)
    marker = RUN / "copromem" / "task_updates" / f"{task_id}.json"
    if not marker.exists():
        raise RuntimeError("task-boundary merge marker is not durable")
    result = json.loads(marker.read_text(encoding="utf-8"))
    if result.get("state") == "committed":
        if not _task_state_path(task_id).exists():
            raise RuntimeError("committed task-boundary state is not durable")
    elif result.get("state") != "rejected":
        raise RuntimeError("task-boundary marker has an unknown state")
    return result


def _snapshot(path: pathlib.Path, state: dict[str, Any]) -> None:
    if path.exists():
        if digest(json.loads(path.read_text(encoding="utf-8"))) != digest(state):
            raise RuntimeError("task pre-state changed across restart")
    else:
        write_json(path, state)


def _run_task(value: dict[str, Any], ledger: AppendOnlyLedger, initial: dict[str, Any], task_id: str,
              public_registry: dict[str, Any] | None = None) -> dict[str, Any]:
    ev = value["evaluation"]; trials, seeds = list(ev["trial_ids"]), list(ev["seeds"])
    pre_file = RUN / "copromem" / "task_pre_states" / f"{task_id}.json"
    _snapshot(pre_file, initial)
    raw_descriptor = ev["descriptors"][task_id]
    descriptor = tuple(ActionObservation(**item) for item in raw_descriptor)
    key = _env("OPENROUTER_API_KEY")
    for arm in value["arms"]:
        for trial, seed in zip(trials, seeds):
            target = _artifact(arm, task_id, trial)
            if target.exists():
                _verify_artifact(target, arm, task_id, trial); continue
            callback = None
            if arm == "copromem_dynamic":
                clone = CoProMemAppWorldAdapter(api_key=""); clone.clone_from_state(initial)
                callback = _retrieval(clone, task_id, trial, descriptor)
            execute_trajectory(run=RUN, progress=PROGRESS, ledger=ledger, api_key=key,
                all_task_ids=list(ev["task_ids"]), arm=arm, task_id=task_id, trial_id=trial, seed=seed,
                max_actions=int(value["execution"]["max_actions"]), temperature=float(value["execution"]["temperature"]),
                phase="evaluation", artifact_path=target, memory_for_instruction=callback)
    merged = CoProMemAppWorldAdapter(api_key=""); merged.clone_from_state(initial)
    marker = _complete_task(merged, task_id, trials, seeds, raw_descriptor,
                            value.get("task_boundary_policy", "strict_exact_v5"), public_registry)
    return marker


def _a_gate(value: dict[str, Any], initial: dict[str, Any], marker: dict[str, Any]) -> dict[str, Any]:
    task_id = value["evaluation"]["task_ids"][0]; trials = value["evaluation"]["trial_ids"]
    rows = [_verify_artifact(_artifact("copromem_dynamic", task_id, trial), "copromem_dynamic", task_id, trial) for trial in trials]
    from ...benchmarks.appworld.adapter import normalize_appworld_history
    from .task_boundary import fully_observed
    observed = []
    for row in rows:
        events = normalize_appworld_history(row["history"], float(row["after_score"]) == 1.0)
        observed.append(bool(LearningCore.signature(events)) and fully_observed(events))
    pending = json.loads((RUN / "copromem" / "task_updates_pending" / f"{task_id}.json").read_text(encoding="utf-8"))
    from .task_boundary import commit_task_boundary_plan
    reconstructed, validation = commit_task_boundary_plan(initial, pending["plan"])
    winner = marker.get("winner_episode_id")
    state = json.loads(_task_state_path(task_id).read_text(encoding="utf-8")) if marker.get("state") == "committed" else initial
    procedures = state.get("learning", {}).get("episode_procedures", {}).get(winner, []) if winner else []
    schema = state.get("learning", {}).get("episode_schemas", {}).get(winner) if winner else None
    if value.get("task_boundary_policy") == "observable_supported_subgraph_v5_1":
        observed = [bool(validation.get("projection_valid"))]
    elif value.get("task_boundary_policy") == "observable_supported_path_v5_2":
        observed = [bool(validation.get("path_complete") and validation.get("path_reproduced"))]
    result = {"task_id": task_id, "official_scores": [float(row["after_score"]) for row in rows],
              "full_success": any(float(row["after_score"]) == 1.0 for row in rows),
              "fully_observed": all(observed), "winner_episode_id": winner, "winner_schema_id": schema,
              "eligible_procedure_count": len(procedures), "post_state_sha256": digest(state),
              "pre_state_sha256": digest(initial), "marker_state": marker.get("state"),
              "offline_reproduction": digest(reconstructed) == digest(state),
              "idempotent_commit": digest(commit_task_boundary_plan(initial, pending["plan"])[0]) == digest(reconstructed),
              "candidate_audit_separate": pending["plan"].get("candidate_audit_state_sha256") != digest(state),
              "plan_validation": validation}
    result["passed"] = bool(result["full_success"] and result["fully_observed"] and winner and schema and
                            str(schema).startswith("schema_") and procedures and result["marker_state"] == "committed" and
                            result["offline_reproduction"] and result["idempotent_commit"] and result["candidate_audit_separate"] and
                            validation["passed"])
    write_json(RUN / "gates" / "a-task-boundary-gate.json", result)
    append(PROGRESS, {"event": "a_task_boundary_gate", **result})
    return result


def _b_gate(value: dict[str, Any], a_gate: dict[str, Any], a_state: dict[str, Any], b_marker: dict[str, Any]) -> dict[str, Any]:
    task_id = value["evaluation"]["task_ids"][1]; winner = a_gate["winner_schema_id"]
    records = [json.loads((RUN / "retrieval" / "copromem_dynamic" / task_id / f"trial-{trial}.json").read_text())
               for trial in value["evaluation"]["trial_ids"]]
    checks = []
    for record in records:
        provenance = record["provenance"]
        guidance = CoProMemAppWorldAdapter.reproduce_retrieval(provenance["pre_state"], provenance["task_input"], provenance)
        checks.append({"pre_state": record["pre_state_sha256"] == digest(a_state),
                       "selected": provenance.get("selected_schema_id") == winner,
                       "reproduced": hashlib.sha256(guidance.encode()).hexdigest() == provenance.get("guidance_sha256"),
                       "learned": provenance.get("fallback_category") == "learned",
                       "no_candidate_or_quarantine": provenance.get("selected_schema_id") in
                           set(provenance.get("candidate_schema_ids", [])),
                       "supported_procedures_only": bool(provenance.get("injected_procedure_ids"))})
    result = {"task_id": task_id, "a_winner_schema_id": winner, "retrieval_checks": checks,
              "merge_once": b_marker.get("state") == "committed",
              "post_state_sha256": b_marker.get("after_state_sha256")}
    result["passed"] = all(all(check.values()) for check in checks) and result["merge_once"]
    write_json(RUN / "gates" / "b-retrieval-gate.json", result)
    append(PROGRESS, {"event": "b_task_boundary_gate", **result})
    return result


def _summary(value: dict[str, Any], state: str) -> None:
    paths = list((RUN / "evaluation").glob("*/*/*.json")); by_arm: dict[str, int] = {}
    for path in paths:
        arm = path.parts[-3]; by_arm[arm] = by_arm.get(arm, 0) + 1
    write_json(SUMMARY, {"state": state, "evaluation_completed": len(paths),
                         "evaluation_expected": value["evaluation"]["expected_trajectories"],
                         "per_arm_completed": by_arm, "c_free_gb": c_free_gb(),
                         "manifest_sha256": MANIFEST_SHA.read_text().strip()})


def _final_report(value: dict[str, Any], state: str, a_gate: dict[str, Any] | None = None,
                  b_gate: dict[str, Any] | None = None) -> None:
    """Sanitized, deterministic engineering report; raw histories stay local."""
    rows: list[dict[str, Any]] = []
    for path in sorted((RUN / "evaluation").glob("*/*/*.json")):
        artifact = json.loads(path.read_text(encoding="utf-8"))
        rows.append({key: artifact.get(key) for key in
                     ("arm", "task_id", "trial_id", "seed", "after_score", "actions", "termination", "history_sha256")})
    reservations = settlements = 0
    for line in LEDGER.read_text(encoding="utf-8").splitlines() if LEDGER.exists() else ():
        item = json.loads(line)
        reservations += int(item.get("event") == "reserve")
        settlements += int(item.get("event") == "settle")
    write_json(RUN / "final-report.json", {
        "classification": "engineering-only strict-v5 task-boundary validation; no efficacy claim",
        "state": state, "manifest_sha256": MANIFEST_SHA.read_text(encoding="utf-8").strip(),
        "source_commit": value["git_commit"], "expected_trajectories": value["evaluation"]["expected_trajectories"],
        "completed_trajectories": len(rows), "trajectory_results": rows, "a_gate": a_gate,
        "b_gate": b_gate, "ledger_events": {"reservations": reservations, "settlements": settlements},
    })


def run(preflight_only: bool = False) -> None:
    value = _load(); RUN.mkdir(parents=True, exist_ok=True); _lock()
    if c_free_gb() < float(value["execution"]["c_floor_gib"]): raise RuntimeError("C-drive floor breached")
    if os.environ.get("COPROMEM_REME_SERVICE_STARTED"):
        raise RuntimeError("006 prohibits ReMe service startup")
    ledger = AppendOnlyLedger(LEDGER, float(value["budget"]["ledger_dispatch_cap_usd"]), value["budget"]["call_limits"])
    carry = float(value["budget"]["historical_charged_or_reserved_usd"])
    carry_id = f"historical-carry-forward-usd-{carry:.12f}"
    if not LEDGER.exists() or carry_id not in LEDGER.read_text(encoding="utf-8"):
        ledger.reserve(carry_id, carry, {"role": "historical_carry_forward", "source": "v5_prior_ledger"})
    acquisition = pathlib.Path(value["acquisition"]["source_export"])
    if sha(acquisition) != value["acquisition"]["export_sha256"]: raise RuntimeError("acquisition export hash mismatch")
    rows = json.loads(acquisition.read_text(encoding="utf-8")); rows = rows.get("trajectories", rows)
    if len(rows) != 32 or set(row["task_id"] for row in rows) & set(value["evaluation"]["task_ids"]):
        raise RuntimeError("006 acquisition provenance/disjointness failed")
    initial_path = RUN / "copromem" / "initial-state.json"
    if initial_path.exists(): initial = json.loads(initial_path.read_text(encoding="utf-8"))
    else:
        initial, _ = construct_copromem(run=RUN, progress=PROGRESS, ledger=ledger, api_key="", raw=raw_acquisition_trajectories(rows), call_cap=0)
    _status("preflight_passed", c_free_gb=c_free_gb(), initial_state_sha256=digest(initial), reme_initialized=False)
    _summary(value, "preflight_passed")
    if preflight_only: return
    registry = None
    if value.get("task_boundary_policy") == "observable_supported_path_v5_2":
        registry = json.loads((ROOT / value["evaluation"]["public_registry_relative_path"]).read_text(encoding="utf-8"))
        verify_public_registry(registry)
    a, b = value["evaluation"]["task_ids"]
    a_marker = _run_task(value, ledger, initial, a, registry)
    gate = _a_gate(value, initial, a_marker)
    if not gate["passed"]:
        state = "terminal_no_go_a_unsuitable"
        _status(state, a_gate=gate); _summary(value, state); _final_report(value, state, a_gate=gate); return
    a_state = json.loads(_task_state_path(a).read_text(encoding="utf-8"))
    b_marker = _run_task(value, ledger, a_state, b, registry)
    b_gate = _b_gate(value, gate, a_state, b_marker)
    final = "completed" if b_gate["passed"] else "terminal_no_go_b_retrieval"
    _status(final, a_gate=gate, b_gate=b_gate); _summary(value, final)
    _final_report(value, final, gate, b_gate)


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--preflight", action="store_true"); args = parser.parse_args()
    run(args.preflight)


if __name__ == "__main__": main()
