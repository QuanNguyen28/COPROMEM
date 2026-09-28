#!/usr/bin/env python3
"""Freeze v5.3's exposed-A / previously-withheld-B replay continuation."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

from copromem.benchmarks.appworld.adapter import CoProMemAppWorldAdapter
from copromem.experiments.reme_copromem.public_tool_schema_registry import canonical_digest, public_tool_path_audit, tool_operation_index, verify_public_tool_schema_registry
from copromem.experiments.reme_copromem.runner import AppendOnlyLedger, construct_copromem, raw_acquisition_trajectories, v5_budget_bound, write_json
from copromem.learning import ActionObservation
from scripts.reme_copromem.prepare_execution_evidence_v1 import EVIDENCE_RELATIVE_PATH
from scripts.reme_copromem.prepare_tool_schema_v53 import (
    ACQUISITION_RELATIVE_PATH, FUNCTION_ROOT, OPENAPI_ROOT, REGISTRY_RELATIVE_PATH,
    ROOT, historical_settled_usd, sha, source_commit,
)


IMMUTABLE_011 = ROOT / "artifacts/research/official_reme_copromem_pilot/v5_2_engineering_011_observable_path"


def load_011() -> tuple[dict[str, Any], str, dict[str, Any]]:
    manifest_path, hash_path = IMMUTABLE_011 / "manifest.json", IMMUTABLE_011 / "manifest.sha256"
    expected = hash_path.read_text(encoding="utf-8").strip()
    if sha(manifest_path) != expected:
        raise RuntimeError("immutable 011 manifest hash mismatch")
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    evaluation = value.get("evaluation", {})
    ids = evaluation.get("task_ids", [])
    if value.get("protocol") != "v5_2_engineering_011_observable_path" or len(ids) != 2:
        raise RuntimeError("immutable 011 allocation is malformed")
    a, b = ids
    if evaluation.get("a_task_id") != a or evaluation.get("b_task_id") != b:
        raise RuntimeError("immutable 011 A/B allocation mismatch")
    descriptors = evaluation.get("descriptors", {})
    if descriptors.get(a) != descriptors.get(b) or not isinstance(descriptors.get(a), list):
        raise RuntimeError("immutable 011 does not contain one shared frozen descriptor")
    return value, expected, {"a_task_id": a, "b_task_id": b, "descriptor": descriptors[a],
                              "seeds": evaluation.get("seeds"), "trial_ids": evaluation.get("trial_ids")}


def custody_audit(pair: dict[str, Any], manifest_hash: str) -> dict[str, Any]:
    a, b = pair["a_task_id"], pair["b_task_id"]
    files = [path for path in IMMUTABLE_011.rglob("*") if path.is_file()]
    a_actions = list((IMMUTABLE_011 / "evaluation").glob(f"*/{a}/trial-*.json"))
    b_actions = list((IMMUTABLE_011 / "evaluation").glob(f"*/{b}/trial-*.json"))
    b_scorer = [path for path in b_actions if path.is_file()]
    b_journals = list((IMMUTABLE_011 / "journals").glob(f"*{b}*"))
    b_retrieval = list((IMMUTABLE_011 / "retrieval").glob(f"*/{b}/trial-*.json"))
    ledger_text = (IMMUTABLE_011 / "ledger.jsonl").read_text(encoding="utf-8")
    b_ledger_mentions = sum(1 for line in ledger_text.splitlines() if b in line)
    b_other = [path for path in files if b in path.name and path not in b_journals and path not in b_actions and path not in b_retrieval]
    audit = {
        "audit_version": "v5_3_013R_custody_v1", "immutable_011_manifest_sha256": manifest_hash,
        "a": {"task_id": a, "textual_public_id_mention": True, "public_descriptor_exposure": True,
              "payload_opening": True, "execution_artifact_count": len(a_actions), "scoring_artifact_count": len(a_actions),
              "classification": "exposed_replay"},
        "b": {"task_id": b, "textual_public_id_mention": True, "public_descriptor_exposure": True,
              "payload_opening": False, "execution_artifact_count": len(b_actions), "scoring_artifact_count": len(b_scorer),
              "journal_count": len(b_journals), "retrieval_count": len(b_retrieval), "executor_settlement_mentions": b_ledger_mentions,
              "nonallocation_file_mentions": len(b_other), "outcome_known": False, "classification": "previously_withheld_continuation"},
        "pair_selected_before_b_result": True,
    }
    audit["passed"] = bool(len(a_actions) > 0 and not b_actions and not b_scorer and not b_journals and not b_retrieval and not b_ledger_mentions)
    return audit


def _registry_path_audit(registry: dict[str, Any], descriptor: list[dict[str, Any]]) -> dict[str, Any]:
    index = tool_operation_index(registry); signatures = []
    for row in descriptor:
        meta = index.get(row["operation"])
        if meta is None:
            raise RuntimeError("011 descriptor operation is absent from v5.3 public registry")
        signatures.append({"application": meta["app"], "callable_name": meta["function_name"], "operation": row["operation"],
                           "public_required": meta["required_parameters"], "public_optional_present": [],
                           "runtime_context_present": [], "output_slots": meta["output_slots"]})
    audit = public_tool_path_audit(registry, signatures)
    if not audit.get("passed"):
        raise RuntimeError("immutable 011 descriptor has no complete v5.3 public callable path")
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--run", type=pathlib.Path, required=True); args = parser.parse_args()
    if args.run.exists() and any(args.run.iterdir()):
        raise RuntimeError("013R run directory already exists")
    original, original_hash, pair = load_011()
    audit = custody_audit(pair, original_hash)
    if not audit["passed"]:
        raise RuntimeError("011 custody audit proves B was not withheld")
    registry_path = ROOT / REGISTRY_RELATIVE_PATH
    registry = json.loads(registry_path.read_text(encoding="utf-8")); verify_public_tool_schema_registry(registry)
    path_audit = _registry_path_audit(registry, pair["descriptor"])
    acquisition_path = ROOT / ACQUISITION_RELATIVE_PATH
    acquisition = json.loads(acquisition_path.read_text(encoding="utf-8")); acquisition = acquisition.get("trajectories", acquisition)
    ids = [pair["a_task_id"], pair["b_task_id"]]
    if len(acquisition) != 32 or set(ids) & {str(row["task_id"]) for row in acquisition}:
        raise RuntimeError("frozen acquisition export is not disjoint from 011 pair")
    args.run.mkdir(parents=True, exist_ok=False)
    limits = {"executor": 240, "reme_lifecycle": 0, "reme_embedding": 0, "copromem_decomposition": 0}
    ledger = AppendOnlyLedger(args.run / "ledger.jsonl", 100.0, limits)
    state, _ = construct_copromem(run=args.run, progress=args.run / "progress.jsonl", ledger=ledger,
                                  api_key="", raw=raw_acquisition_trajectories(acquisition), call_cap=0)
    bank = CoProMemAppWorldAdapter(api_key=""); bank.clone_from_state(state)
    events = tuple(ActionObservation(**item) for item in pair["descriptor"])
    initial = {task_id: bank.module.learning.retrieve("appworld", events).compatibility for task_id in ids}
    if set(initial.values()) != {"unknown"}:
        raise RuntimeError("011 pair is not initially unknown under the fresh v5.3 warm-start state")
    budget = v5_budget_bound(call_limits=limits, historical_usd=historical_settled_usd())
    budget.update({"call_limits": limits, "hard_cap_usd": 100.0, "fits_hard_cap": budget["all_in_usd"] <= 100.0,
                   "ledger_dispatch_cap_usd": budget["dispatchable_usd"]})
    evidence_path = ROOT / EVIDENCE_RELATIVE_PATH
    manifest = {"protocol": "v5_3_engineering_013R_replay_continuation", "purpose": "engineering_only",
        "engineering_only_exposed": True, "claims_prohibited": ["efficacy", "superiority", "transfer_rate", "generalization"],
        "method_amendment": "public_execution_evidence_v1", "git_commit": source_commit(),
        "immutable_011": {"manifest_sha256": original_hash, "source_commit": original["git_commit"], "pair_relationship": "exact frozen pair; fresh replay A and first-use B"},
        "custody": {"a_custody": "exposed_replay", "b_custody": "previously_withheld_continuation"},
        "acquisition": {"source_export": str(acquisition_path.resolve()), "export_sha256": sha(acquisition_path), "expected_trajectories": 32, "fresh_state_required": True},
        "arms": ["no_memory", "copromem_dynamic"],
        "execution": {"max_actions": 30, "temperature": 0.7, "top_p": 1.0, "c_floor_gib": 10.0,
                      "model": "deepseek/deepseek-v4.1-flash", "provider": "deepseek", "fallbacks": False,
                      "reasoning_effort": "none", "stream": False, "completion_token_ceiling": 2048},
        "evaluation": {"split": "dev", "task_ids": ids, "a_task_id": ids[0], "b_task_id": ids[1], "trial_ids": pair["trial_ids"], "seeds": pair["seeds"], "expected_trajectories": 8,
                       "descriptors": {task_id: pair["descriptor"] for task_id in ids}, "descriptor_sha256": canonical_digest(pair["descriptor"]), "initial_compatibility": initial,
                       "public_registry_relative_path": REGISTRY_RELATIVE_PATH, "public_registry_file_sha256": sha(registry_path), "public_registry_sha256": registry["registry_sha256"],
                       "runtime_public_schema": {"openapi_root": OPENAPI_ROOT, "function_calling_root": FUNCTION_ROOT},
                       "execution_evidence": {"version": "public-execution-evidence-v1", "registry_relative_path": REGISTRY_RELATIVE_PATH, "registry_sha256": registry["registry_sha256"],
                                              "implementation_relative_path": EVIDENCE_RELATIVE_PATH, "implementation_sha256": sha(evidence_path)}},
        "budget": budget, "task_boundary_policy": "observable_tool_schema_execution_evidence_v1"}
    write_json(args.run / "custody-audit.json", audit); write_json(args.run / "registry-path-audit.json", path_audit); write_json(args.run / "template.json", manifest)
    print(json.dumps({"a": ids[0], "b": ids[1], "immutable_011": original_hash, "all_in_usd": budget["all_in_usd"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
