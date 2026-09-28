"""Durable live-state dispatcher for CoProMem v6.

The dispatcher owns orchestration only.  Executors/scorers/ledgers are injected
shared boundaries; v5.3 task-boundary code is deliberately never imported.
"""
from __future__ import annotations
import hashlib, json, os
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from ...contrastive_graph_v6 import digest, reproduce_retrieval
from .contrastive_v6_runner import (STATE_FORMAT, commit_task_batch,
                                    plan_task_batch_from_artifacts,
                                    retrieval_record, validate_task_batch)
from .runner import execute_trajectory

VERSION = "copromem-v6-live-dispatcher-v1"
TRANSITIONS = ("initialized", "task_pre_state_frozen", "retrievals_materialized", "trajectories_complete", "batch_ready", "plan_persisted", "validation_persisted", "commit_persisted", "next_task_authorized", "finalized")


@dataclass(frozen=True)
class SharedTrajectoryExecutor:
    """Thin adapter to the maintained common executor boundary.

    Constructing this adapter has no side effects. Its call is the sole point
    at which a future registered launch reaches model/AppWorld/scorer code.
    """
    run: Path
    progress: Path
    ledger: Any
    api_key: str
    all_task_ids: list[str]
    max_actions: int
    temperature: float
    execution_evidence: dict[str, Any]
    # Kept injectable solely for deterministic boundary fixtures.  The live
    # default remains the maintained common executor; constructing this class
    # never reaches a provider or a task runtime.
    dispatch: Callable[..., dict[str, Any]] | None = None

    def __call__(self, *, task: str, pre_state: Mapping[str, Any], retrieval: Mapping[str, Any],
                 arm: str, trial: int, seed: int, **_: Any) -> dict[str, Any]:
        artifact_path = self.run / "trajectory-artifacts" / task / f"{arm}-{trial}.json"
        guidance = str(retrieval["guidance"])
        result = (self.dispatch or execute_trajectory)(
            run=self.run, progress=self.progress, ledger=self.ledger, api_key=self.api_key,
            all_task_ids=self.all_task_ids, arm=arm, task_id=task, trial_id=trial, seed=seed,
            max_actions=self.max_actions, temperature=self.temperature, phase="evaluation",
            artifact_path=artifact_path, execution_evidence=self.execution_evidence,
            memory_for_instruction=lambda _instruction, _benchmark, _meta: guidance,
        )
        evidence_path = result.get("execution_evidence_path")
        if not evidence_path:
            raise ValueError("shared executor did not durably produce execution evidence")
        return {**result, "evidence_path": str(evidence_path),
                "shared_executor_artifact": str(artifact_path),
                "retrieval_pre_state_sha256": digest(pre_state)}

def _write(path: Path, value: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True); payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()+b"\n"
    tmp=path.with_suffix(path.suffix+".tmp")
    with tmp.open("wb") as h: h.write(payload); h.flush(); os.fsync(h.fileno())
    os.replace(tmp,path); return hashlib.sha256(payload).hexdigest()

def _read(path: Path) -> dict[str, Any]:
    row=json.loads(path.read_text(encoding="utf-8"));
    if row.get("record_sha256") != digest({k:v for k,v in row.items() if k!="record_sha256"}): raise ValueError("dispatcher record hash mismatch")
    return row

