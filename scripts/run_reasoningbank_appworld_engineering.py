#!/usr/bin/env python3
"""Dedicated, restart-safe ReasoningBank-AppWorld engineering runner.

``prepare`` reads only a pre-generated public development descriptor inventory.
It never instantiates an AppWorld task.  ``run`` is the sole command that may
open the frozen tasks, and it requires a byte-for-byte frozen manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import math
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from copromem.experiments.reme_copromem.evidence_contract import validate as validate_evidence
from copromem.experiments.reme_copromem.live_summary import build_live_summary, write_live_summary
from copromem.experiments.reme_copromem.runner import AppendOnlyLedger, append, execute_trajectory, write_json
from copromem.integrations.reasoning_bank.appworld import ReasoningBank, sha256
from copromem.integrations.reasoning_bank.appworld_protocol import protocol_record, validate_protocol
from copromem.integrations.reasoning_bank.checkpoints import ReasoningBankDynamicCheckpoints
from copromem.integrations.reasoning_bank.dynamic_runtime import ReasoningBankDynamicRuntime
from copromem.integrations.reasoning_bank.lifecycle import ReasoningBankLifecycle
from copromem.integrations.reasoning_bank.providers import ReasoningBankProviders
from copromem.integrations.reasoning_bank.shared_embedding import SharedAzureOpenRouterEmbedder
from copromem.integrations.reme.transport import INPUT_PRICE, MAX_OUTPUT_TOKENS, OUTPUT_PRICE


RUN_VERSION = "reasoningbank-appworld-engineering-v1"
ARMS = ["no_memory", "reasoningbank_dynamic"]
SEEDS = [9701, 9702]
HARD_CAP = 50.0
HISTORICAL_CARRY_ID = "historical-infrastructure-carry"
REGISTRY = ROOT / "research" / "reme_copromem_fixed_dynamic_review" / "appworld_public_tool_schema_registry_v5_3.json"


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_commit() -> str:
    # Managed Windows worktrees store an absolute ``E:/...`` gitdir pointer.
    # Linux AppWorld workers must translate it explicitly, never fall back to
    # an unrelated current directory or a mutable checkout.
    environment = dict(os.environ)
    pointer = ROOT / ".git"
    if os.name == "posix" and pointer.is_file():
        match = re.fullmatch(r"gitdir:\s*([A-Za-z]):/(.+)", pointer.read_text(encoding="utf-8").strip())
        if match:
            environment["GIT_DIR"] = f"/mnt/{match.group(1).lower()}/{match.group(2)}"
            environment["GIT_WORK_TREE"] = str(ROOT)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, env=environment).strip()


def _public_inventory_path() -> Path:
    raw = os.environ.get("REASONINGBANK_PUBLIC_DEV_DESCRIPTORS", "")
    path = Path(raw).expanduser() if raw else Path("E:/Project/AAMAS/COPROMEM-review/artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v5_engineering_001/public-dev-descriptors.json")
    if not path.is_file():
        raise RuntimeError("public development descriptor inventory is unavailable")
    return path.resolve()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fsync_json(path: Path, value: Mapping[str, Any]) -> None:
    write_json(path, dict(value))


def _c_free_gib() -> float:
    for candidate in ("/mnt/c", "C:/"):
        try:
            stat = os.statvfs(candidate)
            return stat.f_bavail * stat.f_frsize / 1024**3
        except OSError:
            continue
    raise RuntimeError("cannot determine C-drive free space")


def _storage_guard(stage: str) -> None:
    available = _c_free_gib()
    if available < 3.0:
        raise RuntimeError(f"C-drive mandatory stop threshold breached before {stage}")
    if available < 5.0:
        raise RuntimeError(f"C-drive launch floor breached before {stage}")


def _normalize_instruction(value: str) -> str:
    text = str(value).lower()
    text = re.sub(r"\b\d+\b", "<number>", text)
    text = re.sub(r"\b(?:r&b|edm|indie|rock|jazz|pop|hip hop|classical)\b", "<category>", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _family(task_id: str) -> str:
    value, sep, suffix = str(task_id).rpartition("_")
    if not value or sep != "_" or not suffix.isdecimal():
        raise RuntimeError("public development inventory contains malformed task ID")
    return value


def _hard_exposed_task_ids() -> tuple[set[str], dict[str, list[str]]]:
    """Find only execution/scoring evidence; textual mentions do not exclude."""
    raw_roots = os.environ.get("REASONINGBANK_CUSTODY_ROOTS_JSON")
    if raw_roots:
        try:
            configured = json.loads(raw_roots)
        except json.JSONDecodeError as exc:
            raise RuntimeError("ReasoningBank custody roots are malformed") from exc
        if not isinstance(configured, list) or not all(isinstance(item, str) for item in configured):
            raise RuntimeError("ReasoningBank custody roots must be a JSON string list")
        roots = [Path(item).expanduser() for item in configured]
    else:
        # A Windows-side offline audit has a useful conservative default.
        # Linux detached runners must pass explicit /mnt/e roots; never infer
        # an E drive from the worker current directory.
        roots = [ROOT / "artifacts", Path("E:/Project/AAMAS/COPROMEM/artifacts"),
                 Path("E:/Project/AAMAS/COPROMEM-review/artifacts")]
    exposed: set[str] = set(); trace: dict[str, list[str]] = {}
    for root in roots:
        if not root.is_dir():
            continue
        # Limit custody evidence to durable execution/scoring namespaces.  A
        # broad all-JSON traversal would both mistake public reports for runs
        # and needlessly parse large unrelated local test fixtures.
        candidates = list(root.glob("**/artifacts/**/trial-*.json"))
        candidates += list(root.glob("**/evaluation/**/trial-*.json"))
        for path in candidates:
            # Runtime payloads/DBs are never parsed by this custody scanner.
            if any(part in {"data", "databases", "payloads"} for part in path.parts):
                continue
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            candidates = value if isinstance(value, list) else [value]
            for row in candidates:
                if not isinstance(row, Mapping):
                    continue
                task = row.get("task_id")
                if not isinstance(task, str):
                    continue
                # Only durable execution/scoring vocabulary establishes hard
                # exposure.  Public inventories/reports/descriptors do not.
                if any(field in row for field in ("after_score", "official_score", "history", "actions", "trajectory_id")):
                    exposed.add(task); trace.setdefault(task, []).append(str(path))
    return exposed, trace


def _protocol_excluded_task_ids() -> set[str]:
    """Read an explicit pre-execution allocation exclusion, if registered.

    Hard custody is evidence-driven.  A successor may additionally exclude a
    previously frozen engineering triple as a protocol decision even where a
    withheld member has no hard execution evidence.  Keeping the categories
    separate prevents a public mention from being misreported as execution.
    """
    raw = os.environ.get("REASONINGBANK_PROTOCOL_EXCLUDED_TASK_IDS_JSON", "[]")
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("ReasoningBank protocol exclusion list is malformed") from exc
    if not isinstance(values, list) or not all(isinstance(item, str) and item for item in values):
        raise RuntimeError("ReasoningBank protocol exclusion list must be a string list")
    return set(values)


def _allocation() -> dict[str, Any]:
    inventory_path = _public_inventory_path()
    raw = json.loads(inventory_path.read_text(encoding="utf-8"))
    if raw.get("split") != "dev" or raw.get("public_only") is not True or not isinstance(raw.get("tasks"), list):
        raise RuntimeError("descriptor inventory is not the permitted public development inventory")
    exposed, trace = _hard_exposed_task_ids()
    protocol_excluded = _protocol_excluded_task_ids()
    rows = []
    for item in raw["tasks"]:
        if not isinstance(item, Mapping) or not isinstance(item.get("task_id"), str) or not isinstance(item.get("instruction"), str):
            raise RuntimeError("public descriptor record is malformed")
        task = item["task_id"]
        descriptor = {"normalized_instruction": _normalize_instruction(item["instruction"]),
                      "public_app_descriptions_sha256": sha256(item.get("app_descriptions", {}))}
        rows.append({"task_id": task, "family": _family(task), "descriptor": descriptor,
                     "descriptor_sha256": sha256(descriptor)})
    eligible = [row for row in rows if row["task_id"] not in exposed | protocol_excluded]
    pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(sorted(eligible, key=lambda row: row["task_id"])):
        for right in sorted(eligible, key=lambda row: row["task_id"])[left_index + 1:]:
            if left["task_id"] == right["task_id"] or left["descriptor_sha256"] != right["descriptor_sha256"]:
                continue
            # A/B are an exact public structural pair, but do not need the
            # same ID prefix; the descriptor is the preregistered relation.
            negatives = [item for item in eligible if item["task_id"] not in {left["task_id"], right["task_id"]}
                         and item["descriptor_sha256"] != left["descriptor_sha256"]]
            for negative in negatives:
                pairs.append({"a": left, "b": right, "negative": negative})
    pairs.sort(key=lambda row: (row["a"]["descriptor_sha256"], row["a"]["task_id"],
                                row["b"]["task_id"], row["negative"]["descriptor_sha256"], row["negative"]["task_id"]))
    selected = pairs[0] if pairs else None
    return {"version": "reasoningbank-appworld-public-dev-allocation-v1", "split": "dev",
            "payloads_opened": False, "provider_calls": 0, "test_normal_used": False,
            "inventory_sha256": file_sha(inventory_path), "inventory_count": len(rows),
            "hard_exclusion_count": len(exposed), "hard_exclusion_sha256": sha256(sorted(exposed)),
            "hard_exposure_evidence_sha256": sha256({key: sorted(value) for key, value in sorted(trace.items())}),
            "protocol_exclusion_count": len(protocol_excluded),
            "protocol_exclusion_sha256": sha256(sorted(protocol_excluded)),
            "protocol_exclusion_reason": "previously_frozen_engineering_allocation",
            "candidate_list_sha256": sha256(pairs), "candidate_count": len(pairs),
            "ordering_rule": "(A descriptor SHA-256, A ID, B ID, N descriptor SHA-256, N ID)",
            "selected": selected}


def _historical_exposure() -> float:
    raw = os.environ.get("REASONINGBANK_HISTORICAL_EXPOSURE_USD", "0")
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError("ReasoningBank historical exposure is malformed") from exc
    if not math.isfinite(value) or value < 0:
        raise RuntimeError("ReasoningBank historical exposure must be finite and nonnegative")
    return value


def _budget(historical_exposure_usd: float) -> dict[str, Any]:
    limits = {"executor": 12 * 30, "reasoningbank_judge": 6,
              "reasoningbank_extraction": 6, "reasoningbank_embedding": 12}
    chat = 32768 * INPUT_PRICE + MAX_OUTPUT_TOKENS * OUTPUT_PRICE
    embedding = 8192 * (0.02 / 1_000_000)
    contribution = {"executor_usd": limits["executor"] * chat,
                    "judge_usd": limits["reasoningbank_judge"] * chat,
                    "extractor_usd": limits["reasoningbank_extraction"] * chat,
                    "embedding_usd": limits["reasoningbank_embedding"] * embedding}
    dispatchable = sum(contribution.values()); contingency = dispatchable * .15
    return {"call_limits": limits, **contribution, "historical_exposure_usd": historical_exposure_usd,
            "dispatchable_usd": dispatchable, "contingency_usd": contingency,
            "all_in_usd": historical_exposure_usd + dispatchable + contingency,
            "hard_cap_usd": HARD_CAP}


def prepare(run: Path) -> None:
    if run.exists() and any(path.name != "allocation-audit.json" for path in run.iterdir()):
        raise RuntimeError("engineering run directory is nonempty")
    validate_protocol(protocol_record())
    allocation = _allocation()
    run.mkdir(parents=True, exist_ok=True)
    audit = {key: value for key, value in allocation.items() if key != "selected"}
    audit_path = run / "allocation-audit.json"
    if audit_path.exists():
        if json.loads(audit_path.read_text(encoding="utf-8")) != audit:
            raise RuntimeError("interrupted public allocation audit does not reproduce exactly")
    else:
        _fsync_json(audit_path, audit)
    if allocation["selected"] is None:
        raise RuntimeError("no unexecuted public development A/B/N allocation exists")
    historical_exposure = _historical_exposure()
    budget = _budget(historical_exposure)
    if budget["all_in_usd"] > HARD_CAP:
        raise RuntimeError("registered conservative bound exceeds the hard cap")
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    selected = allocation["selected"]
    template = {"version": RUN_VERSION, "engineering_validation_only": True, "git_commit": source_commit(),
                "protocol": protocol_record(), "protocol_sha256": sha256(protocol_record()),
                "evaluation": {"split": "dev", "task_ids": [selected["a"]["task_id"], selected["b"]["task_id"], selected["negative"]["task_id"]],
                               "roles": {"A": selected["a"]["task_id"], "B": selected["b"]["task_id"], "N": selected["negative"]["task_id"]},
                               "descriptor_sha256s": {key: selected[key]["descriptor_sha256"] for key in ("a", "b", "negative")},
                               "seeds": SEEDS, "expected_trajectories": 12, "task_order": "A_then_B_then_N_task_major"},
                "arms": ARMS, "execution": {"model": "deepseek/deepseek-v4.1-flash", "provider_only": "deepseek",
                              "fallbacks": False, "reasoning_enabled": False, "executor_temperature": .7,
                              "judge_temperature": 0.0, "extractor_temperature": 1.0, "max_actions": 30,
                              "storage_policy_gib": {"launch": 5, "warning": 4, "stop": 3}},
                "embedding": protocol_record()["embedding"], "registry_sha256": registry["registry_sha256"],
                "initial_bank": ReasoningBank().state(), "initial_bank_sha256": ReasoningBank().state()["semantic_state_sha256"],
                "allocation": allocation, "budget": budget,
                "historical_infrastructure_exposure_usd": historical_exposure,
                "historical_carry_forward_id": HISTORICAL_CARRY_ID}
    _fsync_json(run / "template.json", template)


def _recovery_envelope(source_run: Path) -> dict[str, Any]:
    """Validate the one permitted immutable predecessor artifact read-only."""
    source = source_run.resolve()
    source_manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if file_sha(source / "manifest.json") != (source / "manifest.sha256").read_text(encoding="utf-8").strip():
        raise RuntimeError("recovery source manifest is hash-inconsistent")
    task, arm, trial, seed = "fac291d_1", "no_memory", 1, 9701
    artifact_path = source / "artifacts" / task / arm / "trial-1.json"
    row = json.loads(artifact_path.read_text(encoding="utf-8"))
    validate_evidence(row, run_root=source, expected_registry_sha256=source_manifest["registry_sha256"])
    if (row.get("task_id"), row.get("arm"), row.get("trial_id"), row.get("seed")) != (task, arm, trial, seed):
        raise RuntimeError("recovery artifact identity is not the frozen completed key")
    if not isinstance(row.get("official_scorer_evidence"), Mapping):
        raise RuntimeError("recovery artifact lacks official scorer evidence")
    calls: dict[str, set[str]] = {"reserve": set(), "settle": set()}
    for line in (source / "ledger.jsonl").read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        if str(item.get("role", "")).startswith("executor:no_memory:fac291d_1:trial=1:seed=9701"):
            calls[str(item.get("event"))].add(str(item.get("id")))
    if not calls["reserve"] or calls["reserve"] != calls["settle"]:
        raise RuntimeError("recovery artifact executor settlements are incomplete")
    journal = Path(str(row["execution_evidence_path"]))
    return {"version": "reasoningbank-recovery-import-v1", "source_run_path_sha256": sha256(str(source)),
            "source_manifest_sha256": file_sha(source / "manifest.json"),
            "source_artifact_path_sha256": sha256(str(artifact_path)), "source_artifact_sha256": file_sha(artifact_path),
            "source_journal_sha256": str(row["execution_evidence_sha256"]),
            "source_journal_rows": int(row["execution_evidence_rows"]),
            "source_official_score": float(row["after_score"]), "source_actions": int(row["actions"]),
            "source_history_sha256": str(row["history_sha256"]),
            "source_executor_settlement_ids": sorted(calls["settle"]),
            "key": {"task_id": task, "arm": arm, "trial_id": trial, "seed": seed,
                    "trajectory_id": str(row["trajectory_id"])}}


def prepare_recovery(run: Path, source_run: Path) -> None:
    if run.exists() and any(run.iterdir()):
        raise RuntimeError("recovery run directory is nonempty")
    envelope = _recovery_envelope(source_run)
    source_manifest = json.loads((source_run / "manifest.json").read_text(encoding="utf-8"))
    historical = _historical_exposure(); budget = _budget(historical)
    if budget["all_in_usd"] > HARD_CAP:
        raise RuntimeError("registered conservative bound exceeds the hard cap")
    template = {**source_manifest, "version": "reasoningbank-appworld-engineering-recovery-v1",
                "git_commit": source_commit(), "budget": budget,
                "historical_infrastructure_exposure_usd": historical,
                "historical_carry_forward_id": HISTORICAL_CARRY_ID,
                "recovery_import": envelope}
    run.mkdir(parents=True, exist_ok=True); _fsync_json(run / "template.json", template)


def import_recovery(run: Path) -> None:
    manifest = load(run)
    expected = dict(manifest.get("recovery_import") or {})
    if not expected:
        raise RuntimeError("recovery manifest lacks its import envelope")
    source = (Path("/mnt/e/Project/AAMAS/reasoningbank-appworld-artifacts/reasoningbank_appworld_engineering_002")
              if os.name == "posix" else Path("E:/Project/AAMAS/reasoningbank-appworld-artifacts/reasoningbank_appworld_engineering_002"))
    actual = _recovery_envelope(source)
    if actual != expected:
        raise RuntimeError("recovery import evidence no longer matches the frozen envelope")
    payload = {**actual, "transition": "recovery_import_completed"}
    payload["record_sha256"] = sha256(payload)
    _fsync_json(run / "recovery-import-completed.json", payload)
    # Read back verifies the marker before it is allowed to count.
    loaded = json.loads((run / "recovery-import-completed.json").read_text(encoding="utf-8"))
    copy = dict(loaded); marker_hash = copy.pop("record_sha256")
    if marker_hash != sha256(copy):
        raise RuntimeError("recovery import completion marker reload failed")


def _imported_key(manifest: Mapping[str, Any], run: Path) -> tuple[str, str, int, int] | None:
    path = run / "recovery-import-completed.json"
    if not path.is_file(): return None
    value = json.loads(path.read_text(encoding="utf-8")); copy = dict(value); digest = copy.pop("record_sha256", None)
    if digest != sha256(copy):
        raise RuntimeError("recovery import completion marker is malformed")
    key = value.get("key")
    if not isinstance(key, Mapping): raise RuntimeError("recovery import key is absent")
    return str(key["arm"]), str(key["task_id"]), int(key["trial_id"]), int(key["seed"])


def freeze(run: Path) -> None:
    template = json.loads((run / "template.json").read_text(encoding="utf-8"))
    if template["git_commit"] != source_commit():
        raise RuntimeError("executable source changed after public allocation")
    if (run / "manifest.json").exists():
        raise RuntimeError("manifest is already frozen")
    _fsync_json(run / "manifest.json", template)
    (run / "manifest.sha256").write_text(file_sha(run / "manifest.json") + "\n", encoding="utf-8")


def load(run: Path) -> dict[str, Any]:
    if not (run / "manifest.json").is_file() or file_sha(run / "manifest.json") != (run / "manifest.sha256").read_text(encoding="utf-8").strip():
        raise RuntimeError("manifest is absent or hash-inconsistent")
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    if manifest["git_commit"] != source_commit():
        raise RuntimeError("runtime source does not equal frozen manifest commit")
    validate_protocol(manifest["protocol"])
    if manifest["budget"]["all_in_usd"] > HARD_CAP:
        raise RuntimeError("frozen bound exceeds hard cap")
    _storage_guard("preflight")
    return manifest


def _credential() -> str:
    value = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not value:
        raise RuntimeError("OPENROUTER_API_KEY is unavailable")
    return value


def _status(run: Path, state: str, **extra: Any) -> None:
    _fsync_json(run / "runner-status.json", {"state": state, "pid": os.getpid(), "updated_ns": time.time_ns(), **extra})


def _summary(run: Path, manifest: Mapping[str, Any], state: str, final: bool = False) -> None:
    historical = float(manifest["historical_infrastructure_exposure_usd"])
    historical_id = str(manifest.get("historical_carry_forward_id") or
                        (HISTORICAL_CARRY_ID if historical else "historical-construction-carry"))
    summary = build_live_summary(ledger_path=run / "ledger.jsonl", artifact_root=run / "artifacts",
                                 expected_tasks=manifest["evaluation"]["task_ids"], expected_seeds=SEEDS,
                                 historical_expected_usd=historical, historical_id=historical_id, state=state, final=False,
                                 expected_trajectories=12, registered_arms=ARMS)
    summary = dict(summary); imported = _imported_key(manifest, run)
    if imported:
        envelope = manifest["recovery_import"]; arm, _task, _trial, _seed = imported
        stats = dict(summary["arms"][arm]); stats.update({"Completed": stats["Completed"] + 1,
            "Successes": stats["Successes"] + int(float(envelope["source_official_score"]) == 1.0),
            "AvgScore": (stats["AvgScore"] * (stats["Completed"] - 1) + float(envelope["source_official_score"])) / stats["Completed"],
            "AvgActions": (stats["AvgActions"] * (stats["Completed"] - 1) + int(envelope["source_actions"])) / stats["Completed"]})
        summary["arms"] = {**summary["arms"], arm: stats}; summary["completed"] += 1
    if final and summary["completed"] != 12:
        raise RuntimeError("terminal reconciliation requires the imported prefix plus eleven new trajectories")
    write_live_summary(run / "live-summary.json", summary)


def _reconciled_marker(run: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    payload = {"version": RUN_VERSION, "transition": "run_reconciled", "manifest_sha256": file_sha(run / "manifest.json"),
               "source_commit": manifest["git_commit"], "artifact_inventory_sha256": sha256(sorted(file_sha(path) for path in (run / "artifacts").glob("**/*.json"))),
               "checkpoint_inventory_sha256": sha256(sorted(file_sha(path) for path in (run / "reasoningbank-dynamic-checkpoints").glob("**/*.json"))),
               "ledger_sha256": file_sha(run / "ledger.jsonl"), "live_summary_sha256": file_sha(run / "live-summary.json")}
    payload["record_sha256"] = sha256(payload)
    _fsync_json(run / "run-reconciled.json", payload)
    return payload


def _write_final(run: Path, manifest: Mapping[str, Any], marker: Mapping[str, Any]) -> None:
    summary = json.loads((run / "live-summary.json").read_text(encoding="utf-8"))
    report = {"version": RUN_VERSION, "engineering_validation_only": True, "manifest_sha256": file_sha(run / "manifest.json"),
              "run_reconciled_sha256": marker["record_sha256"], "summary": summary}
    _fsync_json(run / "final-report.json", report)
    (run / "FINAL_REPORT.md").write_text("# ReasoningBank-AppWorld engineering validation\n\n"
                                           "This is an integration diagnostic, not an efficacy or superiority result.\n",
                                           encoding="utf-8")


def run(run: Path, *, preflight: bool = False) -> None:
    manifest = load(run)
    _status(run, "preflight_passed", manifest_sha256=file_sha(run / "manifest.json"))
    if preflight:
        return
    lock = run / "runner.lock"
    if lock.exists():
        raise RuntimeError("duplicate ReasoningBank runner lock exists")
    _fsync_json(lock, {"pid": os.getpid()})
    try:
        imported = _imported_key(manifest, run)
        if manifest.get("recovery_import") and imported is None:
            raise RuntimeError("recovery import marker is absent")
        key = _credential(); _storage_guard("launch")
        ledger = AppendOnlyLedger(run / "ledger.jsonl", HARD_CAP, manifest["budget"]["call_limits"])
        # The reconciler requires a single carried-exposure record.  This is
        # created before any payload is opened or provider boundary is reached
        # and is never attributed to an Engineering result arm.
        if not (run / "ledger.jsonl").exists():
            historical = float(manifest["historical_infrastructure_exposure_usd"])
            historical_id = str(manifest.get("historical_carry_forward_id") or
                                (HISTORICAL_CARRY_ID if historical else "historical-construction-carry"))
            ledger.reserve(historical_id, historical, {"role": "historical_carry_forward"})
            ledger.settle(historical_id, historical, {"role": "historical_carry_forward"})
        initial = ReasoningBank.restore(manifest["initial_bank"])
        checkpoint = ReasoningBankDynamicCheckpoints(root=run / "reasoningbank-dynamic-checkpoints",
                                                     expected_trajectory_ids=[f"evaluation:reasoningbank_dynamic:{task}:trial={trial}:seed={seed}"
                                                                              for task in manifest["evaluation"]["task_ids"]
                                                                              for trial, seed in enumerate(SEEDS, 1)],
                                                     ledger_path=run / "ledger.jsonl")
        prefix = checkpoint.reconcile(initial)
        bank = prefix.restored_bank
        providers = ReasoningBankProviders(api_key=key, ledger=ledger, progress=run / "progress.jsonl")
        lifecycle = ReasoningBankLifecycle(bank=bank, embedder=SharedAzureOpenRouterEmbedder(api_key=key, ledger=ledger, progress=run / "progress.jsonl"),
                                           judge=providers.judge, extractor=providers.extract)
        runtime = ReasoningBankDynamicRuntime(lifecycle=lifecycle, initial_bank=initial, checkpoints=checkpoint,
                                              run_root=run, registry_sha256=manifest["registry_sha256"])
        evidence = {"registry_path": str(REGISTRY.resolve()), "registry_sha256": manifest["registry_sha256"]}
        _status(run, "running", manifest_sha256=file_sha(run / "manifest.json"), completed_update_prefix=len(prefix.completed))
        for task in manifest["evaluation"]["task_ids"]:
            for arm in ARMS:
                for trial, seed in enumerate(SEEDS, 1):
                    target = run / "artifacts" / task / arm / f"trial-{trial}.json"
                    key_identity = (arm, task, trial, seed)
                    if key_identity == imported:
                        continue
                    if target.is_file():
                        row = json.loads(target.read_text(encoding="utf-8"))
                        validate_evidence(row, run_root=run, expected_registry_sha256=manifest["registry_sha256"])
                        continue
                    _storage_guard("task dispatch")
                    retrieval_path = run / "retrievals" / task / f"{arm}-trial-{trial}.json"
                    kwargs: dict[str, Any] = {}
                    if arm == "reasoningbank_dynamic":
                        kwargs["memory_for_instruction"] = runtime.retrieval_callback(retrieval_path)
                        kwargs["post_score_update"] = runtime.strict_post_score_callback(retrieval_path)
                        kwargs["post_score_update_strict"] = True
                    execute_trajectory(run=run, progress=run / "progress.jsonl", ledger=ledger, api_key=key,
                                       all_task_ids=list(manifest["evaluation"]["task_ids"]), arm=arm, task_id=task,
                                       trial_id=trial, seed=seed, max_actions=30, temperature=.7, phase="evaluation",
                                       artifact_path=target, execution_evidence=evidence, **kwargs)
                    _summary(run, manifest, "running")
        final_prefix = checkpoint.reconcile(initial)
        if final_prefix.next_trajectory_id is not None:
            raise RuntimeError("ReasoningBank Dynamic checkpoint prefix is incomplete at terminal reconciliation")
        _summary(run, manifest, "completed", final=True)
        marker = _reconciled_marker(run, manifest); _write_final(run, manifest, marker)
        _status(run, "completed", manifest_sha256=file_sha(run / "manifest.json"), run_reconciled_sha256=marker["record_sha256"])
    except BaseException as exc:
        _status(run, "failed", error_type=type(exc).__name__)
        append(run / "progress.jsonl", {"event": "runner_failed", "error_type": type(exc).__name__})
        raise
    finally:
        if lock.exists():
            lock.unlink()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "prepare-recovery", "freeze", "import-recovery", "preflight", "run"))
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--source-run", type=Path)
    args = parser.parse_args(); run_path = args.run.resolve()
    if args.command == "prepare": prepare(run_path)
    elif args.command == "prepare-recovery":
        if args.source_run is None: parser.error("prepare-recovery requires --source-run")
        prepare_recovery(run_path, args.source_run.resolve())
    elif args.command == "freeze": freeze(run_path)
    elif args.command == "import-recovery": import_recovery(run_path)
    else: run(run_path, preflight=args.command == "preflight")


if __name__ == "__main__":
    main()
