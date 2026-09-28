#!/usr/bin/env python3
"""Freeze and execute the v6 shared AppWorld acquisition stage.

The runner has no evaluation mode.  It creates one common No-Memory pool,
then independently constructs pinned upstream ReMe and deterministic CoProMem
v6 banks from that exact frozen pool.  It is deliberately fail-closed: no
selected task is opened before ``freeze`` writes the manifest hash.
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
from collections import defaultdict
from typing import Any, Iterable

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUN_NAME = "v6_shared_acquisition_001"
INVENTORY = ROOT / "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v5_train_inventory_001/train-public-inventory.json"
REGISTRY = ROOT / "research/reme_copromem_fixed_dynamic_review/appworld_public_tool_schema_registry_v5_3.json"
SOURCE = pathlib.Path("/mnt/e/Project/AAMAS/_work/reme_paper_2f37a159")
REME_PYTHON = "/mnt/e/Project/AAMAS/reme-upstream-fixed-dynamic/bin/python"
APPWORLD_PYTHON = "/home/xiqhq/copromem-appworld/venv/bin/python"
APPWORLD_ROOT = "/home/xiqhq/copromem-appworld"

# Configure isolated-process paths before importing the maintained bridge.
os.environ.setdefault("COPROMEM_REME_SOURCE", str(SOURCE))
os.environ.setdefault("COPROMEM_REME_PYTHON", REME_PYTHON)
os.environ.setdefault("COPROMEM_APPWORLD_PYTHON", APPWORLD_PYTHON)
os.environ.setdefault("COPROMEM_APPWORLD_ROOT", APPWORLD_ROOT)
os.environ.setdefault("COPROMEM_ROOT", str(ROOT))

from copromem.benchmarks.appworld.execution_evidence import journal_records, partition_v6_graph_evidence
from copromem.contrastive_graph_v6 import digest
from copromem.experiments.reme_copromem.contrastive_v6_runner import (
    commit_task_batch, fresh_state, plan_task_batch_from_artifacts, validate_task_batch,
)
from copromem.experiments.reme_copromem.runner import (
    AppendOnlyLedger, acquisition_pool, append, execute_trajectory, official_post, services, v5_budget_bound, write_json,
)
from copromem.integrations.reme.bank import construct_once, load_clone


def file_sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def c_free_gib() -> float:
    stat = os.statvfs("/mnt/c")
    return stat.f_bavail * stat.f_frsize / 1024 ** 3


def _normalise_public_instruction(text: str) -> str:
    # Values are erased prior to descriptor hashing; it is never a task answer.
    return re.sub(r"(?:\b\d+\b|'[^']*'|\"[^\"]*\")", "<value>", text.lower()).strip()


def _id_from(value: Any) -> set[str]:
    return set(re.findall(r"\b[a-f0-9]{7}_\d+\b", str(value)))


def custody_audit(artifacts: pathlib.Path) -> dict[str, Any]:
    """Separate mere identifier mentions from actual executed/scored evidence."""
    mentioned: set[str] = set(); payload_opened: set[str] = set(); executed: set[str] = set(); scored: set[str] = set()
    for path in artifacts.rglob("*.json"):
        try: row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError): continue
        mentioned |= _id_from(row)
        if not isinstance(row, dict): continue
        task = str(row.get("task_id") or "")
        if task and ("instruction" in row or "app_descriptions" in row): payload_opened.add(task)
        is_trajectory = "history" in row and ("after_score" in row or "official_score" in row)
        if task and is_trajectory:
            executed.add(task)
            if "after_score" in row or "official_score" in row: scored.add(task)
    for path in artifacts.rglob("*.jsonl"):
        try: lines = path.read_text(encoding="utf-8").splitlines()
        except OSError: continue
        for line in lines:
            try: row = json.loads(line)
            except json.JSONDecodeError: continue
            mentioned |= _id_from(row)
            task = str(row.get("task_id") or "")
            if task and row.get("event") in {"action_submitted", "action_applied"}: executed.add(task)
            if task and row.get("event") == "official_score": scored.add(task)
    return {
        "inventory_or_textual_mentions": sorted(mentioned), "payload_opened": sorted(payload_opened),
        "executed": sorted(executed), "scored": sorted(scored),
        "execution_exclusion": sorted(executed | scored),
        "execution_exclusion_sha256": digest(sorted(executed | scored)),
    }


def public_registry() -> dict[str, Any]:
    value = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if not value.get("registry_sha256"):
        raise RuntimeError("frozen public callable registry hash is absent")
    return value


def select_allocation(inventory: dict[str, Any], custody: dict[str, Any], registry: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Choose six public train families with two unexecuted siblings each."""
    excluded = set(custody["execution_exclusion"])
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in inventory.get("unseen_train_tasks", []):
        if not isinstance(raw, dict): continue
        task = str(raw.get("task_id", ""))
        if task in excluded: continue
        family = task.rsplit("_", 1)[0]
        descriptor = {
            "public_instruction_template": _normalise_public_instruction(str(raw.get("instruction", ""))),
            "public_app_description_sha256": digest(raw.get("app_descriptions", {})),
            "callable_registry_sha256": registry["registry_sha256"],
        }
        # AppWorld's public inventory assigns siblings a stable public family
        # prefix while their value-redacted instructions may still differ.
        # Do not require string-equality of sibling instructions (which would
        # erase valid family diversity); retain each descriptor separately.
        effect = {"public_family": family, "public_app_description_sha256": descriptor["public_app_description_sha256"],
                  "callable_registry_sha256": registry["registry_sha256"]}
        groups[family].append({"task_id": task, "family": family, "descriptor": descriptor,
                               "descriptor_sha256": digest(descriptor), "family_effect_sha256": digest(effect)})
    candidates: list[dict[str, Any]] = []
    for family, rows in groups.items():
        rows.sort(key=lambda row: row["task_id"])
        if len(rows) < 2: continue
        candidates.append({"family": family, "family_effect_sha256": rows[0]["family_effect_sha256"],
                           "descriptor_sha256": min(row["descriptor_sha256"] for row in rows), "siblings": rows})
    candidates.sort(key=lambda row: (row["family_effect_sha256"], row["descriptor_sha256"], row["siblings"][0]["task_id"]))
    selected = candidates[:6]
    if len(selected) < 6:
        return [], {"candidate_families": candidates, "candidate_list_sha256": digest(candidates),
                    "shortfall": {"required_families": 6, "available_families": len(selected)}}
    allocation = []
    for family in selected:
        allocation.extend(family["siblings"][:2])
    return allocation, {"candidate_families": candidates, "candidate_list_sha256": digest(candidates),
                        "ordering_rule": "(family_effect_sha256, descriptor_sha256, task_id)",
                        "shortfall": None}


