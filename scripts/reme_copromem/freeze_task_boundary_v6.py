"""Freeze task-boundary 006 only after its fresh CoProMem state exists."""
from __future__ import annotations
import argparse, hashlib, json, pathlib, subprocess
from copromem.experiments.reme_copromem.runner import digest, write_json

ROOT = pathlib.Path(__file__).resolve().parents[2]
def sha(path: pathlib.Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument('--run', type=pathlib.Path, required=True); args=parser.parse_args(); run=args.run
    if (run/'manifest.json').exists(): raise FileExistsError('006 already frozen')
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=no','--','src','scripts'],cwd=ROOT,text=True).strip(): raise RuntimeError('commit runtime source before freezing')
    value=json.loads((run/'template.json').read_text(encoding='utf-8')); state=json.loads((run/'copromem/initial-state.json').read_text(encoding='utf-8'))
    value['acquisition']['fresh_initial_bank_sha256']=digest(state); value['git_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(); value['status']='frozen_pre_payload'
    payload=json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2).encode()+b'\n'; (run/'manifest.json').write_bytes(payload); (run/'manifest.sha256').write_text(hashlib.sha256(payload).hexdigest()+'\n',encoding='utf-8')
    print(run/'manifest.json')
if __name__=='__main__': main()
