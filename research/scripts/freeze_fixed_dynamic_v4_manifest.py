#!/usr/bin/env python3
"""Freeze v4 evaluation allocation from ID-only inventory, without task payload access."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v4"
INVENTORY = ROOT / "research/test_normal_ids.txt"
TASK_RE = re.compile(r"\b[0-9a-f]{7}_[0-9]+\b")
SALT = "fixed_dynamic_v4_test_normal_id_only_20260927"
ARMS = [
    "no_memory",
    "official_upstream_reme_fixed",
    "official_upstream_reme_dynamic",
    "copromem_fixed",
    "copromem_dynamic",
]
SEEDS = [8101, 8102, 8103, 8104]
INPUT_PRICE = 0.30 / 1_000_000
OUTPUT_PRICE = 1.20 / 1_000_000
INPUT_TOKENS = 32_768
OUTPUT_TOKENS = 2_048
EMBEDDING_PRICE = 0.0000001
HARD_CAP = 160.0


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha(value: object) -> str:
    return sha_bytes(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                separators=(",", ":")).encode("utf-8"))


def historical_exposure() -> tuple[set[str], dict[str, int]]:
    """Extract the actual v3 execution boundary, never availability inventories.

    The v4 custody rule is fresh relative to v3-opened evaluation IDs/families.
    Broad historical exposure-audit files include prospective availability lists,
    and therefore are not evidence that a task was executed.
    """
    ids: set[str] = set()
    files = 0
    for base in (ROOT / "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v3",):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            name = path.name.lower()
            if "inventory" in name:
                continue
            if path.suffix.lower() not in {".json", ".jsonl", ".md", ".txt", ".py"}:
                continue
            try:
                ids.update(TASK_RE.findall(path.read_text(encoding="utf-8", errors="ignore")))
                files += 1
            except OSError:
                continue
    return ids, {"files_scanned": files, "id_count": len(ids)}


def ledger_exposure() -> tuple[float, int]:
    """Carry settled plus unresolved reservations in the fixed-dynamic lineage.

    Reserve/settle pairs use the same request ID and must not be double counted.
    The medium pilot is a separate study with its own USD 140 authority and is
    deliberately not included in this v4 successor ledger.
    """
    total = 0.0
    records = 0
    # v3 itself carries v1/v2 exposure as an immutable `historical_carry_forward`
    # reservation.  Replaying all three ledgers would double-count it.
    path = ROOT / "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v3/ledger.jsonl"
    if not path.is_file():
        raise RuntimeError("v3 append-only ledger required for v4 carry-forward is missing")
    try:
        pending: dict[str, float] = {}
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line:
                    continue
                row = json.loads(line)
                records += 1
                request_id = str(row.get("request_id") or row.get("id") or f"row-{records}")
                usd = float(row.get("usd", row.get("reserved_usd", row.get("charged_usd", 0.0))) or 0.0)
                event = row.get("state", row.get("event"))
                if event == "reserve":
                    pending[request_id] = max(0.0, usd)
                elif event == "settle":
                    # A settled request consumes its actual settled amount.
                    pending.pop(request_id, None)
                    total += max(0.0, usd)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("cannot reconcile immutable v3 ledger") from exc
    total += sum(pending.values())
    return total, records


def budget(carried_usd: float) -> dict:
    # 16 x 4 x 5 x 30 executor turns; lifecycle/decomposition maxima are
    # preserved from the approved v3 accounting, with no early-stop discount.
    chat = INPUT_TOKENS * INPUT_PRICE + OUTPUT_TOKENS * OUTPUT_PRICE
    executor_calls = 16 * 4 * 5 * 30
    copromem_decomposition_calls = 320
    reme_lifecycle_calls = 96
    embedding_calls = 216
    executor = executor_calls * chat
    copromem = copromem_decomposition_calls * chat
    reme = reme_lifecycle_calls * chat
    embeddings = embedding_calls * 8192 * EMBEDDING_PRICE
    dispatchable = executor + copromem + reme + embeddings
    contingency = dispatchable * 0.15
    all_in = carried_usd + dispatchable + contingency
    return {
        "historical_charged_or_reserved_usd": carried_usd,
        "executor_calls": executor_calls,
        "executor_usd": executor,
        "copromem_decomposition_calls": copromem_decomposition_calls,
        "copromem_decomposition_usd": copromem,
        "reme_lifecycle_calls": reme_lifecycle_calls,
        "reme_lifecycle_usd": reme,
        "embedding_calls": embedding_calls,
        "embedding_usd": embeddings,
        "dispatchable_usd": dispatchable,
        "non_dispatchable_contingency_fraction": 0.15,
        "non_dispatchable_contingency_usd": contingency,
        "all_in_usd": all_in,
        "hard_cap_usd": HARD_CAP,
        # The contingency is intentionally non-dispatchable; runtime ledger
        # reservations cannot consume it.
        "ledger_dispatch_cap_usd": HARD_CAP - contingency,
        "fits_hard_cap": all_in <= HARD_CAP,
    }


def main() -> None:
    gate_path = RUN / "copromem/acquisition-retrieval-gate.json"
    state_path = RUN / "copromem/initial-state.json"
    if not gate_path.is_file() or not state_path.is_file():
        raise RuntimeError("passed v4 acquisition retrieval gate evidence is missing")
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    expected_bank = "b706c873697b0d226271dab63f843a8afcb343c031f9a3dad3e4f9c22dd98528"
    if not gate.get("passed") or gate.get("bank_sha256") != expected_bank:
        raise RuntimeError("v4 gate is not the passed frozen bank")
    if canonical_sha(json.loads(state_path.read_text(encoding="utf-8"))) != expected_bank:
        raise RuntimeError("v4 initial state hash does not match frozen bank")

    inventory = [line.strip() for line in INVENTORY.read_text(encoding="utf-8").splitlines()
                 if TASK_RE.fullmatch(line.strip())]
    if len(set(inventory)) != len(inventory):
        raise RuntimeError("ID-only inventory contains duplicate IDs")
    exposed, exposure_meta = historical_exposure()
    # Exact exposure is mandatory.  Prefer family exclusion, but the approved
    # protocol permits an exact-ID-only custody claim if fewer than 16 fresh
    # families remain.  That fallback is explicit in the manifest.
    exposed_families = {item.split("_", 1)[0] for item in exposed}
    eligible = [item for item in inventory if item not in exposed and item.split("_", 1)[0] not in exposed_families]
    by_family: dict[str, list[str]] = {}
    for item in eligible:
        by_family.setdefault(item.split("_", 1)[0], []).append(item)
    candidates = []
    for family, entries in by_family.items():
        candidates.append(min(entries, key=lambda x: sha_bytes(f"{SALT}|{x}".encode("utf-8"))))
    selected = sorted(candidates, key=lambda x: sha_bytes(f"{SALT}|{x}".encode("utf-8")))[:16]
    family_holdout = len(selected) == 16
    if not family_holdout:
        # Same ID-only inventory, same deterministic salt; no payload access.
        exact_only = [item for item in inventory if item not in exposed]
        selected = sorted(exact_only, key=lambda x: sha_bytes(f"{SALT}|exact|{x}".encode("utf-8")))[:16]
    if len(selected) != 16:
        raise RuntimeError("custody failure: fewer than 16 fresh exact-ID evaluation candidates")
    carried, ledger_records = ledger_exposure()
    costs = budget(carried)
    if not costs["fits_hard_cap"]:
        raise RuntimeError(f"budget failure: requires USD {costs['all_in_usd']:.8f}, cap is USD {HARD_CAP:.2f}")
    manifest = {
        "protocol": "corrected_fixed_dynamic_v4",
        "status": "frozen_pre_payload",
        "git_commit": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "selection": {"source": "test_normal ID-only inventory", "salt": SALT,
                      "exact_id_holdout_only": True, "family_holdout": family_holdout,
                      "historical_exposure_ids_sha256": canonical_sha(sorted(exposed)), **exposure_meta},
        "acquisition": {"source": "32 immutable preserved trajectories", "provider_calls": 0,
                        "copromem_bank_sha256": expected_bank,
                        "retrieval_gate_path": gate_path.relative_to(ROOT).as_posix(),
                        "retrieval_gate_sha256": sha_bytes(gate_path.read_bytes())},
        "evaluation": {"task_ids": selected, "trial_ids": [1, 2, 3, 4], "seeds": SEEDS,
                       "expected_trajectories": 16 * 4 * len(ARMS)},
        "arms": ARMS,
        "controls": {"temperature": 0.7, "top_p": 1.0, "max_actions": 30,
                     "max_input_tokens": 32768, "max_completion_tokens": 2048,
                     "official_scorer": True, "native_appworld": True},
        "route": {"endpoint": "https://openrouter.ai/api/v1/chat/completions", "model": "deepseek/deepseek-v4.1-flash",
                  "provider_only": ["deepseek"], "allow_fallbacks": False, "reasoning_effort": "none", "stream": False},
        "embedding": {"model": "openai/text-embedding-3-small", "provider_only": ["azure"], "dimensions": 1024},
        "restart_idempotency": {"require_exact_checkpoint_hashes": True, "no_replay_settled_calls": True,
                                "no_lifecycle_or_retrieval_gate_calls_on_resume": True},
        "budget": costs,
        "ledger_audit": {"records_scanned": ledger_records},
        "limitations": ["exploratory faithful adaptation; not an exact ReMe reproduction",
                        "exact-ID holdout only; no task-family or benchmark-wide generalization claim"],
    }
    raw = json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "manifest.json").write_bytes(raw)
    (RUN / "manifest.sha256").write_text(sha_bytes(raw) + "\n", encoding="utf-8")
    (RUN / "budget-preflight.json").write_text(json.dumps(costs, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (RUN / "evaluation-exposure-audit.json").write_text(json.dumps({"exposed_count": len(exposed), **exposure_meta,
        "selected_count": len(selected), "selected_family_count": len({x.split('_', 1)[0] for x in selected}),
        "inventory_count": len(inventory)}, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest_sha256": sha_bytes(raw), "selected": selected,
                      "budget_all_in_usd": costs["all_in_usd"], "historical_usd": carried}, sort_keys=True))


if __name__ == "__main__":
    main()