def historical_exposure(artifacts: pathlib.Path) -> tuple[float, list[dict[str, Any]]]:
    total = 0.0; unresolved: list[dict[str, Any]] = []
    for path in artifacts.rglob("ledger.jsonl"):
        latest: dict[str, float] = {}; settled: set[str] = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            try: row = json.loads(line)
            except json.JSONDecodeError: continue
            call_id = str(row.get("id", ""))
            if row.get("event") == "reserve": latest[call_id] = float(row.get("usd", 0.0))
            elif row.get("event") == "settle" and call_id in latest:
                latest[call_id] = float(row.get("usd", 0.0)); settled.add(call_id)
        total += sum(latest.values())
        unresolved.extend({"ledger": str(path), "id": call_id, "usd": usd}
                          for call_id, usd in latest.items() if call_id not in settled)
    return total, unresolved


def budget(artifacts: pathlib.Path) -> dict[str, Any]:
    history, unresolved = historical_exposure(artifacts)
    limits = {"executor": 720, "reme_lifecycle": 128, "reme_embedding": 512, "copromem_decomposition": 0}
    value = v5_budget_bound(call_limits=limits, historical_usd=history, lifecycle_input_ceiling=131072)
    return {"hard_cap_usd": 100.0, "call_limits": limits, "historical_unresolved_count": len(unresolved),
            "historical_unresolved": unresolved, "fits_hard_cap": value["all_in_usd"] <= 100.0, **value}


