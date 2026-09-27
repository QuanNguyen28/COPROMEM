#!/usr/bin/env python3
"""Read-only v4 restart reconciliation using the executor's canonical digest."""
from __future__ import annotations
import hashlib, json, pathlib
from scripts.run_fixed_dynamic_v4 import RUN, artifact, marker, verify_existing_artifact

TASK, TRIAL = "dac78d9_3", 1
ARMS = ["no_memory", "official_upstream_reme_fixed", "official_upstream_reme_dynamic"]

def main() -> None:
    evidence=[]
    for arm in ARMS:
        path=artifact(arm,TASK,TRIAL); row=verify_existing_artifact(path,arm,TASK,TRIAL)
        evidence.append({"arm":arm,"artifact_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                         "history_sha256":row["history_sha256"],"official_score":row["after_score"],
                         "dynamic_marker":marker(arm,TASK,TRIAL).is_file()})
    copro_artifact=artifact("copromem_fixed",TASK,TRIAL)
    copro_retrieval=RUN/"retrieval"/"copromem_fixed"/TASK/"trial-1.json"
    ledger=[json.loads(line) for line in (RUN/"ledger.jsonl").read_text(encoding="utf-8").splitlines() if line]
    settled=[x for x in ledger if x.get("event")=="settle"]
    copro_settled=[x for x in settled if "copromem" in str(x.get("role", "")) or "copromem_fixed" in str(x.get("role", ""))]
    report={"canonical_digest_source":"research.official_pilot.five_arm_runner.digest","task_id":TASK,"trial":TRIAL,
            "completed_valid":evidence,"copromem_fixed":{"artifact_exists":copro_artifact.exists(),"retrieval_exists":copro_retrieval.exists(),
            "settled_executor_or_decomposition_calls":len(copro_settled)}}
    out=RUN/"reconciliation-v2.json"; out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"completed_valid":len(evidence),"copromem_fixed_clean":not copro_artifact.exists() and not copro_retrieval.exists() and not copro_settled},sort_keys=True))

if __name__=="__main__": main()
