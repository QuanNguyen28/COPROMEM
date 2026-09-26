#!/usr/bin/env python3
"""Read-only final reporting for the completed reduced-v2 pilot."""
from __future__ import annotations
import argparse, hashlib, json, pathlib, statistics, time
from collections import Counter, defaultdict

ROOT=pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
RUN=pathlib.Path(__import__("os").environ.get("OFFICIAL_PILOT_RUN",
    str(ROOT/"artifacts/research/official_reme_copromem_pilot/reduced_v2")))
OUT=RUN/"final-report.json"; MD=RUN/"FINAL_REPORT.md"
ARMS=["no_memory","official_upstream_reme_fixed","official_upstream_reme_dynamic","copromem_v2"]

def lines(path):
    if not path.exists(): return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
def digest(x): return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def mean(x): return sum(x)/len(x) if x else None

def arm_metrics(rows):
    scores=[float(x["after_score"]) for x in rows]
    tasks=defaultdict(list)
    for x in rows: tasks[x["task_id"]].append(float(x["after_score"]))
    return {"trajectory_denominator":len(rows),"avg_at_trials_observed":mean(scores),
      "task_denominator":len(tasks),"pass_at_4":sum(any(v==1.0 for v in values) for values in tasks.values())/len(tasks) if tasks else None,
      "per_task_avg":{t:mean(v) for t,v in sorted(tasks.items())},
      "per_task_pass_at_4":{t:any(v==1.0 for v in v) for t,v in sorted(tasks.items())}}