def prepare(run: pathlib.Path) -> None:
    if run.exists() and any(run.iterdir()): raise RuntimeError("run directory is not empty")
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8")); registry = public_registry(); custody = custody_audit(ROOT / "artifacts")
    allocation, selection = select_allocation(inventory, custody, registry)
    run.mkdir(parents=True, exist_ok=True)
    write_json(run / "custody-audit.json", custody)
    write_json(run / "selection-audit.json", {**selection, "selected": allocation,
                                                "provider_calls": 0, "payloads_opened": False, "test_normal_used": False})
    if not allocation: raise RuntimeError("six fresh public train sibling families are unavailable")
    value = {
        "protocol": RUN_NAME, "status": "prepared_pre_payload", "purpose": "shared_acquisition_only",
        "git_commit": git_head(), "inventory_sha256": file_sha(INVENTORY), "registry_sha256": registry["registry_sha256"],
        "custody_audit_sha256": file_sha(run / "custody-audit.json"), "selection_audit_sha256": file_sha(run / "selection-audit.json"),
        "allocation": allocation, "task_ids": [row["task_id"] for row in allocation], "seeds": [10101, 10102],
        "expected_trajectories": 24,
        "execution": {"arm": "shared_acquisition", "model": "deepseek/deepseek-v4.1-flash", "provider_only": "deepseek",
                      "fallbacks": False, "reasoning_effort": "none", "stream": False, "temperature": 0.7,
                      "top_p": 1.0, "max_actions": 30, "completion_token_ceiling": 2048, "c_floor_gib": 10.0},
        "dependencies": {str(INVENTORY): file_sha(INVENTORY), str(REGISTRY): file_sha(REGISTRY),
                         "reme_source_commit": subprocess.check_output(["git", "-C", str(SOURCE), "rev-parse", "HEAD"], text=True).strip()},
        "budget": budget(ROOT / "artifacts"),
    }
    if not value["budget"]["fits_hard_cap"]: raise RuntimeError("registered all-inclusive acquisition bound exceeds USD 100")
    if value["budget"]["historical_unresolved_count"]:
        # Previous retained reserves are history, not dispatchable state; they
        # remain visibly carried in the new ledger and are never silently deleted.
        value["budget"]["historical_unresolved_policy"] = "carried_forward_as_reserved_exposure"
    write_json(run / "template.json", value)


def freeze(run: pathlib.Path) -> None:
    template = run / "template.json"
    if not template.exists() or (run / "manifest.json").exists(): raise RuntimeError("prepared template required; manifest is immutable")
    value = json.loads(template.read_text(encoding="utf-8"))
    if value["git_commit"] != git_head(): raise RuntimeError("runtime source changed after deterministic selection")
    value["status"] = "frozen_pre_payload"
    write_json(run / "manifest.json", value)
    (run / "manifest.sha256").write_text(file_sha(run / "manifest.json") + "\n", encoding="utf-8")


def load(run: pathlib.Path) -> dict[str, Any]:
    manifest = run / "manifest.json"; checksum = run / "manifest.sha256"
    if not manifest.exists() or file_sha(manifest) != checksum.read_text(encoding="utf-8").strip(): raise RuntimeError("frozen manifest hash mismatch")
    value = json.loads(manifest.read_text(encoding="utf-8"))
    if value["git_commit"] != git_head(): raise RuntimeError("frozen manifest source mismatch")
    if c_free_gib() < value["execution"]["c_floor_gib"]: raise RuntimeError("C-drive floor breached")
    if not value["budget"]["fits_hard_cap"]: raise RuntimeError("frozen budget does not fit hard cap")
    return value


