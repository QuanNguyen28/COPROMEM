#!/usr/bin/env python3
"""Regenerate sanitized medium_v1 results from ignored local evidence only."""
from __future__ import annotations
import hashlib, json, math, pathlib
from collections import defaultdict

ROOT=pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
RUN=ROOT/"artifacts/research/official_reme_copromem_pilot/medium_v1"
OUT=ROOT/"research/medium_v1_results"; ARMS=["no_memory","official_upstream_reme_fixed","official_upstream_reme_dynamic","copromem_v2"]
def sha_path(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p): return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []
def avg(v): return sum(v)/len(v) if v else None
def ci(v):
    if len(v)<2:return [None,None]
    m=avg(v); se=(sum((x-m)**2 for x in v)/(len(v)-1)/len(v))**.5
    return [m-1.96*se,m+1.96*se]
def main():
    manifest=json.loads((RUN/"manifest.json").read_text()); expected=(RUN/"manifest.sha256").read_text().strip()
    canonical=json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()
    if hashlib.sha256(canonical).hexdigest()!=expected: raise SystemExit("manifest digest mismatch")
    artifacts=[]; evidence=[]
    for p in sorted((RUN/"evaluation").glob("*.json")):
        x=json.loads(p.read_text()); artifacts.append({k:x[k] for k in ("task_id","seed","trial","arm","after_score","actions")})
        evidence.append({"path":str(p.relative_to(ROOT)),"sha256":sha_path(p),"kind":"evaluation_artifact"})
    if len(artifacts)!=640: raise SystemExit(f"incomplete evaluation: {len(artifacts)}/640")
    expected_keys={(t,s,i,a) for t in manifest["evaluation"]["task_ids"] for i,s in enumerate(manifest["evaluation"]["seeds"],1) for a in ARMS}
    actual_keys={(x["task_id"],x["seed"],x["trial"],x["arm"]) for x in artifacts}
    if actual_keys!=expected_keys: raise SystemExit("evaluation identity mismatch")
    acq=[]
    for item in manifest["acquisition_source"]["artifacts"]:
        p=ROOT/item["path"]
        if sha_path(p)!=item["sha256"]: raise SystemExit("acquisition evidence hash mismatch")
        acq.append(item); evidence.append({"path":item["path"],"sha256":item["sha256"],"kind":"reused_acquisition"})
    byarm=defaultdict(list); taskarm=defaultdict(list)
    for x in artifacts: byarm[x["arm"]].append(x); taskarm[(x["task_id"],x["arm"])].append(x)
    metrics={}; per_task={}
    for arm in ARMS:
        scores=[x["after_score"] for x in byarm[arm]]
        task_scores={t:avg([x["after_score"] for x in taskarm[(t,arm)]]) for t in manifest["evaluation"]["task_ids"]}
        metrics[arm]={"trajectory_denominator":160,"task_denominator":40,"avg_at_4":avg(scores),"pass_at_4":sum(any(x["after_score"]==1 for x in taskarm[(t,arm)]) for t in manifest["evaluation"]["task_ids"])/40,"mean_actions":avg([x["actions"] for x in byarm[arm]])}
        per_task[arm]=task_scores
    paired={}; lookup={(x["task_id"],x["seed"],x["trial"],x["arm"]):x["after_score"] for x in artifacts}
    for arm in ARMS[:-1]:
        diffs=[]
        for t in manifest["evaluation"]["task_ids"]:
            diffs.append(avg([lookup[(t,s,i,"copromem_v2")]-lookup[(t,s,i,arm)] for i,s in enumerate(manifest["evaluation"]["seeds"],1)]))
        paired[arm]={"paired_task_denominator":40,"copromem_minus_comparator_mean":avg(diffs),"normal_approx_95_ci":ci(diffs),"wins":sum(x>0 for x in diffs),"losses":sum(x<0 for x in diffs),"ties":sum(x==0 for x in diffs)}
    progress=rows(RUN/"progress.jsonl"); calls=defaultdict(lambda:{"calls":0,"prompt_tokens":0,"completion_tokens":0,"reasoning_tokens":0,"latency_seconds":0.0,"cost_usd":0.0})
    for x in progress:
        if x.get("event") not in ("call_settled","embedding_settled"):continue
        role=str(x.get("role","")); arm=next((a for a in ARMS if a in role),"lifecycle_or_embedding")
        d=calls[arm]; d["calls"]+=1; d["prompt_tokens"]+=int(x.get("prompt_tokens") or x.get("input_tokens") or 0); d["completion_tokens"]+=int(x.get("completion_tokens") or 0); d["reasoning_tokens"]+=int(x.get("reasoning_tokens") or 0); d["latency_seconds"]+=float(x.get("latency") or 0); d["cost_usd"]+=float(x.get("cost") or 0)
    ledger=rows(RUN/"successor-ledger.jsonl"); latest={}
    for x in ledger:
        if x.get("event") in ("reserve","settle"):latest[x["id"]]=float(x["usd"])
    evidence += [{"path":str((RUN/"manifest.json").relative_to(ROOT)),"sha256":sha_path(RUN/"manifest.json"),"kind":"manifest"},{"path":str((RUN/"progress.jsonl").relative_to(ROOT)),"sha256":sha_path(RUN/"progress.jsonl"),"kind":"progress"},{"path":str((RUN/"successor-ledger.jsonl").relative_to(ROOT)),"sha256":sha_path(RUN/"successor-ledger.jsonl"),"kind":"ledger"}]
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    (OUT/"manifest.sha256").write_text(expected+"\n")
    (OUT/"evidence-checksums.json").write_text(json.dumps({"evidence":evidence},sort_keys=True,indent=2)+"\n")
    report={"protocol":"medium_v1","label":"diagnostic faithful adaptation; not exact ReMe reproduction","manifest_sha256":expected,"completion":{"expected_evaluation_trajectories":640,"completed_evaluation_trajectories":640,"complete":True},"budget":{"hard_cap_usd":140.0,"charged_or_retained_usd":sum(latest.values())},"acquisition":{"registered_slots":6,"reused_immutable_artifacts":5},"metrics":metrics,"per_task_avg_at_4":per_task,"paired_copromem":paired,"calls_tokens_latency_cost":dict(calls),"retrieval_and_guidance_limitation":"ReMe retrieval was empty; CoProMem evaluation supplied empty intent and consequently generic/empty guidance. This is diagnostic plumbing evidence, not a valid memory-method efficacy comparison.","protocol_deviations":["C-drive operational floor amended from 10 GB to 5 GB only.","ReMe is a faithful adaptation, not an exact paper reproduction."],"conclusion":{"decision":"REVISE","reason":"Complete execution, but empty retrieval and non-informative CoProMem guidance preclude a method-superiority interpretation."}}
    (OUT/"final-report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    md=["# medium_v1 final report","","**Diagnostic faithful adaptation; not an exact ReMe reproduction.**","",f"Manifest SHA-256: `{expected}`","",f"Completion: **640 / 640** evaluation trajectories. Hard cap: **USD 140**; charged/retained: **USD {sum(latest.values()):.6f}**.","", "## Arm metrics","","| Arm | Avg@4 | Pass@4 | trajectories | mean actions |","|---|---:|---:|---:|---:|"]
    for a in ARMS: m=metrics[a]; md.append(f"| {a} | {m['avg_at_4']:.4f} | {m['pass_at_4']:.4f} | 160 | {m['mean_actions']:.2f} |")
    md += ["","## Paired task-level CoProMem comparisons","","| Comparator | tasks | mean difference | 95% normal CI | W/L/T |","|---|---:|---:|---:|---:|"]
    for a,p in paired.items(): md.append(f"| {a} | 40 | {p['copromem_minus_comparator_mean']:.4f} | [{p['normal_approx_95_ci'][0]:.4f}, {p['normal_approx_95_ci'][1]:.4f}] | {p['wins']}/{p['losses']}/{p['ties']} |")
    md += ["","## Scientific limitation","",report["retrieval_and_guidance_limitation"],"","**REVISE:** no superiority claim is supported."]
    (OUT/"FINAL_REPORT.md").write_text("\n".join(md)+"\n")
    print("PASS sanitized medium_v1 report regenerated")
if __name__=="__main__":main()
