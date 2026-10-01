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
from types import MappingProxyType
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from copromem.experiments.reme_copromem.evidence_contract import validate as validate_evidence
from copromem.experiments.reme_copromem.live_summary import build_live_summary, write_live_summary
from copromem.experiments.reme_copromem.runner import AppendOnlyLedger, append, execute_trajectory, write_json
from copromem.experiments.reme_copromem.runtime_identity_binding import read as read_runtime_identity_binding
from copromem.integrations.reasoning_bank.appworld import ReasoningBank, sha256
from copromem.integrations.reasoning_bank.appworld_protocol import protocol_record, validate_protocol
from copromem.integrations.reasoning_bank.checkpoints import CheckpointPrefix, ReasoningBankDynamicCheckpoints
from copromem.integrations.reasoning_bank.dynamic_runtime import ReasoningBankDynamicRuntime
from copromem.integrations.reasoning_bank.lifecycle import ReasoningBankLifecycle
from copromem.integrations.reasoning_bank.providers import ReasoningBankProviders
from copromem.integrations.reasoning_bank.retrieval_provenance import ContentAddressedStore, canonical_identity, verify as verify_retrieval
from copromem.integrations.reasoning_bank.recovery import (
    build_envelope as build_recovery_envelope,
    load_marker as load_recovery_marker,
    publish_marker as publish_recovery_marker,
    validate_envelope as validate_recovery_envelope,
)
from copromem.integrations.reasoning_bank.recovery_admission import (
    resolve_source_run as resolve_recovery_source_run,
    validate_spec as validate_recovery_admission,
)
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
        external_artifacts = (Path("/mnt/e/Project/AAMAS/reasoningbank-appworld-artifacts")
                              if os.name == "posix"
                              else Path("E:/Project/AAMAS/reasoningbank-appworld-artifacts"))
        roots = [ROOT / "artifacts", Path("E:/Project/AAMAS/COPROMEM/artifacts"),
                 Path("E:/Project/AAMAS/COPROMEM-review/artifacts"), external_artifacts]
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


def _publication_commit() -> str:
    value = os.environ.get("REASONINGBANK_PUBLICATION_COMMIT", "").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise RuntimeError("REASONINGBANK_PUBLICATION_COMMIT must identify the frozen allocation publication")
    return value


RUNTIME_IDENTITY_VERSION = "reasoningbank-appworld-runtime-content-v2"