def credential_present() -> bool:
    env = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if env: return True
    path = ROOT / ".env"
    return path.is_file() and any(line.startswith("OPENROUTER_API_KEY=") and line.split("=", 1)[1].strip()
                                  for line in path.read_text(encoding="utf-8").splitlines())


def status(run: pathlib.Path, state: str, **extra: Any) -> None:
    write_json(run / "runner-status.json", {"state": state, "pid": os.getpid(), "updated_ns": time.time_ns(), **extra})


def _event(run: pathlib.Path, event: str, **extra: Any) -> None:
    append(run / "progress.jsonl", {"event": event, "time_ns": time.time_ns(), **extra})


def acquire_lock(run: pathlib.Path) -> pathlib.Path:
    """Allow a restart only after proving the prior runner PID is absent."""
    lock = run / "runner.lock"
    if lock.exists():
        try: prior = int(json.loads(lock.read_text(encoding="utf-8"))["pid"]); os.kill(prior, 0)
        except ProcessLookupError: lock.unlink()
        except (KeyError, ValueError, json.JSONDecodeError): raise RuntimeError("invalid runner lock")
        else: raise RuntimeError("duplicate acquisition runner is active")
    write_json(lock, {"pid": os.getpid(), "manifest_sha256": file_sha(run / "manifest.json")})
    return lock


def bootstrap_historical(ledger: AppendOnlyLedger, amount: float) -> None:
    """Carry prior charged/reserved exposure into the new hard-cap ledger."""
    if amount <= 0 or ledger.path.exists() and ledger.path.stat().st_size:
        return
    call_id = "historical-exposure-carry-forward"
    ledger.reserve(call_id, amount, {"role": "historical_carry_forward", "source": "pre-v6-shared-acquisition"})
    ledger.settle(call_id, amount, {"role": "historical_carry_forward", "source": "pre-v6-shared-acquisition"})


def _acquisition_records(run: pathlib.Path, value: dict[str, Any], ledger: AppendOnlyLedger, key: str) -> list[dict[str, Any]]:
    registry = public_registry(); evidence = {"registry_path": str(REGISTRY), "registry_sha256": registry["registry_sha256"]}
    records: list[dict[str, Any]] = []
    for task_id in value["task_ids"]:
        for trajectory_index, seed in enumerate(value["seeds"]):
            artifact = run / "acquisition" / f"{task_id}--seed_{seed}--trajectory_{trajectory_index}.json"
            if artifact.exists(): row = json.loads(artifact.read_text(encoding="utf-8"))
            else:
                row = execute_trajectory(run=run, progress=run / "progress.jsonl", ledger=ledger, api_key=key,
                    all_task_ids=value["task_ids"], arm="shared_acquisition", task_id=task_id, trial_id=trajectory_index,
                    seed=seed, max_actions=30, temperature=0.7, phase="acquisition", artifact_path=artifact,
                    execution_evidence=evidence)
            evidence_path = str(row.get("execution_evidence_path") or "")
            if not evidence_path or not pathlib.Path(evidence_path).is_file(): raise RuntimeError("acquisition telemetry is absent")
            journal_records(evidence_path)  # verifies the append-only evidence hash chain.
            row.update({"acquisition_identity": f"{task_id}::seed={seed}::trajectory={trajectory_index}",
                        "source_artifact": str(artifact), "source_artifact_sha256": file_sha(artifact),
                        "family": next(item["family"] for item in value["allocation"] if item["task_id"] == task_id)})
            records.append(row)
            _event(run, "acquisition_terminal", trajectory_id=row["acquisition_identity"], score=row["after_score"],
                   history_sha256=row["history_sha256"], telemetry_sha256=file_sha(pathlib.Path(evidence_path)))
    if len(records) != value["expected_trajectories"]: raise RuntimeError("incomplete shared pool")
    return records


