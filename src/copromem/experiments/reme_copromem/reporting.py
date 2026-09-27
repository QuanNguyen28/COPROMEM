#!/usr/bin/env python3
"""Sanitized, read-only final report for the frozen v4 pilot."""
from __future__ import annotations
import hashlib, json, pathlib
from collections import defaultdict

ROOT=pathlib.Path('/mnt/e/Project/AAMAS/COPROMEM')
RUN=ROOT/'artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v4'

def write(path, value):
    path.parent.mkdir(parents=True,exist_ok=True); temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(value,encoding='utf-8'); temp.replace(path)

def main():
    manifest=json.loads((RUN/'manifest.json').read_text())
    mhash=hashlib.sha256((RUN/'manifest.json').read_bytes()).hexdigest()
    if mhash != (RUN/'manifest.sha256').read_text().strip(): raise SystemExit('manifest hash mismatch')
    arms=manifest['arms']; tasks=manifest['evaluation']['task_ids']; trials=manifest['evaluation']['trial_ids']
    wanted={(a,t,r) for a in arms for t in tasks for r in trials}; rows=[]
    for p in (RUN/'evaluation').glob('*/*/trial-*.json'):
        x=json.loads(p.read_text()); key=(x.get('arm'),x.get('task_id'),x.get('trial_id'))
        if key not in wanted: raise SystemExit('unregistered artifact')
        rows.append({'arm':key[0],'task_id':key[1],'trial_id':key[2],'after_score':float(x['after_score']),
                     'actions':int(x['actions']),'termination':x.get('termination'),'artifact_sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    actual={(x['arm'],x['task_id'],x['trial_id']) for x in rows}
    if actual != wanted or len(rows) != len(wanted): raise SystemExit(f'incomplete evaluation: {len(rows)}/{len(wanted)}')
    metrics={}; lookup={(x['arm'],x['task_id'],x['trial_id']):x['after_score'] for x in rows}
    for arm in arms:
        selected=[x for x in rows if x['arm']==arm]
        per_task=[[lookup[(arm,t,r)] for r in trials] for t in tasks]
        metrics[arm]={'trajectory_denominator':len(selected),'task_denominator':len(tasks),
            'avg_at_4':sum(sum(v)/4 for v in per_task)/len(per_task),
            'pass_at_4':sum(any(v==1 for v in group) for group in per_task)/len(per_task),
            'mean_actions':sum(x['actions'] for x in selected)/len(selected)}
    paired={}
    for other in ['no_memory','official_upstream_reme_fixed','official_upstream_reme_dynamic','copromem_fixed']:
        diffs=[lookup[('copromem_dynamic',t,r)]-lookup[(other,t,r)] for t in tasks for r in trials]
        paired[other]={'denominator':len(diffs),'mean_difference':sum(diffs)/len(diffs),
                       'wins':sum(x>0 for x in diffs),'losses':sum(x<0 for x in diffs),'ties':sum(x==0 for x in diffs)}
    report={'protocol':'corrected_fixed_dynamic_v4','label':'exploratory faithful adaptation; exact-ID holdout only',
            'manifest_sha256':mhash,'completion':{'evaluation':f'{len(rows)}/{len(wanted)}','complete':True},
            'metrics':metrics,'paired_copromem_dynamic':paired,'official_scores':rows,
            'limitations':['Not an exact ReMe reproduction.','No task-family or benchmark-wide generalization claim.','v3 evaluation results excluded.']}
    write(RUN/'final-report.json',json.dumps(report,sort_keys=True,indent=2)+'\n')
    lines=['# Corrected fixed-dynamic v4 pilot','',f'Manifest SHA-256: `{mhash}`','',
           '**Exploratory faithful adaptation; exact-ID holdout only.**','', '| Arm | Avg@4 | Pass@4 | mean actions |','|---|---:|---:|---:|']
    for arm in arms: lines.append(f"| {arm} | {metrics[arm]['avg_at_4']:.4f} | {metrics[arm]['pass_at_4']:.4f} | {metrics[arm]['mean_actions']:.2f} |")
    lines += ['', '## Paired CoProMem Dynamic comparisons','', '| Comparator | pairs | mean difference | W/L/T |','|---|---:|---:|---:|']
    for arm,x in paired.items(): lines.append(f"| {arm} | {x['denominator']} | {x['mean_difference']:.4f} | {x['wins']}/{x['losses']}/{x['ties']} |")
    lines += ['', '## Limitations','']+[f'- {x}' for x in report['limitations']]
    write(RUN/'FINAL_REPORT.md','\n'.join(lines)+'\n')

if __name__=='__main__': main()
