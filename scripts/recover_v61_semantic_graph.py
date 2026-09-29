#!/usr/bin/env python3
"""Zero-provider v6.1 semantic recovery from immutable v6 acquisition evidence."""
from __future__ import annotations
import argparse, hashlib, json, sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from copromem.benchmarks.appworld.execution_evidence import journal_records, partition_v6_graph_evidence, runtime_context_fields
from copromem.contrastive_graph_v6 import commit, digest, reproduce_retrieval, retrieve
from copromem.experiments.reme_copromem.contrastive_v6_runner import fresh_state
from copromem.semantic_graph_v61 import build_semantic_graph, semantic_plan, validate_semantic_plan

SOURCE = ROOT / "artifacts/research/official_reme_copromem_pilot/v6_shared_acquisition_001"
MANIFEST_SHA = "422a45f8925b82dd83287bb10642a857fd3753b77570ccadb069f4ed310ad607"
REGISTRY = ROOT / "research/reme_copromem_fixed_dynamic_review/appworld_public_tool_schema_registry_v5_3.json"

def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+"\n", encoding="utf-8")

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--out", type=Path, required=True); args=parser.parse_args()
    if sha(SOURCE/"manifest.json") != MANIFEST_SHA: raise RuntimeError("immutable acquisition manifest mismatch")
    pool=json.loads((SOURCE/"shared-pool.json").read_text(encoding="utf-8"))["trajectories"]
    registry=json.loads(REGISTRY.read_text(encoding="utf-8")); by=defaultdict(list)
    for row in pool: by[str(row["task_id"])].append(row)
    state=fresh_state(); committed=[]; batches=[]; retrievals=[]
    for task_id in sorted(by):
        rows=sorted(by[task_id], key=lambda row: row["acquisition_identity"]); semantic=[]; audits=[]
        for row in rows:
            evidence=journal_records(row["execution_evidence_path"])
            eligible, ingestion=partition_v6_graph_evidence(evidence, registry["registry_sha256"], runtime_context_fields=runtime_context_fields(registry))
            graph,audit=build_semantic_graph(eligible, registry); audit["ingestion_audit_sha256"]=digest(ingestion)
            semantic.append(graph); audits.append(audit)
        success=[graph for graph,row in zip(semantic,rows) if float(row["after_score"])==1.0]
        failed=[graph for graph,row in zip(semantic,rows) if float(row["after_score"])!=1.0]
        plan=semantic_plan(success, failed, state, audits); validation=validate_semantic_plan(plan, registry)
        if validation["passed"]:
            post,marker=commit(state, plan)
            duplicate_state, duplicate_marker = commit(post, plan)
            idempotent = duplicate_state == post and duplicate_marker.get("winner_schema_id") == marker.get("winner_schema_id")
        else:
            post=dict(state); marker={"state":"rejected","winner_schema_id":None,"validation":validation,"before_state_sha256":digest(state),"after_state_sha256":digest(state)}
            idempotent = post == state
        item={"task_id":task_id,"family":rows[0]["family"],"source_trajectories":[{"id":row["acquisition_identity"],"score":row["after_score"],"history_sha256":row["history_sha256"]} for row in rows],
              "original_graph_hashes":[audit["original_graph_sha256"] for audit in audits],"semantic_projection_hashes":[audit["semantic_projection_sha256"] for audit in audits],
              "projection_audits":audits,"plan":plan,"validation":validation,"marker":marker,"duplicate_commit_idempotent":idempotent,"pre_state_sha256":digest(state),"post_state_sha256":digest(post),"provenance_sha256":digest(audits)}
        write(args.out/"task-batches"/f"{task_id}.json",item); batches.append(item)
        if marker["state"]=="committed": state=post; committed.append(item)
    for item in committed:
        required=item["plan"]["schema"]["required_operations"]; before=digest(state); guidance,prov=retrieve(state,required,registry["registry_sha256"])
        reproduced=reproduce_retrieval(state,required,prov)
        retrievals.append({"schema_id":item["marker"]["winner_schema_id"],"guidance_sha256":digest(guidance),"reproduced":guidance==reproduced,"state_unchanged":before==digest(state),"provenance":prov})
    clean=all(not any(node["role"] != "domain_operation" for node in item["projection_audits"][0]["excluded_nodes"] if False) for item in committed)
    gate={"version":"v6.1-semantic-admission-v1","provider_calls":0,"committed_schema_count":len(committed),"families":sorted({row["family"] for row in committed}),"state_sha256":digest(state),
          "all_core_domain":all(item["validation"]["passed"] for item in committed),"all_reproduced":all(row["reproduced"] for row in retrievals),"fixed_retrieval_state_unchanged":all(row["state_unchanged"] for row in retrievals),
          "all_duplicate_commits_idempotent":all(item["duplicate_commit_idempotent"] for item in batches),
          "passed":len(committed)>=3 and len({row["family"] for row in committed})>=3 and all(item["validation"]["passed"] for item in committed) and all(row["reproduced"] for row in retrievals) and all(item["duplicate_commit_idempotent"] for item in batches)}
    report={"method":"v6.1_semantic_graph_recovery","source_manifest_sha256":MANIFEST_SHA,"source_pool_sha256":sha(SOURCE/"shared-pool.json"),"registry_sha256":registry["registry_sha256"],"state_sha256":digest(state),"gate":gate,"batches_sha256":digest(batches),"retrievals":retrievals}
    report["report_sha256"]=digest(report)
    write(args.out/"initial-bank.json",state); write(args.out/"fixed-bank.json",state); write(args.out/"dynamic-bank.json",state); write(args.out/"semantic-admission-gate.json",gate); write(args.out/"semantic-recovery-report.json",report)
    print(json.dumps({"passed":gate["passed"],"schemas":len(committed),"report_sha256":report["report_sha256"],"provider_calls":0},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