def construct_copromem_v6(run: pathlib.Path, records: list[dict[str, Any]], registry: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    state = fresh_state(); commits: list[dict[str, Any]] = []
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records: by_task[str(row["task_id"])].append(row)
    for task_id in sorted(by_task):
        rows = sorted(by_task[task_id], key=lambda row: row["acquisition_identity"])
        plan, audit = plan_task_batch_from_artifacts(artifacts=rows, registry=registry, pre_state=state,
                                                      evidence_paths=[row["execution_evidence_path"] for row in rows])
        validation = validate_task_batch(plan); post, marker = commit_task_batch(state, plan)
        item = {"task_id": task_id, "family": rows[0]["family"], "pre_state_sha256": digest(state),
                "plan": plan, "plan_sha256": plan["plan_sha256"], "audit": audit, "validation": validation,
                "marker": marker, "post_state_sha256": digest(post)}
        write_json(run / "copromem-v6" / "task-batches" / f"{task_id}.json", item)
        if marker["state"] == "committed": state = post; commits.append(item)
    write_json(run / "copromem-v6" / "initial-bank.json", state)
    write_json(run / "copromem-v6" / "fixed-bank.json", state)
    write_json(run / "copromem-v6" / "dynamic-bank.json", state)
    return state, commits


def construct_reme(run: pathlib.Path, records: list[dict[str, Any],], ledger: AppendOnlyLedger) -> dict[str, Any]:
    inputs = [{"trajectory_id": row["acquisition_identity"], "task_id": row["task_id"],
               "task_history": row["history"], "after_score": row["after_score"]} for row in records]
    names = ["reme-builder", "reme-fixed", "reme-dynamic"]
    with services(run, run / "ledger.jsonl", run / "progress.jsonl", 100.0, names, lifecycle_input_ceiling=131072) as svc:
        snapshot, checkpoint = run / "reme" / "shared-bank.jsonl", run / "reme" / "construction.jsonl"
        shared_hash, count = construct_once(official_post, svc["reme-builder"].base_url, inputs, checkpoint, snapshot,
                                             lambda record: _event(run, "reme_lifecycle", **record))
        if count != len(inputs): raise RuntimeError("official ReMe did not consume every acquisition input")
        fixed_hash = load_clone(official_post, svc["reme-fixed"].base_url, snapshot, shared_hash)
        dynamic_hash = load_clone(official_post, svc["reme-dynamic"].base_url, snapshot, shared_hash)
        # A retrieval probe uses only the public instruction already present in
        # the frozen acquisition artifact and the upstream route/schema.
        probe = official_post(svc["reme-fixed"].base_url, "retrieve_task_memory", {"query": str(records[0]["history"][0].get("content", "")), "top_k": 1,
                                                                                "enable_llm_build": False, "enable_llm_rerank": False, "enable_llm_rewrite": False})
        write_json(run / "reme" / "retrieval-smoke.json", {"query_source": "frozen_acquisition_public_instruction",
                                                             "response_sha256": digest(probe), "bank_sha256": shared_hash})
    return {"shared_bank_sha256": shared_hash, "fixed_clone_sha256": fixed_hash, "dynamic_clone_sha256": dynamic_hash,
            "input_count": len(inputs), "snapshot_sha256": file_sha(run / "reme" / "shared-bank.jsonl")}


def summarize(run: pathlib.Path, value: dict[str, Any], records: list[dict[str, Any]] | None = None, stage: str = "running") -> None:
    records = records or []
    full = [row for row in records if float(row.get("after_score", 0)) == 1.0]
    write_json(run / "live-summary.json", {"stage": stage, "completed": len(records), "expected": value["expected_trajectories"],
                                             "full_successes": len(full), "partial_or_failure": len(records) - len(full),
                                             "successful_families": sorted({row["family"] for row in full}),
                                             "c_free_gib": c_free_gib(), "manifest_sha256": file_sha(run / "manifest.json")})


def run(run: pathlib.Path, *, preflight_only: bool = False) -> None:
    value = load(run)
    if not credential_present(): raise RuntimeError("OpenRouter credential is absent")
    lock = acquire_lock(run)
    ledger = AppendOnlyLedger(run / "ledger.jsonl", 100.0, value["budget"]["call_limits"])
    bootstrap_historical(ledger, float(value["budget"]["historical_charged_or_reserved_usd"]))
    try:
        if preflight_only:
            status(run, "preflight_passed", manifest_sha256=file_sha(run / "manifest.json"), c_free_gib=c_free_gib()); return
        status(run, "running", manifest_sha256=file_sha(run / "manifest.json"), c_free_gib=c_free_gib()); _event(run, "acquisition_started")
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not key:
            # The transport needs the value only at dispatch; preserve it solely in process memory.
            for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
                if line.startswith("OPENROUTER_API_KEY="): key = line.split("=", 1)[1].strip().strip("'\"")
        records = _acquisition_records(run, value, ledger, key); summarize(run, value, records, "acquisition_complete")
        pool = {"trajectories": records, "pool_sha256": digest([{k: row[k] for k in ("acquisition_identity", "source_artifact_sha256", "history_sha256", "after_score")} for row in records])}
        write_json(run / "shared-pool.json", pool)
        registry = public_registry(); copro_state, commits = construct_copromem_v6(run, records, registry)
        promoted = [item for item in commits if item["marker"]["state"] == "committed"]
        copro_gate = {"promoted_schema_count": len(promoted), "families": sorted({item["family"] for item in promoted}),
                      "state_sha256": digest(copro_state), "passed": len(promoted) >= 3 and len({item["family"] for item in promoted}) >= 3}
        write_json(run / "copromem-v6" / "gate.json", copro_gate)
        if not copro_gate["passed"]:
            status(run, "terminal_no_go_copromem", copro_gate=copro_gate); summarize(run, value, records, "terminal_no_go_copromem"); return
        reme = construct_reme(run, records, ledger)
        write_json(run / "reme" / "bank-identity.json", reme)
        if ledger._call_state()[0].keys() - ledger._call_state()[1]: raise RuntimeError("unsettled provider reservation")
        report = {"classification": "ACQUISITION READY: shared trajectory pool produced valid, separately constructed upstream ReMe and CoProMem v6 banks suitable for a separately preregistered five-arm pilot.",
                  "manifest_sha256": file_sha(run / "manifest.json"), "shared_pool_sha256": pool["pool_sha256"],
                  "reme": reme, "copromem": copro_gate, "ledger_exposure_usd": ledger._exposure(), "c_free_gib": c_free_gib()}
        write_json(run / "FINAL_ACQUISITION_REPORT.json", report); status(run, "completed", final_report_sha256=file_sha(run / "FINAL_ACQUISITION_REPORT.json")); summarize(run, value, records, "completed")
    finally:
        if lock.exists(): lock.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=["prepare", "freeze", "preflight", "run"]); parser.add_argument("--run", required=True, type=pathlib.Path); args = parser.parse_args(); run_dir = args.run.resolve()
    if args.command == "prepare": prepare(run_dir)
    elif args.command == "freeze": freeze(run_dir)
    else: run(run_dir, preflight_only=args.command == "preflight")


if __name__ == "__main__":
    try: main()
    except BaseException as exc:
        # Never expose provider responses, credential material, or task content.
        if "args" in globals():
            args.run.mkdir(parents=True, exist_ok=True); _event(args.run, "runner_failed", error_type=type(exc).__name__)
            status(args.run, "failed", error_type=type(exc).__name__)
        raise
