#!/usr/bin/env python3
"""Immutable-prefix continuation for the v6.2.5 CoProMem overlay.

The failed predecessor is never edited.  This successor verifies the nine
scored predecessor trajectories and three completed Dynamic transactions by
hash, uses the third post-state as its own initial bank, and schedules only
the remaining 97 tasks.
"""
from __future__ import annotations

import argparse, hashlib, json, shutil
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from copromem.contrastive_graph_v6 import digest
from copromem.experiments.reme_copromem.recovery_import import RecoveryImportError
from copromem.experiments.reme_copromem.runner import write_json
from copromem.experiments.reme_copromem.runtime_identity_v3 import build_evaluation_identity_v3
from scripts import run_v61_exploratory_evaluation as base
from scripts import run_v625_safe_terminal_slice_100x3 as overlay

PROTOCOL = "v6_2_5_safe_terminal_slice_four_arm_overlay_recovery_002"
SOURCE = overlay.REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_2_5_safe_terminal_slice_four_arm_overlay_001"
CUSTODY = "recovery-custody.json"
ADMISSION = "recovery-admission.json"
BANK = "recovery-initial-bank"
PREFIX_TASKS = 3
PREFIX_TRAJECTORIES = 9

def load(path: Path) -> dict[str, Any]:
    try: value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise RecoveryImportError(f"unreadable evidence: {path}") from exc
    if not isinstance(value, dict): raise RecoveryImportError("evidence is not a JSON object")
    return value

