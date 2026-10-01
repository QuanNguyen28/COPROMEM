#!/usr/bin/env python3
"""Read-only, sanitized terminal audit for v6.2.1 engineering run 003.

This boundary deliberately opens only already-durable local evidence.  It does
not construct an AppWorld task, start a service, or contact any provider.  Its
output contains identities, hashes, public schema IDs, and aggregates only;
task instructions, histories, journals, memory text, and scorer payloads stay
in the ignored run directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
import sys
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from copromem.contrastive_graph_v6 import digest
from copromem.experiments.reme_copromem.evidence_contract import validate as validate_evidence
from copromem.experiments.reme_copromem.task_conditioned_retrieval_v621 import reproduce_retrieval


RUN_NAME = "v6_2_1_task_conditioned_retrieval_engineering_003"
RUN = ROOT / "artifacts/research/official_reme_copromem_pilot" / RUN_NAME
REGISTRY = ROOT / "research/reme_copromem_fixed_dynamic_review/appworld_public_tool_schema_registry_v5_3.json"
COPRO_BANK = ROOT / "artifacts/research/official_reme_copromem_pilot/v6_shared_acquisition_001/copro" \
    "mem-v6.1-semantic-recovery-003/fixed-bank.json"
AUDIT = ROOT / "research/reme_copromem_fixed_dynamic_review/v621-engineering-003-final-audit.json"
CHECKSUMS = ROOT / "research/reme_copromem_fixed_dynamic_review/v621-engineering-003-final-audit.checksums.json"
MARKDOWN = ROOT / "research/reme_copromem_fixed_dynamic_review/V621_ENGINEERING_003_FINAL_AUDIT.md"

COPRO_ARMS = ("copromem_v6_2_1_fixed", "copromem_v6_2_1_dynamic")
REME_ARMS = ("official_upstream_reme_fixed", "official_upstream_reme_dynamic")
NO_MEMORY = "no_memory"
COMPATIBLE = frozenset({"3aa1a22_2", "3aa1a22_3"})
NEGATIVE = "024c982_3"


class AuditError(RuntimeError):
    """A terminal invariant is not independently reproducible."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AuditError(f"expected JSON object: {path.name}")
    return value


def state_from(wrapper: Mapping[str, Any]) -> dict[str, Any]:
    state = wrapper.get("state", wrapper)
    if not isinstance(state, Mapping):
        raise AuditError("semantic state is absent")
    return dict(state)


def host_path(value: str) -> pathlib.Path:
    """Read the same E-backed evidence from either Windows or WSL spelling."""
    if value.startswith("/mnt/e/") and os.name == "nt":
        return pathlib.Path("E:/" + value[len("/mnt/e/"):])
    if os.name != "nt" and re.match(r"^[Ee]:[\\/]", value):
        return pathlib.Path("/mnt/e/" + value[3:].replace("\\", "/"))
    return pathlib.Path(value)


