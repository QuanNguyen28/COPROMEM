#!/usr/bin/env python3
"""Read-only report generator for corrected_fixed_dynamic_appworld_v1."""
from __future__ import annotations
import hashlib, json, os, pathlib, random
from collections import defaultdict
from typing import Any

ROOT=pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
RUN=pathlib.Path(os.environ.get("CORRECTED_FIXED_DYNAMIC_RUN", ROOT/"artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v1"))
ARMS=["no_memory","official_upstream_reme_fixed","official_upstream_reme_dynamic","copromem_fixed","copromem_dynamic"]

def mean(values: list[float]) -> float: return sum(values)/len(values)
def sha(path: pathlib.Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def rows(path: pathlib.Path) -> list[dict[str,Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []

def cluster_ci(diffs: dict[str,list[float]]) -> list[float|None]:
    keys=sorted(diffs)
    if len(keys)<2:return [None,None]
    randomizer=random.Random(0)
    samples=[]
    for _ in range(2000):
        selected=[randomizer.choice(keys) for _ in keys]
        samples.append(mean([value for key in selected for value in diffs[key]]))
    samples.sort(); return [samples[49],samples[1949]]

def main() -> None:
    manifest_name="manifest-budget-160" if (RUN/"manifest-budget-160.json").exists() else "manifest"
    manifest=json.loads((RUN/f"{manifest_name}.json").read_text()); expected=(RUN/f"{manifest_name}.sha256").read_text().strip()
    raw=json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()
    if hashlib.sha256(raw).hexdigest()!=expected: raise SystemExit("manifest hash mismatch")
    wanted={(task,trial,arm) for task in manifest["evaluation"]["task_ids"] for trial in manifest["evaluation"]["trial_ids"] for arm in ARMS}
    evidence=[]; records=[]
    for path in sorted((RUN/"evaluation").glob("*/*/trial-*.json")):
        row=json.loads(path.read_text()); key=(row.get("task_id"),row.get("trial_id"),row.get("arm"))
        if key not in wanted: raise SystemExit(f"unregistered evaluation artifact: {path}")
        row["artifact"]=str(path.relative_to(ROOT)); row["artifact_sha256"]=sha(path); records.append(row)
        evidence.append({"path":row["artifact"],"sha256":row["artifact_sha256"],"kind":"evaluation"})
    actual={(row["task_id"],row["trial_id"],row["arm"]) for row in records}
    expected_evaluation=len(wanted)
    if actual!=wanted or len(records)!=expected_evaluation: raise SystemExit(f"incomplete evaluation: {len(records)}/{expected_evaluation}")
    grouped=defaultdict(list); task_grouped=defaultdict(list)
    for row in records: grouped[row["arm"]].append(row); task_grouped[(row["task_id"],row["arm"])].append(row)
    metrics={}
    for arm in ARMS:
        arm_rows=grouped[arm]; tasks={task:task_grouped[(task,arm)] for task in manifest["evaluation"]["task_ids"]}
        scores=[float(row["after_score"]) for row in arm_rows]
        metrics[arm]={"trajectory_denominator":len(arm_rows),"task_denominator":len(tasks),"mean_official_score":mean(scores),
            "avg_at_4":mean([mean([float(x["after_score"]) for x in tasks[t]]) for t in tasks]),
            "pass_at_4":mean([float(any(float(x["after_score"])==1 for x in tasks[t])) for t in tasks]),
            "mean_actions":mean([float(x["actions"]) for x in arm_rows]),
            "full_success_rate":mean([float(x["after_score"]==1) for x in arm_rows])}
    lookup={(row["task_id"],row["trial_id"],row["arm"]):float(row["after_score"]) for row in records}
    paired={}
    for comparator in ["copromem_fixed","official_upstream_reme_dynamic","official_upstream_reme_fixed","no_memory"]:
        per_family=defaultdict(list); diffs=[]
        for task in manifest["evaluation"]["task_ids"]:
            values=[lookup[(task,trial,"copromem_dynamic")]-lookup[(task,trial,comparator)] for trial in manifest["evaluation"]["trial_ids"]]
            diffs.extend(values); per_family[task[:7]].extend(values)
        paired[comparator]={"complete_pair_denominator":len(diffs),"mean_difference":mean(diffs),"cluster_bootstrap_95_ci":cluster_ci(per_family),
            "wins":sum(x>0 for x in diffs),"losses":sum(x<0 for x in diffs),"ties":sum(x==0 for x in diffs)}
    progress=rows(RUN/"progress.jsonl"); calls=defaultdict(lambda:{"calls":0,"prompt_tokens":0,"completion_tokens":0,"reasoning_tokens":0,"latency_seconds":0.0,"cost_usd":0.0})
    for event in progress:
        if event.get("event") not in {"call_settled","embedding_settled"}:continue
        role=str(event.get("role","lifecycle")); arm=next((a for a in ARMS if a in role),"lifecycle_or_embedding")
        total=calls[arm]; total["calls"]+=1; total["prompt_tokens"]+=int(event.get("prompt_tokens") or event.get("input_tokens") or 0); total["completion_tokens"]+=int(event.get("completion_tokens") or 0); total["reasoning_tokens"]+=int(event.get("reasoning_tokens") or 0); total["latency_seconds"]+=float(event.get("latency") or 0); total["cost_usd"]+=float(event.get("cost") or 0)
    ledger_rows=rows(RUN/"ledger.jsonl"); exposure={}
    for row in ledger_rows:
        if row.get("event") in {"reserve","settle"}:exposure[row["id"]]=float(row["usd"])
    acquisition=list((RUN/"acquisition").glob("*.json"));
    expected_new_acquisition=len(manifest["acquisition"].get("new_task_ids", manifest["acquisition"].get("task_ids", [])))
    if len(acquisition)!=expected_new_acquisition: raise SystemExit(f"incomplete acquisition: {len(acquisition)}/{expected_new_acquisition}")
    evidence += [{"path":str((RUN/f"{manifest_name}.json").relative_to(ROOT)),"sha256":sha(RUN/f"{manifest_name}.json"),"kind":"manifest"},{"path":str((RUN/"progress.jsonl").relative_to(ROOT)),"sha256":sha(RUN/"progress.jsonl"),"kind":"progress"},{"path":str((RUN/"ledger.jsonl").relative_to(ROOT)),"sha256":sha(RUN/"ledger.jsonl"),"kind":"ledger"}]
    carry=int(manifest.get("acquisition",{}).get("carry_forward_v1_count",0)); cap=float(manifest["budget"]["hard_cap_usd"])
    report={"protocol":manifest["protocol"],"label":"exploratory exact-ID custody; corrected fixed/dynamic faithful adaptation","manifest_sha256":expected,"completion":{"acquisition":f"{carry + len(acquisition)}/{carry + expected_new_acquisition}","evaluation":f"{len(records)}/{expected_evaluation}","complete":True},"metrics":metrics,"paired_copromem_dynamic":paired,"official_scores":records,"calls_tokens_latency_cost":dict(calls),"ledger":{"hard_cap_usd":cap,"charged_or_retained_usd":sum(exposure.values()),"records":len(ledger_rows)},"evidence":evidence,"limitations":["Exact-ID custody only; no task-family or benchmark-wide claim.","Official upstream ReMe service/executor is used through OpenRouter compatibility boundaries; embedding model is the amended Azure OpenRouter text-embedding-3-small route.","This pilot does not support superiority without the preregistered beneficial-flip and compute-parity conditions."],"decision":"REVISE"}
    out=RUN/"final-report.json"; md=RUN/"FINAL_REPORT.md"; out.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    lines=["# Corrected fixed/dynamic AppWorld pilot","","**Exploratory exact-ID custody; faithful ReMe adaptation.**","",f"Manifest SHA-256: `{expected}`","", "| Arm | Avg@4 | Pass@4 | mean score | success rate | actions |","|---|---:|---:|---:|---:|---:|"]
    for arm in ARMS:
        metric=metrics[arm]; lines.append(f"| {arm} | {metric['avg_at_4']:.4f} | {metric['pass_at_4']:.4f} | {metric['mean_official_score']:.4f} | {metric['full_success_rate']:.4f} | {metric['mean_actions']:.2f} |")
    lines += ["","## Paired CoProMem Dynamic comparisons","","| Comparator | pairs | mean difference | 95% cluster CI | W/L/T |","|---|---:|---:|---:|---:|"]
    for arm,result in paired.items(): lines.append(f"| {arm} | {result['complete_pair_denominator']} | {result['mean_difference']:.4f} | {result['cluster_bootstrap_95_ci']} | {result['wins']}/{result['losses']}/{result['ties']} |")
    lines += ["",f"Ledger exposure: **USD {sum(exposure.values()):.6f} / USD {cap:.2f}**.","","## Limitations","",*[f"- {x}" for x in report["limitations"]],"","**REVISE:** interpret only after the preregistered beneficial-flip and compute-parity review."]
    md.write_text("\n".join(lines)+"\n")
    print(f"corrected_report=passed rows={len(records)}")
if __name__=="__main__":main()
