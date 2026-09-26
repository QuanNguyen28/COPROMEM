#!/usr/bin/env python3
"""Reconcile one interrupted fixed evaluation only from its durable journal."""
from __future__ import annotations
import hashlib, json, pathlib, time

ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
RUN = ROOT / "artifacts/research/official_reme_copromem_pilot/reduced_v2"
KEY = "evaluation:official_upstream_reme_fixed:024c982_1:seed=8101:trial=1"
JOURNAL = RUN / "journals/evaluation_official_upstream_reme_fixed_024c982_1_seed_8101_trial_1.jsonl"

def append(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"); f.flush()

def main():
    completed = RUN / "completed.jsonl"
    if completed.exists() and any(json.loads(x).get("key") == KEY for x in completed.read_text().splitlines() if x):
        print("already reconciled"); return
    events=[json.loads(x) for x in JOURNAL.read_text(encoding="utf-8").splitlines() if x]
    scores=[x for x in events if x.get("event") == "official_score"]
    actions=[x for x in events if x.get("event") == "action_applied"]
    progress=ROOT / "artifacts/research/official_reme_copromem_pilot/progress.jsonl"
    if not scores:
        append(completed,{"key":KEY,"time_ns":time.time_ns(),"state":"terminal_incomplete_no_durable_official_score",
            "journal":str(JOURNAL.relative_to(ROOT))})
        append(progress,{"event":"trajectory_terminal_incomplete","arm":"official_upstream_reme_fixed",
            "task_id":"024c982_1","seed":8101,"trial":1,"reason":"no_durable_official_score"})
        print("terminal incomplete: no durable score"); return
    score=scores[-1]; passed=int(score.get("pass_count",0)); failed=int(score.get("fail_count",0)); total=passed+failed
    result={"task_id":"024c982_1","seed":8101,"trial":1,"arm":"official_upstream_reme_fixed",
        "before_score":None,"after_score":(passed/total if total else 0.0),"actions":len(actions),
        "reconciled_from_durable_journal":True,"journal":str(JOURNAL.relative_to(ROOT)),
        "official_pass_count":passed,"official_fail_count":failed}
    artifact=RUN / "evaluation/official_upstream_reme_fixed-024c982_1-8101.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    digest=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    append(completed,{"key":KEY,"time_ns":time.time_ns(),"artifact":str(artifact.relative_to(ROOT)),"sha256":digest,
        "state":"reconciled_from_durable_native_actions_and_official_score"})
    append(progress,{"event":"trajectory_reconciled","stage":"evaluation","arm":"official_upstream_reme_fixed",
        "task_id":"024c982_1","seed":8101,"trial":1,"score":result["after_score"],"actions":len(actions),
        "evidence":"native_journal_and_official_score"})
    print(f"reconciled score={result['after_score']:.1f} actions={len(actions)}")
if __name__ == "__main__": main()
