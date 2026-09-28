"""Zero-provider audit of a durable CoProMem task-boundary evidence bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from copromem.benchmarks.appworld.adapter import normalize_appworld_history
from copromem.experiments.reme_copromem.runner import digest, write_json
from copromem.experiments.reme_copromem.task_boundary import (
    POLICY_VERSION, commit_task_boundary_plan, plan_task_boundary_update,
    validate_task_boundary_plan,
)


def load(path: Path): return json.loads(path.read_text(encoding="utf-8"))
def sha(path: Path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--run", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); run=args.run; manifest=load(run / "manifest.json")
    task=manifest["evaluation"]["a_task_id"]; trials=[]; ledger=[json.loads(x) for x in (run / "ledger.jsonl").read_text().splitlines()]
    for trial, seed in zip(manifest["evaluation"]["trial_ids"], manifest["evaluation"]["seeds"]):
        scored_path=run / "evaluation" / "copromem_dynamic" / task / f"trial-{trial}.json"; baseline_path=run / "evaluation" / "no_memory" / task / f"trial-{trial}.json"
        scored, baseline=load(scored_path), load(baseline_path); history=scored["history"]
        role=f"executor:copromem_dynamic:{task}:trial={trial}:seed={seed}"
        cost=sum(float(x["usd"]) for x in ledger if x.get("event")=="settle" and x.get("role")==role)
        trials.append({"task_id":task,"seed":seed,"trajectory_index":trial,"intent":next(x["content"] for x in history if x["role"]=="user"),
            "score":float(scored["after_score"]),"no_memory_score":float(baseline["after_score"]),"cost_usd":cost,"actions":int(scored["actions"]),
            "actions_text":[x["content"] for x in history if x["role"]=="assistant"],"task_state":{"evaluation":True,"scored_artifact_sha256":sha(scored_path)},
            "events":[vars(x) for x in normalize_appworld_history(history,float(scored["after_score"])==1.0)],"scored_artifact_sha256":sha(scored_path)})
    pre=load(run / "copromem" / "initial-state.json"); descriptor=manifest["evaluation"]["descriptors"][task]
    plan=plan_task_boundary_update(pre,descriptor,trials,POLICY_VERSION); validation=validate_task_boundary_plan(plan); post,commit_validation=commit_task_boundary_plan(pre,plan)
    result={"immutable_manifest_sha256":sha(run / "manifest.json"),"task_id":task,"trial_artifact_sha256":[x["scored_artifact_sha256"] for x in trials],
      "plan_sha256":plan["plan_sha256"],"validation":validation,"commit_validation":commit_validation,
      "pre_state_sha256":digest(pre),"reconstructed_post_state_sha256":digest(post),"events_per_trial":[len(x["events"]) for x in trials],
      "provider_calls":0,"raw_payloads_written":False}
    write_json(args.output,result); print(json.dumps(result,sort_keys=True))

if __name__=="__main__": main()