def sha(path: Path) -> str:
    if not path.is_file(): raise RecoveryImportError(f"evidence missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()

def canon(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def source() -> dict[str, Any]:
    manifest = load(SOURCE / "manifest.json")
    if sha(SOURCE / "manifest.json") != (SOURCE / "manifest.sha256").read_text().strip(): raise RecoveryImportError("source manifest hash mismatch")
    tasks, seeds = list(manifest.get("evaluation",{}).get("task_ids", ())), list(manifest.get("evaluation",{}).get("seeds", ()))
    if manifest.get("protocol") != overlay.PROTOCOL or manifest.get("arms") != [overlay.ARM] or len(tasks) != 100 or seeds != list(overlay.TRIAL_SEEDS): raise RecoveryImportError("wrong source schedule")
    artifacts=[]
    for pos, task in enumerate(tasks[:PREFIX_TASKS],1):
      for trial, seed in enumerate(seeds,1):
        artifact=SOURCE/"artifacts"/task/overlay.ARM/f"trial-{trial}.json"; row=load(artifact)
        expected={"task_id":task,"arm":overlay.ARM,"trial_id":trial,"seed":seed}
        if any(row.get(k)!=v for k,v in expected.items()) or not isinstance(row.get("trajectory_id"),str): raise RecoveryImportError("source artifact identity mismatch")
        journal=SOURCE/str(row.get("execution_evidence_path","")); retrieval=SOURCE/"retrievals"/task/f"{overlay.ARM}-{trial}.json"; binding=retrieval.with_suffix(".binding.json")
        if not journal.is_file() or not retrieval.is_file() or not binding.is_file(): raise RecoveryImportError("source artifact custody incomplete")
        artifacts.append({"position":len(artifacts)+1,"identity":expected,"trajectory_id":row["trajectory_id"],"artifact":str(artifact.resolve()),"artifact_sha256":sha(artifact),"journal":str(journal.resolve()),"journal_sha256":sha(journal),"retrieval":str(retrieval.resolve()),"retrieval_sha256":sha(retrieval),"binding":str(binding.resolve()),"binding_sha256":sha(binding)})
    if len(artifacts)!=PREFIX_TRAJECTORIES or len(list((SOURCE/"artifacts").rglob("trial-*.json")))!=PREFIX_TRAJECTORIES: raise RecoveryImportError("source prefix is incomplete or has extras")
    chains=[]; previous=None
    names=("task_pre_state_frozen","retrievals_materialized","trajectories_complete","batch_ready","semantic_plan_persisted","validation_persisted","commit_persisted","post_state_snapshot_persisted","next_task_authorized")
    for i,task in enumerate(tasks[:PREFIX_TASKS],1):
      root=SOURCE/"copromem-dynamic-checkpoints"/"tasks"/f"{i:04d}-{task}"; files=[root/f"{n:02d}-{name}.json" for n,name in enumerate(names,1)]; post=root/"post-state.json"; pre=root/"pre-state.json"
      if not all(x.is_file() for x in files+[post,pre]): raise RecoveryImportError("source Dynamic chain incomplete")
      p=load(post); state=p.get("state")
      if not isinstance(state,dict) or p.get("semantic_state_sha256")!=digest(state): raise RecoveryImportError("source Dynamic post-state invalid")
      if previous is not None and load(pre).get("semantic_state_sha256")!=previous: raise RecoveryImportError("source Dynamic chain transition mismatch")
      previous=str(p["semantic_state_sha256"]); chains.append({"task_id":task,"task_index":i,"post_state":str(post.resolve()),"post_state_sha256":previous,"post_state_file_sha256":sha(post),"records":[{"path":str(x.resolve()),"sha256":sha(x)} for x in files]})
    try: ledger=[json.loads(x) for x in (SOURCE/"ledger.jsonl").read_text().splitlines() if x]
    except (OSError,json.JSONDecodeError) as exc: raise RecoveryImportError("source ledger unreadable") from exc
    reserved={str(x.get("id")) for x in ledger if x.get("event")=="reserve"}; settled={str(x.get("id")) for x in ledger if x.get("event")=="settle"}
    if not reserved or reserved!=settled: raise RecoveryImportError("source ledger unresolved")
    exposure=sum((Decimal(str(x.get("usd",0))) for x in ledger if x.get("event")=="settle"),Decimal("0"))
    return {"manifest":manifest,"manifest_sha256":sha(SOURCE/"manifest.json"),"ledger_sha256":sha(SOURCE/"ledger.jsonl"),"ledger_rows":len(ledger),"exposure":str(exposure),"artifacts":artifacts,"chains":chains,"state":load(Path(chains[-1]["post_state"])),"remaining":tasks[PREFIX_TASKS:]}

def copy(source: Path,target: Path) -> None:
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists() and target.read_bytes()!=source.read_bytes(): raise RecoveryImportError(f"conflicting immutable successor input: {target}")
    if not target.exists(): shutil.copyfile(source,target)

def configure(run: Path, src: Mapping[str,Any]) -> None:
    overlay.configure(run) # installs v6.2.5 query/retrieval hooks and validates full original allocation.
    state=dict(src["state"]["state"]); remaining=list(src["remaining"])
    base.COPRO=run/BANK; base.FROZEN_TASK_IDS=remaining; base.ARMS=[overlay.ARM]; base.COPRO_DYNAMIC_ARM=overlay.ARM; base.COPRO_FIXED_ARM="copromem_v6_2_5_fixed_unregistered"; base.EVALUATION_SEEDS=tuple(overlay.TRIAL_SEEDS); base.CALL_LIMITS={**overlay.CALL_LIMITS,"executor":len(remaining)*3*30}; base.HARD_CAP_USD=overlay.HARD_CAP_USD; base.HISTORICAL_EXPOSURE=float(Decimal(str(src["exposure"]))); base.PROTOCOL=PROTOCOL
    base.PREEXISTING_RUN_FILES={overlay.ALLOCATION_NAME,"public-operation-intents.json","external-admission-receipt.json",CUSTODY,BANK}
    def identities(): return load(base.CONSTRUCTION/"FINAL_CONSTRUCTION_REPORT.json"),{"state_sha256":digest(state)}
    base.identities=identities

def prepare(run: Path) -> None:
    src=source()
    if run.exists() and any(run.iterdir()): raise RecoveryImportError("successor target must be empty")
    run.mkdir(parents=True)
    for name in (overlay.ALLOCATION_NAME,"public-operation-intents.json","external-admission-receipt.json"): copy(SOURCE/name,run/name)
    custody={"version":PROTOCOL,"source_run":str(SOURCE.resolve()),"source_manifest_sha256":src["manifest_sha256"],"source_ledger_sha256":src["ledger_sha256"],"source_ledger_rows":src["ledger_rows"],"historical_settled_exposure_usd":src["exposure"],"imported_trajectory_count":PREFIX_TRAJECTORIES,"imported_task_count":PREFIX_TASKS,"artifacts":src["artifacts"],"dynamic_checkpoint_chains":src["chains"],"restored_dynamic_state_sha256":src["chains"][-1]["post_state_sha256"],"next_task_id":src["remaining"][0],"remaining_task_count":len(src["remaining"]),"source_immutable":True,"provider_calls_replayed":False}; custody["custody_sha256"]=canon(custody); write_json(run/CUSTODY,custody)
    bank=run/BANK; bank.mkdir(); write_json(bank/"fixed-bank.json",src["state"]["state"]); write_json(bank/"semantic-admission-gate.json",{"state_sha256":custody["restored_dynamic_state_sha256"]}); write_json(bank/"recovery-report.json",{"version":PROTOCOL,"custody_sha256":custody["custody_sha256"]})
    configure(run,src); base.prepare(run); template=load(run/"template.json")
    template.update({"protocol":PROTOCOL,"method":{"copromem":overlay.POLICY_VERSION,"retrieval":"v6.2.5 admitted retrieval; continuation from immutable predecessor post-state","analysis_scope":"continuation only; predecessor evidence remains immutable"},"method_policy":overlay.frozen_policy(),"runtime_identity_version":"runtime-content-identity-v3","recovery":{"custody_file_sha256":sha(run/CUSTODY),"source_manifest_sha256":src["manifest_sha256"],"source_ledger_sha256":src["ledger_sha256"],"imported_trajectory_count":PREFIX_TRAJECTORIES,"remaining_trajectory_count":len(src["remaining"])*3,"restored_dynamic_state_sha256":custody["restored_dynamic_state_sha256"],"next_task_id":custody["next_task_id"]}})
    template["evaluation"].update({"task_ids":list(src["remaining"]),"task_count":len(src["remaining"]),"expected_trajectories":len(src["remaining"])*3,"recovery_imported_trajectories":PREFIX_TRAJECTORIES,"composite_expected_trajectories":300,"allocation_audit_sha256":sha(run/overlay.ALLOCATION_NAME)})
    template["banks"]["copromem_sha256"]=custody["restored_dynamic_state_sha256"]; template["budget"].update({"historical_settled_exposure":float(Decimal(src["exposure"])),"hard_cap_usd":overlay.HARD_CAP_USD,"call_limits":dict(base.CALL_LIMITS)}); template["execution"].update({"provider_only":overlay.CHAT_PROVIDER,"call_limits":dict(base.CALL_LIMITS)})
    runtime,inputs=build_evaluation_identity_v3(root=overlay.ROOT,manifest=template); write_json(run/"runtime-identity.json",runtime); write_json(run/"runtime-identity.binding.json",{"runtime_identity_sha256":runtime["runtime_identity_sha256"],"runtime_identity_record_sha256":sha(run/"runtime-identity.json")}); template["runtime_identity_inputs"]=inputs; template["runtime_identity_sha256"]=runtime["runtime_identity_sha256"]; template["runtime_identity_file_sha256"]=sha(run/"runtime-identity.json"); write_json(run/"template.json",template)

def verify(run: Path) -> dict[str,Any]:
    src=source(); custody=load(run/CUSTODY); recorded=custody.pop("custody_sha256",None)
    if recorded!=canon(custody) or custody.get("source_manifest_sha256")!=src["manifest_sha256"] or custody.get("source_ledger_sha256")!=src["ledger_sha256"] or custody.get("artifacts")!=src["artifacts"] or custody.get("dynamic_checkpoint_chains")!=src["chains"] or custody.get("next_task_id")!=src["remaining"][0]: raise RecoveryImportError("recovery custody differs from immutable predecessor")
    if digest(load(run/BANK/"fixed-bank.json"))!=src["chains"][-1]["post_state_sha256"]: raise RecoveryImportError("successor initial bank differs from immutable post-state")
    return src

def freeze(run: Path) -> None:
    src=verify(run); configure(run,src); base.freeze(run)

def preflight(run: Path) -> None:
    src=verify(run); configure(run,src); manifest=base.load(run)
    if manifest["evaluation"]["task_ids"]!=src["remaining"]: raise RecoveryImportError("successor does not begin at first unscored task")
    route=overlay.verify_locked_chat_route_available()
    if route.get("provider")!=overlay.CHAT_PROVIDER: raise RecoveryImportError("provider route changed")
    write_json(run/"provider-route-preflight.json",route); write_json(run/ADMISSION,{"version":PROTOCOL,"custody_file_sha256":sha(run/CUSTODY),"source_ledger_sha256":src["ledger_sha256"],"imported_trajectory_count":PREFIX_TRAJECTORIES,"next_task_id":src["remaining"][0],"provider_calls_replayed":False}); base.st(run,"preflight_passed",imported_completed_trajectories=PREFIX_TRAJECTORIES,next_task_id=src["remaining"][0])

def run(run: Path) -> None:
    src=verify(run); configure(run,src); preflight(run); base.run(run)

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("command",choices=("prepare","freeze","preflight","run")); p.add_argument("--run",required=True,type=Path); a=p.parse_args(); {"prepare":prepare,"freeze":freeze,"preflight":preflight,"run":run}[a.command](a.run.resolve())
if __name__=="__main__": main()