class ContrastiveV6Dispatcher:
    def __init__(self, run: Path, registry: Mapping[str, Any], executor: Callable[..., dict[str, Any]], *, policy_sha256: str,
                 planner: Callable[..., tuple[dict[str, Any], dict[str, Any]]] = plan_task_batch_from_artifacts,
                 validator: Callable[[Mapping[str, Any]], dict[str, Any]] = validate_task_batch,
                 committer: Callable[[Mapping[str, Any], Mapping[str, Any]], tuple[dict[str, Any], dict[str, Any]]] = commit_task_batch,
                 checkpoint_hook: Callable[[str, Mapping[str, Any]], None] | None = None):
        self.run,self.registry,self.executor,self.policy_sha256=run,dict(registry),executor,policy_sha256
        if not self.registry.get("registry_sha256"): raise ValueError("frozen registry required")
        self.planner,self.validator,self.committer=planner,validator,committer
        self.checkpoint_hook=checkpoint_hook
    def _record(self, task: str, transition: str, **body: Any) -> dict[str, Any]:
        if transition not in TRANSITIONS: raise ValueError("unknown transition")
        row={"version":VERSION,"task":task,"transition":transition,"policy_sha256":self.policy_sha256,**body}; row["record_sha256"]=digest(row)
        path=self.run/"state-machine"/task/f"{transition}.json"
        if path.exists():
            existing=_read(path)
            if existing != row: raise ValueError(f"immutable transition conflict: {transition}")
            return existing
        _write(path,row)
        if self.checkpoint_hook is not None:
            self.checkpoint_hook(transition, row)
        return row
    def _existing(self, task: str, transition: str) -> dict[str, Any]|None:
        p=self.run/"state-machine"/task/f"{transition}.json"; return _read(p) if p.exists() else None
    def prepare(self, task: str, pre_state: Mapping[str,Any], queries: list[list[str]]) -> list[dict[str,Any]]:
        initialized = self._existing(task, "initialized")
        if initialized is None:
            initialized = self._record(task,"initialized",state_format=STATE_FORMAT,registry_sha256=self.registry["registry_sha256"])
        if initialized.get("registry_sha256") != self.registry["registry_sha256"]:
            raise ValueError("initialized task registry mismatch")
        if len(queries) < 2: raise ValueError("v6 requires at least two same-task retrievals")
        frozen=self._existing(task,"task_pre_state_frozen") or self._record(task,"task_pre_state_frozen",state=dict(pre_state),state_sha256=digest(pre_state))
        if frozen["state_sha256"]!=digest(pre_state): raise ValueError("task pre-state mismatch")
        result=[]
        for trial,query in enumerate(queries,1):
            p=self.run/"retrievals"/task/f"trial-{trial}.json"
            if p.exists(): row=_read(p)
            else:
                guidance,prov=retrieval_record(state=pre_state,query_operations=query,registry_sha256=self.registry["registry_sha256"])
                row={"version":VERSION,"task":task,"trial":trial,"pre_state_sha256":digest(pre_state),"query":query,"guidance":guidance,"provenance":prov};row["record_sha256"]=digest(row);_write(p,row)
                if self.checkpoint_hook is not None:
                    self.checkpoint_hook("retrieval_persisted", row)
            if row["pre_state_sha256"]!=digest(pre_state) or reproduce_retrieval(pre_state,row["query"],row["provenance"])!=row["guidance"]: raise ValueError("retrieval reconciliation failure")
            result.append(row)
        if len({r["pre_state_sha256"] for r in result}) != 1: raise ValueError("same-task retrieval state split")
        self._record(task,"retrievals_materialized",retrieval_hashes=[r["record_sha256"] for r in result],pre_state_sha256=digest(pre_state))
        return result
    def execute_batch(self, task:str, pre_state:Mapping[str,Any], queries:list[list[str]], trials:list[dict[str,Any]])->tuple[dict[str,Any],dict[str,Any]]:
        retrievals=self.prepare(task,pre_state,queries); artifacts=[]
        if len(trials) != len(retrievals):
            raise ValueError("registered trials and same-task retrievals differ")
        for trial,retrieval in zip(trials,retrievals):
            path=self.run/"trajectories"/task/f"{trial['arm']}-{trial['trial']}.json"
            if path.exists(): artifact=_read(path)
            else:
                artifact=self.executor(task=task,pre_state=pre_state,retrieval=retrieval,**trial)
                if "after_score" not in artifact or "evidence_path" not in artifact: raise ValueError("durable scorer/evidence artifact required")
                artifact={"version":VERSION,**artifact};artifact["record_sha256"]=digest(artifact);_write(path,artifact)
            artifacts.append(artifact)
        self._record(task,"trajectories_complete",artifact_hashes=[a["record_sha256"] for a in artifacts])
        committed = self._existing(task, "commit_persisted")
        if committed:
            post = committed.get("post_state")
            marker = committed.get("marker")
            if digest(post) != committed.get("post_state_sha256") or not isinstance(marker, Mapping):
                raise ValueError("invalid persisted commit")
            # A power loss after the semantic transaction is not permission to
            # repeat lifecycle work.  Finish only the remaining durable state
            # transitions from the exact committed payload.
            if self._existing(task, "next_task_authorized") is None:
                self._record(task, "next_task_authorized", post_state_sha256=digest(post))
            if self._existing(task, "finalized") is None:
                self._record(task, "finalized", terminal_artifact_hashes=[a["record_sha256"] for a in artifacts],
                             post_state_sha256=digest(post), reconciliation="complete")
            return dict(post), dict(marker)
        rejected = self._existing(task, "finalized")
        if rejected:
            marker = rejected.get("marker")
            if not isinstance(marker, Mapping) or marker.get("state") != "rejected":
                raise ValueError("invalid persisted rejection")
            return dict(pre_state), dict(marker)
        copro=[a for a in artifacts if a["arm"]=="copromem_v6_dynamic"]
        if len(copro) < 2: raise ValueError("at least two complete CoProMem trajectories required")
        persisted_plan = self._existing(task, "plan_persisted")
        if persisted_plan is None:
            plan,audit=self.planner(artifacts=copro,registry=self.registry,pre_state=pre_state,evidence_paths=[a["evidence_path"] for a in copro])
            self._record(task,"batch_ready",audit=audit)
            self._record(task,"plan_persisted",plan=plan,plan_sha256=plan["plan_sha256"])
        else:
            plan = persisted_plan.get("plan")
            if not isinstance(plan, Mapping) or persisted_plan.get("plan_sha256") != plan.get("plan_sha256"):
                raise ValueError("invalid persisted v6 plan")
            if self._existing(task, "batch_ready") is None:
                raise ValueError("persisted v6 plan lacks batch-ready audit")
        persisted_validation = self._existing(task, "validation_persisted")
        if persisted_validation is None:
            validation=self.validator(plan)
            self._record(task,"validation_persisted",validation=validation)
        else:
            validation = persisted_validation.get("validation")
            if not isinstance(validation, Mapping) or validation.get("plan_sha256") != plan.get("plan_sha256"):
                raise ValueError("invalid persisted v6 validation")
        post,marker=self.committer(pre_state,plan)
        if marker.get("validation") != validation: raise ValueError("commit validation mismatch")
        if marker["state"]=="committed":
            replay_post,replay_marker=self.committer(pre_state,plan)
            if replay_post != post or replay_marker != marker: raise ValueError("non-idempotent v6 commit")
            self._record(task,"commit_persisted",marker=marker,post_state=post,post_state_sha256=digest(post))
            self._record(task,"next_task_authorized",post_state_sha256=digest(post))
            self._record(task,"finalized",terminal_artifact_hashes=[a["record_sha256"] for a in artifacts],
                         post_state_sha256=digest(post),reconciliation="complete")
        else: self._record(task,"finalized",marker=marker,post_state_sha256=digest(pre_state))
        return post,marker

    def reconcile(self, task: str, pre_state: Mapping[str, Any], *, ledger_reconciled: bool) -> str:
        """Fail-closed restart decision; never dispatches an external operation."""
        if not ledger_reconciled: raise ValueError("unsettled reservation blocks restart")
        frozen=self._existing(task,"task_pre_state_frozen")
        if frozen and frozen["state_sha256"] != digest(pre_state): raise ValueError("restart pre-state mismatch")
        for transition in TRANSITIONS:
            if self._existing(task,transition): continue
            return transition
        return "complete"

    def authorize_b(self, a_task: str, b_task: str) -> dict[str, Any]:
        """Open B only from A's persisted committed post-state."""
        marker = self._existing(a_task, "commit_persisted")
        if not marker or marker.get("marker", {}).get("state") != "committed":
            raise ValueError("B is permanently unopened because A lacks a committed schema")
        post = marker.get("post_state")
        if digest(post) != marker.get("post_state_sha256"):
            raise ValueError("A post-state hash mismatch")
        return self._record(b_task, "initialized", state_format=STATE_FORMAT,
                            registry_sha256=self.registry["registry_sha256"],
                            authorized_from_task=a_task,
                            authorized_pre_state_sha256=marker["post_state_sha256"],
                            selected_schema_id=marker["marker"].get("winner_schema_id"))

    def finalize(self, task: str, *, terminal_artifact_hashes: list[str]) -> dict[str, Any]:
        """Durably reconcile a completed task without changing its semantic state."""
        commit = self._existing(task, "commit_persisted")
        rejection = self._existing(task, "finalized")
        if rejection:
            return rejection
        if not commit:
            raise ValueError("cannot finalize without committed or rejected task gate")
        return self._record(task, "finalized", terminal_artifact_hashes=terminal_artifact_hashes,
                            post_state_sha256=commit["post_state_sha256"],
                            reconciliation="complete")