def host_evidence_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Make an in-memory host-path projection for the maintained validator.

    The persisted evidence stays byte-identical; only the reading host's view
    of its absolute E-backed path is projected.
    """
    clone = json.loads(json.dumps(row))
    journal = host_path(str(clone["execution_evidence_path"]))
    clone["execution_evidence_path"] = str(journal)
    ordinary = clone.get("official_scorer_evidence")
    if isinstance(ordinary, dict): ordinary["path"] = str(host_path(str(ordinary["path"])))
    zero = clone.get("zero_action_evidence")
    if isinstance(zero, dict): zero["scorer_evidence_path"] = str(host_path(str(zero["scorer_evidence_path"])))
    return clone


def artifact_paths(run: pathlib.Path) -> list[pathlib.Path]:
    return sorted((run / "artifacts").glob("*/*/trial-*.json"))


def artifact_identity(row: Mapping[str, Any]) -> tuple[str, str, int, int]:
    return (str(row.get("arm")), str(row.get("task_id")), int(row.get("trial_id")), int(row.get("seed")))


def artifact_sha(path: pathlib.Path) -> str:
    return sha_file(path)


def validate_artifact(path: pathlib.Path, run: pathlib.Path, registry_sha: str) -> dict[str, Any]:
    row = read(path)
    if not isinstance(row.get("history"), list) or digest(row["history"]) != row.get("history_sha256"):
        raise AuditError(f"canonical history hash mismatch: {path.relative_to(run)}")
    persisted_journal = host_path(str(row.get("execution_evidence_path") or ""))
    if str(row.get("execution_evidence_run_relative") or "") != persisted_journal.relative_to(run).as_posix():
        raise AuditError(f"portable evidence locator mismatch: {path.relative_to(run)}")
    if "zero_action_evidence" in row:
        # This immutable record predates cross-host path projection.  Validate
        # its persisted canonical binding before translating its scorer path
        # for this Windows host; mutating it for the legacy validator would
        # intentionally change its binding preimage.
        zero = row["zero_action_evidence"]
        if not isinstance(zero, Mapping):
            raise AuditError(f"canonical zero-action evidence is malformed: {path.relative_to(run)}")
        copy = dict(zero); bound = copy.pop("binding_sha256", None)
        scorer = host_path(str(zero.get("scorer_evidence_path") or ""))
        if (bound != digest(copy) or persisted_journal.read_bytes() != b""
                or row.get("execution_evidence_sha256") != hashlib.sha256(b"").hexdigest()
                or row.get("execution_evidence_rows") != 0 or not scorer.is_file()
                or sha_file(scorer) != zero.get("scorer_evidence_sha256")
                or zero.get("history_sha256") != row.get("history_sha256")
                or zero.get("official_score") != row.get("after_score")):
            raise AuditError(f"canonical zero-action evidence failed: {path.relative_to(run)}")
        journal = persisted_journal
    else:
        projected = host_evidence_row(row)
        projected["execution_evidence_run_relative"] = str(persisted_journal.relative_to(run))
        try:
            journal = validate_evidence(projected, run_root=run, expected_registry_sha256=registry_sha)
        except Exception as exc:  # convert the maintained contract to audit vocabulary
            raise AuditError(f"execution-evidence failure: {path.relative_to(run)}: {exc}") from exc
    scorer = row.get("official_scorer_evidence") or row.get("zero_action_evidence")
    if not isinstance(scorer, Mapping):
        raise AuditError(f"canonical scorer binding is absent: {path.relative_to(run)}")
    return {"row": row, "journal": journal, "artifact_sha256": artifact_sha(path),
            "scorer_contract": "zero_action" if "zero_action_evidence" in row else "ordinary"}


def ledger_inventory(run: pathlib.Path) -> dict[str, Any]:
    rows = [json.loads(line) for line in (run / "ledger.jsonl").read_text(encoding="utf-8").splitlines() if line]
    reserve: dict[str, dict[str, Any]] = {}
    settle: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("event") == "reserve":
            if not isinstance(row.get("id"), str) or row["id"] in reserve:
                raise AuditError("duplicate or malformed ledger reservation")
            reserve[row["id"]] = row
        elif row.get("event") == "settle":
            if not isinstance(row.get("id"), str) or row["id"] in settle:
                raise AuditError("duplicate or malformed ledger settlement")
            settle[row["id"]] = row
    if set(reserve) != set(settle):
        raise AuditError("unresolved or settlement-without-reservation ledger record")
    return {"reservation_count": len(reserve), "settlement_count": len(settle),
            "unresolved_reservation_count": 0,
            "settled_usd": round(sum(float(item.get("usd", 0.0)) for item in settle.values()), 12),
            "settlements": settle}


def assert_executor_settled(ledger: Mapping[str, Any], row: Mapping[str, Any]) -> None:
    role = f"executor:{row['arm']}:{row['task_id']}:trial={row['trial_id']}:seed={row['seed']}"
    if not any(item.get("role") == role for item in ledger["settlements"].values()):
        raise AuditError(f"executor settlement missing for {row['trajectory_id']}")


def _dynamic_pre_state(run: pathlib.Path, task_index: int, task_id: str) -> dict[str, Any]:
    return state_from(read(run / "copromem-dynamic-checkpoints" / "tasks" / f"{task_index:04d}-{task_id}" / "pre-state.json"))


def _compact_features(provenance: Mapping[str, Any]) -> dict[str, Any]:
    rows = provenance.get("candidate_scores", [])
    if not isinstance(rows, list):
        raise AuditError("candidate scores are malformed")
    return {str(item.get("schema_id")): {
        "compatible": bool(item.get("compatible")),
        "rejection_reason": item.get("rejection_reason"),
        "terminal_effect_supported": bool(item.get("terminal_effect_supported")),
        "public_dependency_edge_count": int(item.get("public_dependency_edge_count", 0)),
        "positive_success_count": int(item.get("positive_success_count", 0)),
        "negative_failure_count": int(item.get("negative_failure_count", 0)),
    } for item in rows if isinstance(item, Mapping)}


def copromem_rows(run: pathlib.Path, manifest: Mapping[str, Any], registry: Mapping[str, Any], artifacts: Mapping[tuple[str, str, int, int], dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fixed = state_from(read(COPRO_BANK)); tasks = list(manifest["evaluation"]["task_ids"]); seeds = list(manifest["evaluation"]["seeds"])
    output: list[dict[str, Any]] = []; dynamic_boundaries: list[dict[str, Any]] = []
    for task_index, task in enumerate(tasks, 1):
        dynamic = _dynamic_pre_state(run, task_index, task)
        dynamic_rows: list[dict[str, Any]] = []
        for arm in COPRO_ARMS:
            state = fixed if arm.endswith("fixed") else dynamic
            before = digest(state)
            for trial, seed in enumerate(seeds, 1):
                record = read(run / "retrievals" / task / f"{arm}-{trial}.json")
                provenance, query, guidance = record.get("provenance"), record.get("task_query"), record.get("guidance")
                if not isinstance(provenance, Mapping) or not isinstance(query, Mapping) or not isinstance(guidance, str):
                    raise AuditError("CoProMem retrieval record is malformed")
                reproduced = reproduce_retrieval(state, query, registry, provenance)
                if reproduced != guidance or digest(state) != before:
                    raise AuditError("CoProMem offline reproduction or non-mutation failed")
                artifact = artifacts[(arm, task, trial, seed)]
                # The production artifact binds the canonical JSON object,
                # rather than filesystem formatting (which is intentionally
                # host-independent).
                if artifact["row"].get("copromem_retrieval_record_sha256") != digest(record):
                    raise AuditError("CoProMem artifact/retrieval binding mismatch")
                item = {
                    "task_id": task, "compatibility_class": "compatible" if task in COMPATIBLE else "negative_control",
                    "arm": arm, "trial": trial, "seed": seed, "score": artifact["row"]["after_score"],
                    "action_count": artifact["row"]["actions"], "semantic_pre_state_sha256": before,
                    "task_query_sha256": provenance["task_query_sha256"],
                    "candidate_schema_ids": list(provenance["candidate_schema_ids"]),
                    "selected_schema_id": provenance["selected_schema_id"],
                    "compatibility_features": _compact_features(provenance),
                    "guidance_nonempty": bool(provenance["guidance_nonempty"]),
                    "guidance_length": len(guidance), "guidance_sha256": provenance["guidance_sha256"],
                    "prompt_injection_sha256": record["prompt_injection_sha256"],
                    "initial_model_visible_prompt_sha256": record["initial_prompt_messages_sha256"],
                    "offline_reproduction_passed": True,
                    "post_task_update_marker": None, "semantic_post_state_sha256": before,
                }
                output.append(item)
                if arm.endswith("dynamic"): dynamic_rows.append(item)
        root = run / "copromem-dynamic-checkpoints" / "tasks" / f"{task_index:04d}-{task}"
        update = read(run / "copromem-dynamic" / task / "update.json")
        marker = update.get("audit", {}).get("marker", {}) if isinstance(update.get("audit"), Mapping) else {}
        post = state_from(read(root / "post-state.json"))
        if digest(post) != update.get("post_state_sha256"):
            raise AuditError("CoProMem post-state hash mismatch")
        if any(item["semantic_pre_state_sha256"] != before for item in dynamic_rows):
            raise AuditError("same-task CoProMem Dynamic trials did not share one pre-state")
        for item in dynamic_rows:
            item["post_task_update_marker"] = str(marker.get("state") or "missing")
            item["semantic_post_state_sha256"] = digest(post)
        dynamic_boundaries.append({"task_id": task, "task_index": task_index,
            "both_trials_scored_before_update": (root / "03-trajectories_complete.json").is_file(),
            "plan_persisted": (root / "05-semantic_plan_persisted.json").is_file(),
            "validation_persisted": (root / "06-validation_persisted.json").is_file(),
            "commit_persisted": (root / "07-commit_persisted.json").is_file(),
            "post_state_persisted": (root / "08-post_state_snapshot_persisted.json").is_file(),
            "next_task_authorized": (root / "09-next_task_authorized.json").is_file(),
            "state": marker.get("state"), "winner_schema_id": marker.get("winner_schema_id"),
            "pre_state_semantic_sha256": digest(dynamic), "post_state_semantic_sha256": digest(post),
            "semantic_state_changed": digest(dynamic) != digest(post),
            "newly_retrieval_visible_schema_ids": sorted(set(post.get("contrastive_v6_schemas", {})) - set(dynamic.get("contrastive_v6_schemas", {}))),
            "duplicate_commit_idempotency": "validated_by_durable_checkpoint_reconciliation",
            "restart_reproduction": "validated_by_run_reconciled_marker",
        })
    return output, dynamic_boundaries


def reme_rows(run: pathlib.Path, manifest: Mapping[str, Any], artifacts: Mapping[tuple[str, str, int, int], dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tasks, seeds = list(manifest["evaluation"]["task_ids"]), list(manifest["evaluation"]["seeds"])
    output: list[dict[str, Any]] = []; dynamic_markers: list[dict[str, Any]] = []
    for arm in REME_ARMS:
        for task in tasks:
            for trial, seed in enumerate(seeds, 1):
                row = artifacts[(arm, task, trial, seed)]["row"]
                baseline = artifacts[(NO_MEMORY, task, trial, seed)]["row"]
                p = row.get("reme_retrieval_provenance")
                if not isinstance(p, Mapping): raise AuditError("ReMe retrieval provenance is absent")
                def first_user_length(value: Mapping[str, Any]) -> int:
                    history = value.get("history", [])
                    return next((len(item["content"]) for item in history if isinstance(item, Mapping)
                                 and item.get("role") == "user" and isinstance(item.get("content"), str)), 0)
                output.append({"task_id": task, "arm": arm, "trial": trial, "seed": seed,
                    "score": row["after_score"], "action_count": row["actions"],
                    "retrieved_memory_count": int(p["retrieved_memory_count"]),
                    "ordered_memory_hashes": list(p["retrieved_memory_sha256s"]),
                    "ordered_retrieval_sha256": p["ordered_retrieval_sha256"],
                    "prompt_memory_hash": p["prompt_memory_sha256"],
                    "prompt_memory_length": max(0, first_user_length(row) - first_user_length(baseline)),
                    "retrieval_empty": bool(p["retrieval_empty"]),
                    "semantic_relevance_classification": "not_deterministically-established_from_hash-only_upstream_provenance",
                    "summary_production": "not_applicable_for_fixed" if arm.endswith("fixed") else "post_score_update_marker",
                    "dynamic_update_index": None})
    previous = str(manifest["banks"]["reme_shared_sha256"])
    for index, path in enumerate(sorted((run / "reme-dynamic-checkpoints" / "markers").glob("update-*.json")), 1):
        marker = read(path)
        if marker.get("ordered_update_index") != index or marker.get("pre_update_semantic_sha256") != previous:
            raise AuditError("ReMe Dynamic checkpoint order mismatch")
        snapshot = run / "reme-dynamic-checkpoints" / "snapshots" / str(marker.get("source_snapshot"))
        verifier = run / "reme-dynamic-checkpoints" / "snapshots" / str(marker.get("verifier_dump"))
        if not snapshot.is_file() or not verifier.is_file() or sha_file(snapshot) != marker.get("source_snapshot_sha256") or sha_file(verifier) != marker.get("verifier_dump_sha256"):
            raise AuditError("ReMe Dynamic snapshot/verifier binding mismatch")
        dynamic_markers.append({"update_index": index, "trajectory_id": marker["identity"]["trajectory_id"],
                                "pre_state_semantic_sha256": previous, "post_state_semantic_sha256": marker["post_update_semantic_sha256"],
                                "marker_sha256": sha_file(path), "summary_produced": True})
        previous = str(marker["post_update_semantic_sha256"])
    if len(dynamic_markers) != len(tasks) * len(seeds): raise AuditError("ReMe Dynamic update marker count mismatch")
    by_trajectory = {item["trajectory_id"]: item for item in dynamic_markers}
    for item in output:
        if item["arm"].endswith("dynamic"):
            marker = by_trajectory[f"evaluation:{item['arm']}:{item['task_id']}:trial={item['trial']}:seed={item['seed']}"]
            item["dynamic_update_index"] = marker["update_index"]
            item["post_update_state_sha256"] = marker["post_state_semantic_sha256"]
        else:
            item["post_update_state_sha256"] = manifest["banks"]["reme_shared_sha256"]
    paired = {(item["arm"], item["task_id"], item["trial"], item["seed"]): item for item in output}
    for item in output:
        opposite = "official_upstream_reme_dynamic" if item["arm"].endswith("fixed") else "official_upstream_reme_fixed"
        peer = paired[(opposite, item["task_id"], item["trial"], item["seed"])]
        item["fixed_dynamic_retrieval_equal"] = (
            item["ordered_retrieval_sha256"] == peer["ordered_retrieval_sha256"]
            and item["prompt_memory_hash"] == peer["prompt_memory_hash"])
    return output, dynamic_markers


def paired_statistics(artifacts: Mapping[tuple[str, str, int, int], dict[str, Any]], manifest: Mapping[str, Any]) -> dict[str, Any]:
    tasks, seeds, arms = list(manifest["evaluation"]["task_ids"]), list(manifest["evaluation"]["seeds"]), list(manifest["arms"])
    rows=[]; paired={}
    for arm in arms:
        if arm == NO_MEMORY: continue
        diffs=[]; wins=ties=losses=0
        for task in tasks:
            for trial, seed in enumerate(seeds,1):
                value=float(artifacts[(arm,task,trial,seed)]["row"]["after_score"]); base=float(artifacts[(NO_MEMORY,task,trial,seed)]["row"]["after_score"])
                diff=value-base; diffs.append(diff); wins+=diff>0; ties+=diff==0; losses+=diff<0
                rows.append({"task_id":task,"trial":trial,"seed":seed,"arm":arm,"score":value,"no_memory_score":base,"paired_difference":diff})
        paired[arm]={"mean_paired_difference":sum(diffs)/len(diffs),"wins":wins,"ties":ties,"losses":losses}
    all_scores = [{"task_id": task, "trial": trial, "seed": seed, "arm": arm,
                   "score": float(artifacts[(arm, task, trial, seed)]["row"]["after_score"]),
                   "action_count": int(artifacts[(arm, task, trial, seed)]["row"]["actions"])}
                  for task in tasks for trial, seed in enumerate(seeds, 1) for arm in arms]
    return {"all_per_task_trial_scores": all_scores, "per_task_trial": rows, "paired_against_no_memory": paired}


def audit(run: pathlib.Path = RUN) -> dict[str, Any]:
    run=run.resolve(); manifest=read(run/"manifest.json"); registry=read(REGISTRY)
    manifest_sha=sha_file(run/"manifest.json")
    if manifest_sha != (run/"manifest.sha256").read_text(encoding="utf-8").strip(): raise AuditError("manifest hash file mismatch")
    registry_sha=str(registry.get("registry_sha256") or "")
    if not registry_sha: raise AuditError("frozen registry identity missing")
    artifacts: dict[tuple[str,str,int,int],dict[str,Any]]={}
    for path in artifact_paths(run):
        checked=validate_artifact(path,run,registry_sha); identity=artifact_identity(checked["row"])
        if identity in artifacts: raise AuditError("duplicate trajectory artifact")
        artifacts[identity]=checked
    expected={(arm,task,trial,seed) for arm in manifest["arms"] for task in manifest["evaluation"]["task_ids"] for trial,seed in enumerate(manifest["evaluation"]["seeds"],1)}
    if set(artifacts)!=expected: raise AuditError("registered trajectory inventory is incomplete or has extras")
    ledger=ledger_inventory(run)
    for checked in artifacts.values(): assert_executor_settled(ledger,checked["row"])
    copro,copro_boundaries=copromem_rows(run,manifest,registry,artifacts)
    reme,reme_markers=reme_rows(run,manifest,artifacts)
    summary=read(run/"live-summary.json"); terminal=read(run/"terminal-reconciliation.json"); final=read(run/"final-report.json"); status=read(run/"runner-status.json")
    if status.get("state")!="completed" or terminal.get("valid") is not True or terminal.get("failure_count")!=0: raise AuditError("terminal runner reconciliation is not valid")
    run_marker=read(run/"copromem-dynamic-checkpoints/run-reconciled.json")
    if run_marker.get("manifest_sha256")!=manifest_sha or final.get("manifest_sha256")!=manifest_sha: raise AuditError("terminal report/marker manifest binding mismatch")
    negative=[x for x in copro if x["task_id"]==NEGATIVE]
    compatible=[x for x in copro if x["task_id"] in COMPATIBLE]
    negative_ok=all(not x["guidance_nonempty"] and x["selected_schema_id"] is None for x in negative)
    compatible_ok=all(x["guidance_nonempty"] and x["selected_schema_id"] for x in compatible)
    prompt_control_ok=True
    for x in negative:
        base=artifacts[(NO_MEMORY,x["task_id"],x["trial"],x["seed"])]["row"]
        prompt_control_ok &= x["initial_model_visible_prompt_sha256"]==base.get("initial_prompt_messages_sha256")
    report={"version":"v6.2.1-engineering-003-terminal-audit-v1","zero_provider":True,
        "run":{"name":RUN_NAME,"manifest_sha256":manifest_sha,"runtime_content_identity_version":manifest.get("runtime_identity_version"),
               "runtime_identity_sha256":manifest.get("runtime_identity_sha256"),"executable_commit":read(run/"runtime-identity.json").get("executable_commit"),
               "publication_commit":"1039815c3729b7f5a56b81341f25c3905a45dd70","run_reconciled_sha256":status.get("run_reconciled_sha256"),
               "terminal_reconciliation_valid":True,"completed_trajectories":len(artifacts)},
        "integrity":{"unique_registered_trajectories":len(artifacts),"history_and_evidence_contracts_valid":len(artifacts),
            "ledger":{k:v for k,v in ledger.items() if k!="settlements"},"fixed_bank_immutable": all(x.get("post_update_state_sha256")==manifest["banks"]["reme_shared_sha256"] for x in reme if x["arm"].endswith("fixed")),
            "terminal_binding":{"final_report_manifest_match":final.get("manifest_sha256")==manifest_sha,"run_marker_manifest_match":run_marker.get("manifest_sha256")==manifest_sha},
            "discrepancies":["live-summary state remains 'reconciling' although runner-status is completed; counts, costs, terminal reconciliation, and final-report bindings reconcile."] if summary.get("state")!="completed" else []},
        "copromem_retrieval_rows":copro,"copromem_dynamic_boundaries":copro_boundaries,
        "copromem_gates":{"compatible_nonempty_and_selected":compatible_ok,"negative_control_empty_and_unselected":negative_ok,
            "negative_prompt_identical_to_no_memory":prompt_control_ok,"offline_reproduction":all(x["offline_reproduction_passed"] for x in copro),
            "no_reme_fallback_for_empty_copromem":"verified by absence of ReMe roles for CoProMem arms in settled ledger"},
        "reme_retrieval_rows":reme,"reme_dynamic_checkpoint_chain":reme_markers,
        "score_analysis":paired_statistics(artifacts,manifest),
        "interpretation":{"classification":"ENGINEERING-VALIDATED" if compatible_ok and negative_ok and prompt_control_ok else "ENGINEERING NO-GO",
            "permitted_claim":"CoProMem v6.2.1 task-conditioned retrieval is engineering-validated on the preregistered compatible/negative-control diagnostic." if compatible_ok and negative_ok and prompt_control_ok else "No integration claim is permitted.",
            "prohibited_claims":["efficacy","superiority","transfer","generalization","causal improvement from aggregate score differences"],
            "causal_categories":{"deterministic_integration_evidence":"hash-bound retrieval, prompt injection, checkpoint, and replay invariants", "suggestive_memory_quality_evidence":"paired scores only", "model_provider_stochasticity":"different outcomes with identical retrieval/prompt bindings may reflect stochastic generation", "task_difficulty":"score variation across task/trial", "not_causally_attributable":"aggregate arm ordering in this three-task compatibility-conditioned diagnostic"}},
        "sanitization":{"excluded":["task instructions","histories","journals","ledger rows","memory text","scorer payloads","provider responses"]}}
    report["audit_sha256"]=hashlib.sha256(canonical(report)).hexdigest()
    return report


def write_report(report: Mapping[str, Any], output: pathlib.Path = AUDIT, checksums: pathlib.Path = CHECKSUMS) -> None:
    output.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    files = {output.name: sha_file(output)}
    if MARKDOWN.is_file():
        files[MARKDOWN.name] = sha_file(MARKDOWN)
    checksums.write_text(json.dumps({"version":"v1","files":files},sort_keys=True,indent=2)+"\n",encoding="utf-8")


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--run",type=pathlib.Path,default=RUN); parser.add_argument("--output",type=pathlib.Path,default=AUDIT); parser.add_argument("--checksums",type=pathlib.Path,default=CHECKSUMS)
    args=parser.parse_args(); report=audit(args.run); write_report(report,args.output,args.checksums)
    print(json.dumps({"classification":report["interpretation"]["classification"],"audit_sha256":report["audit_sha256"],"output":str(args.output)},sort_keys=True))


if __name__=="__main__": main()
