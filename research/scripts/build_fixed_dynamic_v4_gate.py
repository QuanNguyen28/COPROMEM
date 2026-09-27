#!/usr/bin/env python3
"""Zero-provider v4 CoProMem acquisition rebuild and retrieval gate."""
from __future__ import annotations
import hashlib, json, pathlib
from src.copromem.appworld_comparison_adapter import CoProMemAppWorldAdapter, TrialInput
from scripts.run_corrected_fixed_dynamic_v2 import frozen_v3_acquisition_pool

ROOT=pathlib.Path('/mnt/e/Project/AAMAS/COPROMEM')
RUN=ROOT/'artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v4'
def digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def write(p,v): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n')
def main():
    rows=frozen_v3_acquisition_pool()
    if len(rows)!=32: raise RuntimeError('immutable acquisition pool is incomplete')
    from research.official_pilot.five_arm_runner import raw_acquisition_trajectories
    adapter=CoProMemAppWorldAdapter(api_key='',model='deepseek/deepseek-v4.1-flash',provider_only='deepseek',reasoning_effort='none')
    raw=raw_acquisition_trajectories(rows)
    for item in raw: adapter.ingest(item)
    adapter.consolidate()
    state=adapter.export_state(); bank_hash=digest(state)
    write(RUN/'copromem'/'initial-state.json',state)
    write(RUN/'copromem'/'acquisition-provenance.json',{'source_count':32,'source_artifact_hashes':sorted(str(r['source_artifact_sha256']) for r in rows),'semantic_state_sha256':bank_hash})
    clones={'fixed':state,**{f'dynamic-trial-{i}':state for i in range(1,5)}}
    clone_hashes={name:digest(value) for name,value in clones.items()}
    if set(clone_hashes.values())!={bank_hash}: raise RuntimeError('initial clone mismatch')
    records=[]
    # distinct acquisition families, no evaluation payloads.
    picked={}
    for row in rows: picked.setdefault(str(row['task_id'])[:7],row)
    for index,(family,row) in enumerate(list(picked.items())[:8],1):
        trial=TrialInput(str(row['task_id']),str(row['instruction']),'appworld',base_prompt=str(row['instruction']))
        before=adapter.semantic_state_hash(); guidance,prov=adapter.retrieve_with_provenance(trial,index)
        reproduced=CoProMemAppWorldAdapter.reproduce_retrieval(state,prov['task_input'],prov)
        records.append({'family':family,'task_id':row['task_id'],'pre_state_sha256':before,'post_state_sha256':adapter.semantic_state_hash(),'guidance_sha256':prov['guidance_sha256'],'fallback_category':prov['fallback_category'],'reproduced':guidance==reproduced,'provenance':prov})
    learned=[r for r in records if r['fallback_category']=='learned_or_structural']
    passed=(all(r['reproduced'] and r['pre_state_sha256']==r['post_state_sha256']==bank_hash for r in records)
            and len({r['family'] for r in learned})>=2 and len({r['guidance_sha256'] for r in learned})>=2)
    gate={'protocol':'fixed_dynamic_v4','provider_calls':0,'passed':passed,'bank_sha256':bank_hash,'clone_hashes':clone_hashes,'records':records,
          'learned_family_count':len({r['family'] for r in learned}),'distinct_learned_guidance_hashes':len({r['guidance_sha256'] for r in learned})}
    write(RUN/'copromem'/'acquisition-retrieval-gate.json',gate)
    print(json.dumps({'passed':passed,'bank_sha256':bank_hash,'learned_families':gate['learned_family_count'],'distinct_hashes':gate['distinct_learned_guidance_hashes']}))
if __name__=='__main__': main()
