#!/usr/bin/env python3
"""Durably close the pre-ceiling interrupted dynamic trajectory without replay."""
from __future__ import annotations
import json, pathlib, time

ROOT=pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
RUN=ROOT / "artifacts/research/official_reme_copromem_pilot/reduced_v2"
KEY="evaluation:official_upstream_reme_dynamic:024c982_2:seed=8102:trial=2"
J=RUN / "journals/evaluation_official_upstream_reme_dynamic_024c982_2_seed_8102_trial_2.jsonl"
def append(p, x):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a",encoding="utf-8") as f: f.write(json.dumps(x,sort_keys=True,separators=(",",":"))+"\n"); f.flush()
def main():
    c=RUN/"completed.jsonl"
    if c.exists() and any(json.loads(x).get("key")==KEY for x in c.read_text().splitlines() if x): print("already reconciled"); return
    events=[json.loads(x) for x in J.read_text(encoding="utf-8").splitlines() if x]
    scorer=[x for x in events if x.get("event")=="official_score"]
    # The only recorded score is the initial pre-action score; current native
    # state was closed with the process, so no post-action score is recoverable.
    append(c,{"key":KEY,"time_ns":time.time_ns(),"state":"terminal_incomplete_no_durable_post_action_official_score",
        "journal":str(J.relative_to(ROOT)),"action_count":sum(x.get("event")=="action_applied" for x in events)})
    append(ROOT/"artifacts/research/official_reme_copromem_pilot/progress.jsonl",{"event":"trajectory_terminal_incomplete",
        "stage":"evaluation","arm":"official_upstream_reme_dynamic","task_id":"024c982_2","seed":8102,"trial":2,
        "reason":"native_state_not_restorable_and_no_durable_post_action_official_score","initial_score_evidence":bool(scorer)})
    print("terminal incomplete; no replay")
if __name__=="__main__": main()
