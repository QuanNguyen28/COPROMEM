#!/usr/bin/env python3
"""Sanitized zero-cost audit of a legacy ReMe dump/load/dump round trip."""
from __future__ import annotations
import hashlib, json, pathlib
from collections import Counter
from typing import Any

ROOT=pathlib.Path('/mnt/e/Project/AAMAS/COPROMEM')
RUN=ROOT/'artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v3'

def rows(path: pathlib.Path) -> list[dict[str,Any]]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]
def h(x: Any) -> str:
    return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def value_kind(x: Any) -> str:
    if isinstance(x,dict): return 'object:' + ','.join(sorted(x))
    if isinstance(x,list): return f'array:{len(x)}'
    return type(x).__name__

def main() -> None:
    source=rows(RUN/'reme/shared-bank.jsonl'); clone=rows(RUN/'reme/shared-bank.clone-check.jsonl')
    by_id={str(x.get('memory_id')):x for x in source}; clone_by_id={str(x.get('memory_id')):x for x in clone}
    shared=sorted(set(by_id)&set(clone_by_id)); changed=Counter(); shapes=Counter(); vector_deltas=[]
    for key in shared:
        left,right=by_id[key],clone_by_id[key]
        for field in sorted(set(left)|set(right)):
            if left.get(field)!=right.get(field):
                changed[field]+=1; shapes[(field,value_kind(left.get(field)),value_kind(right.get(field)))]+=1
                if field == 'vector' and isinstance(left.get(field), list) and isinstance(right.get(field), list):
                    vector_deltas.extend(abs(float(a)-float(b)) for a,b in zip(left[field], right[field]))
    result={'source_rows':len(source),'clone_rows':len(clone),'source_id_set_sha256':h(sorted(by_id)),
            'clone_id_set_sha256':h(sorted(clone_by_id)),'common_ids':len(shared),
            'only_source_count':len(set(by_id)-set(clone_by_id)),'only_clone_count':len(set(clone_by_id)-set(by_id)),
            'changed_field_counts':dict(sorted(changed.items())),
            'changed_field_shape_counts':[{"field":field,"source":a,"clone":b,"count":n} for (field,a,b),n in sorted(shapes.items())],
            'vector_max_absolute_delta':max(vector_deltas,default=0.0), 'vector_nonzero_delta_count':sum(delta != 0.0 for delta in vector_deltas)}
    (RUN/'reme/clone-semantics-audit.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    print(json.dumps(result,sort_keys=True))
if __name__=='__main__': main()