def _capture_python_runtime_identity() -> dict[str, Any]:
    """Capture the one interpreter contract allowed in a new frozen manifest."""
    import importlib.util
    checker_path = ROOT / "scripts" / "check_reasoningbank_appworld_runtime.py"
    spec = importlib.util.spec_from_file_location("copromem_python_runtime_gate", checker_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("production Python runtime gate module is unavailable")
    checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
    interpreter = Path(os.environ.get("REASONINGBANK_PRODUCTION_PYTHON", "/home/xiqhq/copromem-appworld/venv/bin/python"))
    agent_root = Path(os.environ.get("REASONINGBANK_APPWORLD_AGENT_ROOT", "/home/xiqhq/copromem-reme/benchmark/appworld"))
    return checker.build_identity(expected_python=interpreter, agent_root=agent_root, runtime_root=ROOT)


def _python_runtime_manifest(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    value = manifest.get("python_runtime")
    required = {"version", "python_executable", "python_version", "python_prefix", "python_base_prefix",
                "ray_version", "appworld_version", "dependency_set_sha256", "appworld_react_agent_sha256",
                "appworld_module_sha256", "entrypoint_sha256", "imports", "runtime_identity_sha256"}
    if not isinstance(value, Mapping) or set(value) != required:
        raise RuntimeError("frozen manifest lacks a complete production Python runtime identity")
    if not isinstance(value["python_executable"], str) or not value["python_executable"].startswith("/"):
        raise RuntimeError("frozen manifest production Python executable is not absolute")
    return value


def _runtime_identity_material(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Use only frozen manifest content; never infer identity from HEAD at dispatch."""
    python_runtime = _python_runtime_manifest(manifest)
    material = {"version": RUNTIME_IDENTITY_VERSION, "executable_commit": str(manifest.get("git_commit") or ""),
            "protocol_sha256": str(manifest.get("protocol_sha256") or ""),
            "registry_sha256": str(manifest.get("registry_sha256") or ""),
            "initial_bank_sha256": str(manifest.get("initial_bank_sha256") or ""),
            "execution_sha256": sha256(manifest.get("execution")), "embedding_sha256": sha256(manifest.get("embedding")),
            "allocation_sha256": sha256(manifest.get("allocation")),
            "python_runtime_identity_sha256": str(python_runtime["runtime_identity_sha256"]),
            "recovery_envelope_sha256": str((manifest.get("recovery_import") or {}).get("envelope_sha256") or "")}
    if manifest.get("recovery_admission_spec"):
        material["recovery_admission_spec_sha256"] = str(manifest["recovery_admission_spec"].get("recovery_spec_sha256") or "")
    return material


def _runtime_identity_digest(manifest: Mapping[str, Any]) -> str:
    material = _runtime_identity_material(manifest)
    if not all(material[key] for key in ("executable_commit", "protocol_sha256", "registry_sha256", "initial_bank_sha256")):
        raise RuntimeError("frozen manifest lacks a runtime-content identity component")
    return sha256(material)


def _runtime_identity(run: Path, manifest: Mapping[str, Any]) -> str:
    """Durably materialize and verify the manifest-declared runtime identity."""
    expected = _runtime_identity_digest(manifest)
    if manifest.get("runtime_identity_version") != RUNTIME_IDENTITY_VERSION or manifest.get("runtime_identity_sha256") != expected:
        raise RuntimeError("frozen manifest runtime-content identity is inconsistent")
    path = run / "runtime-identity.json"
    record = {"version": RUNTIME_IDENTITY_VERSION, "manifest_sha256": file_sha(run / "manifest.json"),
              "runtime_identity_sha256": expected, "material": _runtime_identity_material(manifest)}
    if path.exists():
        try: observed = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc: raise RuntimeError("runtime-content identity is malformed") from exc
        if observed != record:
            raise RuntimeError("runtime-content identity differs from the frozen manifest")
    else:
        _fsync_json(path, record)
    record_sha256 = file_sha(path)
    binding = {"runtime_identity_sha256": expected, "runtime_identity_record_sha256": record_sha256}
    binding_path = run / "runtime-identity.binding.json"
    if binding_path.exists():
        try: observed_binding = json.loads(binding_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc: raise RuntimeError("runtime identity binding is malformed") from exc
        if observed_binding != binding:
            raise RuntimeError("runtime identity binding differs from the frozen record")
    else:
        _fsync_json(binding_path, binding)
    return expected


def _verify_python_runtime_identity(run: Path, manifest: Mapping[str, Any]) -> None:
    expected = dict(_python_runtime_manifest(manifest))
    path = run / "python-runtime-identity.json"
    try:
        observed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("production Python dependency gate record is absent or malformed") from exc
    if observed != expected:
        raise RuntimeError("production Python runtime identity differs from the frozen manifest")


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
    python_runtime = _capture_python_runtime_identity()
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
                "historical_carry_forward_id": HISTORICAL_CARRY_ID, "python_runtime": python_runtime}
    template.update({"runtime_identity_version": RUNTIME_IDENTITY_VERSION})
    template["runtime_identity_sha256"] = _runtime_identity_digest(template)
    _fsync_json(run / "template.json", template)


def _recovery_envelope(source_run: Path) -> dict[str, Any]:
    """Validate the one permitted immutable predecessor artifact read-only."""
    return build_recovery_envelope(source_run, task_id="fac291d_1", arm="no_memory", trial_id=1, seed=9701)


def _schedule(manifest: Mapping[str, Any]) -> list[tuple[str, str, int, int]]:
    seeds = [int(item) for item in manifest["evaluation"]["seeds"]]
    return [(arm, str(task), trial, seed)
            for task in manifest["evaluation"]["task_ids"]
            for arm in manifest["arms"]
            for trial, seed in enumerate(seeds, 1)]


def _frozen_next_key(manifest: Mapping[str, Any], envelope: Mapping[str, Any]) -> dict[str, Any]:
    schedule = _schedule(manifest); position = int(envelope["successor_allocation_position"])
    key = envelope["key"]
    imported = (str(key["arm"]), str(key["task_id"]), int(key["trial_id"]), int(key["seed"]))
    if position >= len(schedule) or schedule[position] != imported or position + 1 >= len(schedule):
        raise RuntimeError("recovery envelope does not identify the expected schedule prefix")
    arm, task, trial, seed = schedule[position + 1]
    return {"arm": arm, "task_id": task, "trial_id": trial, "seed": seed}


def prepare_recovery(run: Path, source_run: Path) -> None:
    if run.exists() and any(run.iterdir()):
        raise RuntimeError("recovery run directory is nonempty")
    envelope = _recovery_envelope(source_run)
    source_manifest = json.loads((source_run / "manifest.json").read_text(encoding="utf-8"))
    historical = _historical_exposure(); budget = _budget(historical)
    if budget["all_in_usd"] > HARD_CAP:
        raise RuntimeError("registered conservative bound exceeds the hard cap")
    if source_manifest.get("initial_bank", {}).get("experiences") != []:
        raise RuntimeError("recovery predecessor does not have the frozen empty initial bank")
    template = {**source_manifest, "version": "reasoningbank-appworld-engineering-recovery-v2",
                "git_commit": source_commit(), "budget": budget,
                "python_runtime": _capture_python_runtime_identity(),
                "allocation_publication_commit": _publication_commit(),
                "historical_infrastructure_exposure_usd": historical,
                "historical_carry_forward_id": HISTORICAL_CARRY_ID,
                "recovery_import": envelope,
                "recovery_next_key": _frozen_next_key(source_manifest, envelope)}
    template.update({"runtime_identity_version": RUNTIME_IDENTITY_VERSION})
    template["runtime_identity_sha256"] = _runtime_identity_digest(template)
    run.mkdir(parents=True, exist_ok=True); _fsync_json(run / "template.json", template)


def import_recovery(run: Path) -> None:
    manifest = load(run)
    expected = dict(manifest.get("recovery_import") or {})
    if not expected:
        raise RuntimeError("recovery manifest lacks its import envelope")
    source = (Path("/mnt/e/Project/AAMAS/reasoningbank-appworld-artifacts/reasoningbank_appworld_engineering_002")
              if os.name == "posix" else Path("E:/Project/AAMAS/reasoningbank-appworld-artifacts/reasoningbank_appworld_engineering_002"))
    actual = validate_recovery_envelope(expected, source)
    publish_recovery_marker(run / "recovery-import-completed.json", envelope=actual)


def _imported_key(manifest: Mapping[str, Any], run: Path) -> tuple[str, str, int, int] | None:
    path = run / "recovery-import-completed.json"
    if not path.is_file(): return None
    expected = manifest.get("recovery_import")
    if not isinstance(expected, Mapping):
        raise RuntimeError("recovery manifest has no frozen import envelope")
    value = load_recovery_marker(path, envelope=expected)
    key = value.get("envelope", {}).get("key")
    if not isinstance(key, Mapping): raise RuntimeError("recovery import key is absent")
    return str(key["arm"]), str(key["task_id"]), int(key["trial_id"]), int(key["seed"])


def _retrieval_identity(manifest: Mapping[str, Any], run: Path, arm: str, task: str,
                        trial: int, seed: int) -> Mapping[str, Any]:
    """Freeze the exact public identity used by every trajectory boundary."""
    return MappingProxyType(canonical_identity({
        "task_id": task, "arm": arm, "trial_id": trial, "seed": seed,
        "trajectory_id": f"evaluation:{arm}:{task}:trial={trial}:seed={seed}",
        "benchmark": "appworld", "manifest_sha256": file_sha(run / "manifest.json"),
        "runtime_identity_sha256": manifest["runtime_identity_sha256"],
        "registry_sha256": manifest["registry_sha256"],
    }))


def _reconcile_execution_prefix(manifest: Mapping[str, Any], run: Path,
                                admission: Mapping[str, Any] | None = None) -> tuple[int, tuple[str, str, int, int] | None]:
    schedule = _schedule(manifest); completed: set[tuple[str, str, int, int]] = set()
    imported = _imported_key(manifest, run)
    if imported is not None: completed.add(imported)
    for arm, task, trial, seed in schedule:
        path = run / "artifacts" / task / arm / f"trial-{trial}.json"
        retrieval_path = run / "retrievals" / task / f"{arm}-trial-{trial}.json"
        if not path.is_file():
            if arm == "reasoningbank_dynamic" and (retrieval_path.exists() or
                    retrieval_path.with_name(retrieval_path.name + ".prompt-binding.json").exists()):
                raise RuntimeError("partial ReasoningBank retrieval exists without a scored artifact")
            continue
        row = json.loads(path.read_text(encoding="utf-8"))
        validate_evidence(row, run_root=run, expected_registry_sha256=manifest["registry_sha256"])
        if (str(row.get("arm")), str(row.get("task_id")), int(row.get("trial_id")), int(row.get("seed"))) != (arm, task, trial, seed):
            raise RuntimeError("successor artifact identity differs from its schedule key")
        completed.add((arm, task, trial, seed))
    prefix = 0
    for key in schedule:
        if key not in completed: break
        prefix += 1
    if completed != set(schedule[:prefix]):
        raise RuntimeError("successor completed work is not an ordered schedule prefix")
    for arm, task, trial, seed in schedule[:prefix]:
        if arm != "reasoningbank_dynamic" or (arm, task, trial, seed) == imported:
            continue
        retrieval_path = run / "retrievals" / task / f"{arm}-trial-{trial}.json"
        pending = admission.get("next_key") if admission is not None else None
        if isinstance(pending, Mapping) and (arm, task, trial, seed) == (
                str(pending["arm"]), str(pending["task_id"]), int(pending["trial_id"]), int(pending["seed"])):
            # The typed admission verifier needs the restored bank and is run
            # after runtime construction below.  At this early schedule pass,
            # only reject missing/partial files; never send the versioned
            # recovery record through the ordinary provenance verifier.
            binding = retrieval_path.with_suffix(retrieval_path.suffix + ".prompt-binding.json")
            if not retrieval_path.is_file() or not binding.is_file():
                raise RuntimeError("completed recovery trajectory lacks retrieval or prompt binding")
            continue
        retrieval = verify_retrieval(path=retrieval_path,
                                     store=ContentAddressedStore(run / "reasoningbank-retrieval-objects"),
                                     require_prompt_binding=True)
        identity = _retrieval_identity(manifest, run, arm, task, trial, seed)
        if retrieval["identity"] != dict(identity):
            raise RuntimeError("restarted ReasoningBank retrieval identity differs from frozen schedule")
        artifact_path = run / "artifacts" / task / arm / f"trial-{trial}.json"
        row = json.loads(artifact_path.read_text(encoding="utf-8"))
        binding_path = retrieval_path.with_name(retrieval_path.name + ".prompt-binding.json")
        binding = json.loads(binding_path.read_text(encoding="utf-8"))
        if (row.get("runtime_identity_sha256") != identity["runtime_identity_sha256"] or
                row.get("execution_evidence_registry_sha256") != identity["registry_sha256"] or
                row.get("initial_prompt_messages_sha256") != binding["initial_prompt_messages_sha256"]):
            raise RuntimeError("restarted ReasoningBank artifact differs from sealed identity or prompt")
    return prefix, None if prefix == len(schedule) else schedule[prefix]


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


def _checkpoint_prefix_from_manifest(manifest: Mapping[str, Any], admission: Mapping[str, Any] | None = None) -> CheckpointPrefix | None:
    """Open a frozen read-only checkpoint prefix without copying its records.

    The manifest supplies all locators and identities.  This deliberately has
    no run-name or experiment-name policy: every source is revalidated by the
    checkpoint manager before it can affect successor scheduling.
    """
    recovery = manifest.get("recovery_prefix")
    if recovery is None and admission is not None:
        ledger = admission["source_ledger"]; prefix = admission["checkpoint_prefix"]
        recovery = {"source_run": admission["source_run"], "source_ledger_relative": ledger["relative_locator"],
                    "source_ledger_sha256": ledger["sha256"], "checkpoint_root_relative": "reasoningbank-dynamic-checkpoints",
                    "checkpoint_count": prefix["count"], "checkpoint_prefix_identity_sha256": prefix["identity_sha256"],
                    "restored_bank_sha256": prefix["restored_bank_sha256"]}
    if recovery is None:
        return None
    if not isinstance(recovery, Mapping):
        raise RuntimeError("recovery prefix specification is malformed")
    source_root = resolve_recovery_source_run(str(recovery.get("source_run") or ""))
    ledger = source_root / str(recovery.get("source_ledger_relative") or "ledger.jsonl")
    expected_ledger = str(recovery.get("source_ledger_sha256") or "")
    if not source_root.is_dir() or not ledger.is_file() or file_sha(ledger) != expected_ledger:
        raise RuntimeError("recovery prefix source ledger identity differs from frozen specification")
    dynamic_ids = [f"evaluation:reasoningbank_dynamic:{task}:trial={trial}:seed={seed}"
                   for task in manifest["evaluation"]["task_ids"] for trial, seed in enumerate(SEEDS, 1)]
    prefix = CheckpointPrefix.from_source(root=source_root / str(recovery.get("checkpoint_root_relative") or "reasoningbank-dynamic-checkpoints"),
                                           expected_trajectory_ids=dynamic_ids, ledger_path=ledger,
                                           count=int(recovery.get("checkpoint_count") or 0),
                                           initial_bank=ReasoningBank.restore(manifest["initial_bank"]))
    if prefix.identity_sha256 != recovery.get("checkpoint_prefix_identity_sha256"):
        raise RuntimeError("recovery prefix checkpoint identity differs from frozen specification")
    if prefix.restored_bank.state()["semantic_state_sha256"] != recovery.get("restored_bank_sha256"):
        raise RuntimeError("recovery prefix restored bank differs from frozen specification")
    return prefix


def _imported_recovery_keys(manifest: Mapping[str, Any]) -> tuple[tuple[str, str, int, int], ...]:
    recovery = manifest.get("recovery_prefix")
    if recovery is None: return ()
    raw = recovery.get("imported_keys") if isinstance(recovery, Mapping) else None
    if not isinstance(raw, list): raise RuntimeError("recovery prefix has no ordered imported trajectory keys")
    keys = tuple((str(item.get("arm")), str(item.get("task_id")), int(item.get("trial_id")), int(item.get("seed")))
                 for item in raw if isinstance(item, Mapping))
    schedule = _schedule(manifest)
    if len(keys) != len(raw) or not keys or keys != tuple(schedule[:len(keys)]) or len(set(keys)) != len(keys):
        raise RuntimeError("recovery imported trajectories are not an exact ordered schedule prefix")
    expected = recovery.get("next_key")
    next_key = schedule[len(keys)] if len(keys) < len(schedule) else None
    if not isinstance(expected, Mapping) or next_key is None or dict(expected) != {"arm": next_key[0], "task_id": next_key[1], "trial_id": next_key[2], "seed": next_key[3]}:
        raise RuntimeError("recovery imported prefix does not admit its exact next trajectory")
    return keys


def _validated_recovery_admission(run: Path, manifest: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Reload the sole immutable admission marker before scheduling recovery work."""
    if "recovery_admission_spec" not in manifest:
        return None
    path = run / "recovery-admission-completed.json"
    if not path.is_file(): raise RuntimeError("frozen recovery admission marker is absent")
    value = json.loads(path.read_text(encoding="utf-8")); body = dict(value); bound = body.pop("marker_sha256", None)
    if bound != sha256(body) or value.get("transition") != "recovery_admitted":
        raise RuntimeError("recovery admission marker hash or transition is invalid")
    frozen = manifest["recovery_admission_spec"]
    if value.get("recovery_spec") != frozen or value.get("recovery_spec_sha256") != frozen.get("recovery_spec_sha256"):
        raise RuntimeError("recovery admission marker differs from frozen specification")
    return validate_recovery_admission(frozen)


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
        envelope = manifest["recovery_import"]; result = envelope["result"]; arm, _task, _trial, _seed = imported
        stats = dict(summary["arms"][arm]); prior = int(stats["Completed"]); completed = prior + 1
        successes = int(stats["Successes"]) + int(float(result["official_score"]) == 1.0)
        stats.update({"Completed": completed,
            "Successes": successes, "SuccessRate": successes / completed,
            "AvgScore": (stats["AvgScore"] * prior + float(result["official_score"])) / completed,
            "AvgActions": (stats["AvgActions"] * prior + int(result["actions"])) / completed})
        summary["arms"] = {**summary["arms"], arm: stats}; summary["completed"] += 1
    admission = _validated_recovery_admission(run, manifest)
    if admission is not None:
        arms = dict(summary["arms"])
        for envelope in admission["imported_envelopes"]:
            key = envelope["key"]; result = envelope["result"]; arm = str(key["arm"])
            stats = dict(arms[arm]); prior = int(stats["Completed"]); completed = prior + 1
            score = float(result["official_score"]); actions = int(result["actions"])
            successes = int(stats["Successes"]) + int(score == 1.0)
            stats.update({"Completed": completed, "Successes": successes,
                          "SuccessRate": successes / completed,
                          "AvgScore": (float(stats["AvgScore"]) * prior + score) / completed,
                          "AvgActions": (float(stats["AvgActions"]) * prior + actions) / completed})
            arms[arm] = stats
        summary["arms"] = arms
        summary["completed"] += len(admission["imported_envelopes"])
        summary.update({"imported_completed": len(admission["imported_envelopes"]),
                        "successor_completed": summary["completed"] - len(admission["imported_envelopes"]),
                        "referenced_checkpoints": int(admission["checkpoint_prefix"]["count"]),
                        "native_checkpoints": len(list((run / "reasoningbank-dynamic-checkpoints" / "completion-markers").glob("*.json")))})
    if final and summary["completed"] != 12:
        raise RuntimeError("terminal reconciliation requires exactly twelve registered trajectories")
    write_live_summary(run / "live-summary.json", summary)


def _reconciled_marker(run: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    payload = {"version": RUN_VERSION, "transition": "run_reconciled", "manifest_sha256": file_sha(run / "manifest.json"),
               "source_commit": manifest["git_commit"], "artifact_inventory_sha256": sha256(sorted(file_sha(path) for path in (run / "artifacts").glob("**/*.json"))),
               "checkpoint_inventory_sha256": sha256(sorted(file_sha(path) for path in (run / "reasoningbank-dynamic-checkpoints").glob("**/*.json"))),
               "ledger_sha256": file_sha(run / "ledger.jsonl"), "live_summary_sha256": file_sha(run / "live-summary.json"),
               "runtime_identity_sha256": manifest["runtime_identity_sha256"],
               "runtime_identity_record_sha256": read_runtime_identity_binding(run)["runtime_identity_record_sha256"]}
    if manifest.get("recovery_import"):
        payload.update({"recovery_envelope_sha256": manifest["recovery_import"]["envelope_sha256"],
                        "recovery_import_marker_sha256": file_sha(run / "recovery-import-completed.json")})
    if manifest.get("recovery_admission_spec"):
        admission = _validated_recovery_admission(run, manifest)
        payload.update({"recovery_admission_marker_sha256": file_sha(run / "recovery-admission-completed.json"),
                        "recovery_spec_sha256": admission["recovery_spec_sha256"],
                        "checkpoint_prefix_identity_sha256": admission["checkpoint_prefix"]["identity_sha256"],
                        "source_ledger_sha256": admission["source_ledger"]["sha256"],
                        "imported_artifact_count": len(admission["imported_envelopes"])})
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
    _verify_python_runtime_identity(run, manifest)
    runtime_identity_sha256 = _runtime_identity(run, manifest)
    runtime_identity_record_sha256 = read_runtime_identity_binding(run)["runtime_identity_record_sha256"]
    _status(run, "preflight_passed", manifest_sha256=file_sha(run / "manifest.json"))
    if preflight:
        return
    lock = run / "runner.lock"
    if lock.exists():
        raise RuntimeError("duplicate ReasoningBank runner lock exists")
    _fsync_json(lock, {"pid": os.getpid()})
    try:
        admission = _validated_recovery_admission(run, manifest)
        imported = _imported_key(manifest, run)
        imported_prefix = (_imported_recovery_keys(manifest) if admission is None else tuple(
            (str(item["key"]["arm"]), str(item["key"]["task_id"]), int(item["key"]["trial_id"]), int(item["key"]["seed"]))
            for item in admission["imported_envelopes"]))
        if admission is not None:
            expected = dict(admission["next_key"]); schedule = _schedule(manifest)
            if tuple(imported_prefix) != tuple(schedule[:len(imported_prefix)]) or expected != {"arm": schedule[len(imported_prefix)][0], "task_id": schedule[len(imported_prefix)][1], "trial_id": schedule[len(imported_prefix)][2], "seed": schedule[len(imported_prefix)][3]}:
                raise RuntimeError("validated recovery admission does not identify the exact next schedule key")
        if manifest.get("recovery_import") and imported is None:
            raise RuntimeError("recovery import marker is absent")
        prefix_count, next_key = _reconcile_execution_prefix(manifest, run, admission)
        if prefix_count == 1:
            expected_next = manifest.get("recovery_next_key")
            observed_next = None if next_key is None else {"arm": next_key[0], "task_id": next_key[1],
                                                           "trial_id": next_key[2], "seed": next_key[3]}
            if observed_next != expected_next:
                raise RuntimeError("recovery prefix does not admit the exact frozen next trajectory")
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
        checkpoint_prefix = _checkpoint_prefix_from_manifest(manifest, admission)
        checkpoint = ReasoningBankDynamicCheckpoints(root=run / "reasoningbank-dynamic-checkpoints",
                                                     expected_trajectory_ids=[f"evaluation:reasoningbank_dynamic:{task}:trial={trial}:seed={seed}"
                                                                              for task in manifest["evaluation"]["task_ids"]
                                                                              for trial, seed in enumerate(SEEDS, 1)],
                                                     ledger_path=run / "ledger.jsonl", prefix=checkpoint_prefix)
        prefix = checkpoint.reconcile(initial)
        bank = prefix.restored_bank
        providers = ReasoningBankProviders(api_key=key, ledger=ledger, progress=run / "progress.jsonl")
        lifecycle = ReasoningBankLifecycle(bank=bank, embedder=SharedAzureOpenRouterEmbedder(api_key=key, ledger=ledger, progress=run / "progress.jsonl"),
                                           judge=providers.judge, extractor=providers.extract)
        runtime = ReasoningBankDynamicRuntime(lifecycle=lifecycle, initial_bank=initial, checkpoints=checkpoint,
                                              run_root=run, registry_sha256=manifest["registry_sha256"],
                                              manifest_sha256=file_sha(run / "manifest.json"),
                                              runtime_identity_sha256=runtime_identity_sha256,
                                              runtime_identity_record_sha256=runtime_identity_record_sha256,
                                              embedding_identity=manifest["embedding"])
        evidence = {"registry_path": str(REGISTRY.resolve()), "registry_sha256": manifest["registry_sha256"],
                    "runtime_identity_sha256": runtime_identity_sha256,
                    "runtime_identity_record_sha256": runtime_identity_record_sha256}
        _status(run, "running", manifest_sha256=file_sha(run / "manifest.json"), completed_update_prefix=len(prefix.completed))
        for task in manifest["evaluation"]["task_ids"]:
            for arm in ARMS:
                for trial, seed in enumerate(SEEDS, 1):
                    target = run / "artifacts" / task / arm / f"trial-{trial}.json"
                    key_identity = (arm, task, trial, seed)
                    if key_identity == imported or key_identity in imported_prefix:
                        continue
                    if target.is_file():
                        row = json.loads(target.read_text(encoding="utf-8"))
                        validate_evidence(row, run_root=run, expected_registry_sha256=manifest["registry_sha256"])
                        if arm == "reasoningbank_dynamic" and admission is not None:
                            expected = admission["next_key"]
                            if key_identity == (str(expected["arm"]), str(expected["task_id"]), int(expected["trial_id"]), int(expected["seed"])):
                                runtime._admission_receipt(retrieval_path, admission, require_prompt_binding=True)
                        continue
                    _storage_guard("task dispatch")
                    retrieval_path = run / "retrievals" / task / f"{arm}-trial-{trial}.json"
                    kwargs: dict[str, Any] = {}
                    if arm == "reasoningbank_dynamic":
                        # This immutable identity is deliberately built once
                        # from frozen run files and passed unchanged to the
                        # retrieval writer and post-prompt pre-dispatch seal.
                        # Neither boundary may augment a narrower identity.
                        identity = _retrieval_identity(manifest, run, arm, task, trial, seed)
                        admitted_pending = admission is not None and key_identity == (str(admission["next_key"]["arm"]), str(admission["next_key"]["task_id"]), int(admission["next_key"]["trial_id"]), int(admission["next_key"]["seed"]))
                        if admitted_pending:
                            kwargs["memory_for_instruction"] = runtime.admission_precomputed_retrieval_callback(retrieval_path, admission=admission, identity=identity)
                            kwargs["pre_dispatch_binding"] = runtime.admission_prompt_binding_callback(retrieval_path, admission=admission, identity=identity)
                        else:
                            kwargs["memory_for_instruction"] = runtime.retrieval_callback(retrieval_path, identity=identity)
                            kwargs["pre_dispatch_binding"] = runtime.prompt_binding_callback(retrieval_path, identity=identity)
                        kwargs["post_score_update"] = runtime.strict_post_score_callback(
                            retrieval_path, admission=admission if admitted_pending else None)
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