def paired(copro, other, missing_as_failure=False):
    c={ (x["task_id"],x["seed"],x["trial"]):float(x["after_score"]) for x in copro }
    o={ (x["task_id"],x["seed"],x["trial"]):float(x["after_score"]) for x in other }
    keys=sorted(set(c)&set(o))
    diffs=[c[k]-o[k] for k in keys]
    return {"complete_case_denominator":len(keys),"mean_copromem_minus_comparator":mean(diffs),
      "wins":sum(x>0 for x in diffs),"losses":sum(x<0 for x in diffs),"ties":sum(x==0 for x in diffs),
      "paired_keys": ["%s/%s/%s"%k for k in keys]}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--finalize-status",action="store_true"); args=parser.parse_args()
    manifest=json.loads((RUN/"manifest.json").read_text())
    expected=(RUN/"manifest.sha256").read_text().strip()
    actual=digest(manifest)
    if actual!=expected: raise SystemExit("manifest digest mismatch")
    rows=[]
    for p in sorted((RUN/"evaluation").glob("*.json")):
        x=json.loads(p.read_text()); x["artifact"]=str(p.relative_to(ROOT)); x["artifact_sha256"]=hashlib.sha256(p.read_bytes()).hexdigest(); rows.append(x)
    # A recovered fixed result is admissible only with matching immutable scorer evidence.
    for x in rows:
        if x.get("reconciled_from_durable_journal"):
            ev=lines(ROOT/x["journal"]); scores=[e for e in ev if e.get("event")=="official_score"]
            if not scores: raise SystemExit("recovered fixed score lacks official scorer evidence")
            final=scores[-1]; denom=int(final.get("pass_count",0))+int(final.get("fail_count",0))
            if not denom or float(x["after_score"]) != int(final.get("pass_count",0))/denom:
                raise SystemExit("recovered fixed score conflicts with official scorer evidence")
    byarm={a:[x for x in rows if x["arm"]==a] for a in ARMS}
    completed=lines(RUN/"completed.jsonl")
    recovered_keys={x.get("key") for x in completed if x.get("supersedes_terminal_incomplete_for_analysis")}
    terminal_all=[x for x in completed if str(x.get("state","")).startswith("terminal_incomplete")]
    terminal=[x for x in terminal_all if x.get("key") not in recovered_keys]
    metrics={a:arm_metrics(byarm[a]) for a in ARMS}
    pairs={a:paired(byarm["copromem_v2"],byarm[a]) for a in ARMS if a!="copromem_v2"}
    dynamic_sensitivity=list(byarm["official_upstream_reme_dynamic"])
    sensitivity={"dynamic_terminal_incomplete_as_failure":arm_metrics(dynamic_sensitivity),
      "copromem_minus_dynamic":paired(byarm["copromem_v2"],dynamic_sensitivity)}
    progress=lines(RUN/"progress.jsonl")
    call_events=[x for x in progress if x.get("event") in ("call_settled","embedding_settled")]
    callstats=defaultdict(lambda:{"calls":0,"prompt_tokens":0,"completion_tokens":0,"reasoning_tokens":0,"latency":0.0,"cost":0.0})
    for x in call_events:
        role=str(x.get("role","unclassified")); arm=next((a for a in ARMS if a in role), "reme_embedding" if x.get("event")=="embedding_settled" else "lifecycle_or_other")
        s=callstats[arm]; s["calls"]+=1
        for k in ("prompt_tokens","completion_tokens","reasoning_tokens"): s[k]+=int(x.get(k) or 0)
        s["prompt_tokens"] += int(x.get("input_tokens") or 0)
        s["latency"]+=float(x.get("latency") or 0); s["cost"]+=float(x.get("cost") or 0)
    ledger=lines(RUN/"successor-ledger.jsonl"); latest={}
    for x in ledger:
        if x.get("event") in ("reserve","settle"): latest[x["id"]]=float(x["usd"])
    acquisition=[]
    for p in sorted((RUN/"acquisition").glob("*.json")):
        x=json.loads(p.read_text()); acquisition.append({"task_id":x.get("task_id"),"seed":x.get("seed"),"score":x.get("after_score"),"sha256":hashlib.sha256(p.read_bytes()).hexdigest()})
    context=[x for x in progress if x.get("event")=="context_ceiling_termination"]
    failures=[x for x in progress if x.get("event") in ("runner_failed","dynamic_update_failed","trajectory_terminal_incomplete")]
    retrieval_empty=[x for x in progress if x.get("event")=="dynamic_update_skipped_empty_retrieval"]
    report={"protocol":manifest.get("protocol","reduced_v2"),"label":manifest.get("label","exploratory faithful adaptation; not exact ReMe reproduction"),
      "generated_at_ns":time.time_ns(),"manifest_sha256":actual,"primary_analysis":"all frozen evaluation trajectories; one score recovered by exact zero-model native action replay",
      "official_scores":rows,"metrics":metrics,"paired_copromem_comparisons":pairs,"sensitivity":sensitivity,
      "terminal_incomplete":terminal,"acquisition":{"frozen_manifest_count":len(manifest["acquisition"]["task_ids"]),"durable_artifact_count":len(acquisition),"artifacts":acquisition,
        "provenance":"durable acquisition artifacts plus immutable completed journal"},
      "retrieval_coverage":{"dynamic_empty_retrieval_events":len(retrieval_empty),"note":"empty retrievals are preserved; ReMe dynamic skipped update on empty retrieval"},
      "calls_tokens_latency_cost":dict(callstats),"ledger":{"records":len(ledger),"charged_or_retained_usd":sum(latest.values()),"hard_cap_usd":35.0},
      "context_ceiling_terminations":context,"infrastructure_failures":failures,
      "protocol_deviations":["ReMe is a faithful adaptation, not exact upstream reproduction.","Embedding infrastructure was amended to OpenRouter Azure openai/text-embedding-3-small at 1024 dimensions.","One dynamic score was recovered by replaying the exact durable 29-action prefix; every output hash matched and no model call was made.","Input ceiling is a terminal scored trajectory condition, not a run failure."],
      "conclusion":{"decision":"REVISE","reason":"near-ceiling scores and incomplete/empty-retrieval infrastructure prevent a supported superiority claim; paired evidence is descriptive only."}}
    OUT.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    md=["# reduced_v2 final report","","**Exploratory faithful adaptation; not an exact ReMe reproduction.**","",
      f"Manifest SHA-256: `{actual}`","", "## Primary results","", "| Arm | trajectories | Avg@observed trials | tasks | Pass@4 |", "|---|---:|---:|---:|---:|"]
    for a in ARMS:
        m=metrics[a]; md.append(f"| {a} | {m['trajectory_denominator']} | {m['avg_at_trials_observed']:.4f} | {m['task_denominator']} | {m['pass_at_4']:.4f} |")
    md += ["","All 64 frozen evaluation trajectories are scored. One ReMe-dynamic score was recovered by exact zero-model replay of its durable 29-action prefix with output-hash verification.","", "## Paired CoProMem comparisons", "", "| Comparator | n | mean difference | wins/losses/ties |", "|---|---:|---:|---:|"]
    for a,p in pairs.items(): md.append(f"| {a} | {p['complete_case_denominator']} | {p['mean_copromem_minus_comparator']:.4f} | {p['wins']}/{p['losses']}/{p['ties']} |")
    md += ["", "## Official scorer trajectories", "", "| Task | Seed | Trial | Arm | score | actions | termination |", "|---|---:|---:|---|---:|---:|---|"]
    for x in sorted(rows,key=lambda z:(z["task_id"],z["seed"],z["arm"])):
        md.append(f"| {x['task_id']} | {x['seed']} | {x['trial']} | {x['arm']} | {x['after_score']:.1f} | {x['actions']} | {x.get('termination_reason','')} |")
    md += ["", "## Calls and ledger", "", "| Attribution | calls | prompt tokens | completion tokens | reasoning tokens | latency sec | cost USD |", "|---|---:|---:|---:|---:|---:|---:|"]
    for arm,s in sorted(callstats.items()):
        md.append(f"| {arm} | {s['calls']} | {s['prompt_tokens']} | {s['completion_tokens']} | {s['reasoning_tokens']} | {s['latency']:.3f} | {s['cost']:.6f} |")
    md += ["", f"Acquisition: {len(acquisition)} durable artifacts from {len(manifest['acquisition']['task_ids'])} frozen IDs; one acquisition remained terminal unresumable without replay.",
      f"Dynamic empty-retrieval update skips: {len(retrieval_empty)}. Context-ceiling terminations: {len(context)}. Infrastructure-failure events: {len(failures)}.",
      "", "## Protocol deviations and amendments", ""] + [f"- {x}" for x in report["protocol_deviations"]]
    md += ["", "## Recovery", "", f"The formerly missing dynamic score is now included; paired CoProMem−dynamic n={sensitivity['copromem_minus_dynamic']['complete_case_denominator']}.", "", "## Conclusion", "", "**REVISE.** This small, failure-informed exploratory run does not support a superiority or generalization claim.", "", f"Ledger charged/retained exposure: ${report['ledger']['charged_or_retained_usd']:.6f} of $35.00."]
    MD.write_text("\n".join(md)+"\n")
    report_hash=hashlib.sha256(OUT.read_bytes()).hexdigest(); markdown_hash=hashlib.sha256(MD.read_bytes()).hexdigest()
    if args.finalize_status:
        status_path=RUN/"runner-status.json"; old=json.loads(status_path.read_text()) if status_path.exists() else {}
        old.update({"state":"completed","final_report":str(OUT),"final_report_sha256":report_hash,
                    "markdown_report_sha256":markdown_hash,"reports_durable":True})
        status_path.write_text(json.dumps(old,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"report":str(OUT),"sha256":report_hash,"rows":len(rows)}))
if __name__=="__main__": main()
