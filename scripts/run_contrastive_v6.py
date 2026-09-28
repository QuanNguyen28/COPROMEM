#!/usr/bin/env python3
"""Prepare, freeze, preflight, and run the isolated v6 A→B engineering probe.

The prepare command reads only the pre-existing public train inventory.  It
does not construct an AppWorld task or contact any provider.  The run command
is deliberately separate and is the only command allowed to invoke the shared
executor boundary after a manifest is frozen.
"""
from __future__ import annotations
import argparse, hashlib, json, os, pathlib, re, subprocess, sys, time
from collections import defaultdict
from typing import Any

from copromem.contrastive_graph_v6 import POLICY_VERSION, digest
from copromem.experiments.reme_copromem.contrastive_v6_dispatcher import ContrastiveV6Dispatcher, SharedTrajectoryExecutor
from copromem.experiments.reme_copromem.contrastive_v6_runner import fresh_state
from copromem.experiments.reme_copromem.runner import AppendOnlyLedger, execute_trajectory, write_json

ROOT=pathlib.Path(__file__).resolve().parents[1]
INVENTORY=ROOT/'artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v5_train_inventory_001/train-public-inventory.json'
REGISTRY=ROOT/'research/reme_copromem_fixed_dynamic_review/appworld_public_tool_schema_registry_v5_3.json'
ID=re.compile(r'\b[a-f0-9]{7}_[0-9]+\b')

def sha(path:pathlib.Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def git()->str:
 env=dict(os.environ)
 pointer=ROOT/'.git'
 if pointer.is_file():
  match=re.match(r'gitdir:\s*([A-Za-z]):/(.+)',pointer.read_text(encoding='utf-8').strip())
  if match:
   env['GIT_DIR']=f"/mnt/{match.group(1).lower()}/{match.group(2)}";env['GIT_WORK_TREE']=str(ROOT)
 return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,env=env).strip()
def canonical(v:Any)->str:return digest(v)
def append(path:pathlib.Path,row:dict[str,Any])->None:
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('a',encoding='utf-8') as h:h.write(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n');h.flush();os.fsync(h.fileno())
def c_free_gib()->float:
 s=os.statvfs('/mnt/c');return s.f_bavail*s.f_frsize/1024**3
def _norm(text:str)->str:
 return re.sub(r'\b\d+\b|"[^"]*"|\'[^\']*\'','<value>',text.lower()).strip()
def executed_ids()->set[str]:
 result=set()
 for p in (ROOT/'artifacts').glob('**/evaluation/*/*/trial-*.json'):
  try: result.add(str(json.loads(p.read_text(encoding='utf-8')).get('task_id') or ''))
  except (OSError,json.JSONDecodeError): pass
 return result-{''}
def _registry()->dict[str,Any]:
 raw=json.loads(REGISTRY.read_text(encoding='utf-8'))
 # The public callable registry contains extra v5 metadata; v6 consumes only
 # the operation fields it needs and content-addresses this projection.
 ops=[]
 for item in raw.get('operations',[]):
  op=str(item.get('operation',''))
  if op:ops.append({'operation':op,'app':item.get('app'),'function_name':item.get('function_name'),
                    'access_mode':item.get('access_mode','read'),'required_parameters':item.get('required_parameters',[]),
                    'output_slots':item.get('output_slots',[])})
 value={'operations':sorted(ops,key=lambda x:x['operation']),'dependency_edges':raw.get('dependency_edges',[])}
 value['registry_sha256']=digest(value);return value
def select()->tuple[dict[str,Any]|None,list[dict[str,Any]],dict[str,Any]]:
 inv=json.loads(INVENTORY.read_text(encoding='utf-8')); excluded=executed_ids(); rows=inv['unseen_train_tasks']
 groups=defaultdict(list)
 for row in rows:
  task=str(row['task_id'])
  if task not in excluded: groups[(task.rsplit('_',1)[0],_norm(str(row['instruction'])))].append(row)
 candidates=[]
 for (family,template),values in groups.items():
  for i,a in enumerate(sorted(values,key=lambda x:x['task_id'])):
   for b in sorted(values,key=lambda x:x['task_id'])[i+1:]:
    apps=sorted({name for name in ('amazon','file_system','gmail','phone','simple_note','spotify','splitwise','todoist','venmo') if name.replace('_',' ') in template or name in template})
    # The public descriptor may request only one application. Its query set is
    # therefore the complete public callable set for those named applications,
    # never a post-execution operation guess.
    descriptor={'family':family,'public_instruction_template':template,'public_apps':apps,'public_callable_set_sha256':sha(REGISTRY)}
    candidates.append({'a_task_id':a['task_id'],'b_task_id':b['task_id'],'family':family,'descriptor':descriptor,'descriptor_sha256':digest(descriptor)})
 candidates.sort(key=lambda x:(x['descriptor_sha256'],x['a_task_id'],x['b_task_id']))
 return (candidates[0] if candidates else None),candidates,{'inventory_count':len(rows),'executed_exclusion_count':len(excluded),'executed_exclusion_sha256':digest(sorted(excluded))}
def prepare(run:pathlib.Path)->None:
 if run.exists() and any(run.iterdir()):raise RuntimeError('run directory is not empty')
 pair,candidates,audit=select();run.mkdir(parents=True)
 record={'provider_calls':0,'payloads_opened':False,'test_normal_used':False,'selection_state':'selected' if pair else 'no_eligible_pair',
         'candidate_list_sha256':digest(candidates),'candidate_count':len(candidates),'ordering_rule':'(descriptor_sha256, a_task_id, b_task_id)',**audit}
 write_json(run/'allocation-audit.json',record)
 if not pair:raise RuntimeError('no fresh public-train sibling pair')
 registry=_registry(); initial=fresh_state(); limits={'executor':240,'reme_lifecycle':0,'reme_embedding':0,'copromem_decomposition':0}
 # Executor upper bound: 32,768 input at $0.30/M + 2,048 output at $1.20/M.
 per_call=32768*.30/1_000_000+2048*1.20/1_000_000; dispatch=limits['executor']*per_call; all_in=dispatch*1.15
 if all_in>100:raise RuntimeError('registered v6 bound exceeds USD 100')
 template={'protocol':'v6_engineering_001_contrastive_graph','engineering_only_exposed':True,'git_commit':git(),
  'arms':['no_memory','copromem_v6_dynamic'],'execution':{'max_actions':30,'temperature':.7,'top_p':1.0,'c_floor_gib':10.0,
  'model':'deepseek/deepseek-v4.1-flash','provider':'deepseek','fallbacks':False,'reasoning_effort':'none','stream':False,'completion_token_ceiling':2048},
  'evaluation':{'split':'train','task_ids':[pair['a_task_id'],pair['b_task_id']],'a_task_id':pair['a_task_id'],'b_task_id':pair['b_task_id'],
  'trial_ids':[1,2],'seeds':[9601,9602],'expected_trajectories':8,'descriptor':pair['descriptor'],'descriptor_sha256':pair['descriptor_sha256']},
  'initial_state':initial,'initial_state_sha256':digest(initial),'registry':registry,'policy_version':POLICY_VERSION,
  'selection':{**record,'selected':pair},'budget':{'hard_cap_usd':100.0,'call_limits':limits,'dispatchable_usd':dispatch,'contingency_usd':dispatch*.15,'all_in_usd':all_in}}
 write_json(run/'template.json',template)
def freeze(run:pathlib.Path)->None:
 template=run/'template.json';value=json.loads(template.read_text(encoding='utf-8'))
 if value['git_commit']!=git():raise RuntimeError('source changed after allocation')
 if (run/'manifest.json').exists():raise RuntimeError('manifest already frozen')
 write_json(run/'manifest.json',value);(run/'manifest.sha256').write_text(sha(run/'manifest.json')+'\n',encoding='utf-8')
def _cred()->str:
 value=os.environ.get('OPENROUTER_API_KEY','').strip()
 if value:return value
 for line in (ROOT/'.env').read_text(encoding='utf-8').splitlines():
  if line.startswith('OPENROUTER_API_KEY=') and line.split('=',1)[1].strip():return line.split('=',1)[1].strip().strip('"\'')
 raise RuntimeError('OPENROUTER_API_KEY is unavailable')
def _load(run:pathlib.Path)->dict[str,Any]:
 if sha(run/'manifest.json')!=(run/'manifest.sha256').read_text().strip():raise RuntimeError('manifest hash mismatch')
 value=json.loads((run/'manifest.json').read_text())
 if value['git_commit']!=git():raise RuntimeError('frozen source mismatch')
 if c_free_gib()<value['execution']['c_floor_gib']:raise RuntimeError('C-drive floor breached')
 if value['budget']['all_in_usd']>100:raise RuntimeError('budget cap breached')
 return value
def run(run:pathlib.Path,preflight:bool=False)->None:
 value=_load(run);status=run/'runner-status.json';progress=run/'progress.jsonl';write_json(status,{'state':'preflight_passed','pid':os.getpid(),'manifest_sha256':sha(run/'manifest.json')})
 if preflight:return
 lock=run/'runner.lock'
 if lock.exists():raise RuntimeError('runner lock exists')
 write_json(lock,{'pid':os.getpid()});ledger=AppendOnlyLedger(run/'ledger.jsonl',100.,value['budget']['call_limits']);key=_cred()
 registry=value['registry'];dispatcher=ContrastiveV6Dispatcher(run,registry,SharedTrajectoryExecutor(run,progress,ledger,key,value['evaluation']['task_ids'],30,.7,{'registry_sha256':registry['registry_sha256']}),policy_sha256=digest({'policy':POLICY_VERSION,'registry':registry['registry_sha256']}))
 a,b=value['evaluation']['task_ids']; apps=set(value['evaluation']['descriptor']['public_apps'])
 query=[x['operation'] for x in registry['operations'] if x.get('app') in apps]
 if not query:raise RuntimeError('public descriptor has no callable retrieval query')
 def no_memory(task:str,trial:int,seed:int)->None:
  target=run/'no-memory'/task/f'trial-{trial}.json'
  if not target.exists():execute_trajectory(run=run,progress=progress,ledger=ledger,api_key=key,all_task_ids=[a,b],arm='no_memory',task_id=task,trial_id=trial,seed=seed,max_actions=30,temperature=.7,phase='evaluation',artifact_path=target,execution_evidence={'registry_sha256':registry['registry_sha256']})
 def task(task:str,state:dict[str,Any])->tuple[dict[str,Any],dict[str,Any]]:
  for trial,seed in zip(value['evaluation']['trial_ids'],value['evaluation']['seeds']):no_memory(task,trial,seed)
  return dispatcher.execute_batch(task,state,[query,query],[{'arm':'copromem_v6_dynamic','trial':t,'seed':s} for t,s in zip(value['evaluation']['trial_ids'],value['evaluation']['seeds'])])
 post,marker=task(a,value['initial_state'])
 if marker['state']!='committed':write_json(status,{'state':'terminal_no_go_a','marker':marker});return
 dispatcher.authorize_b(a,b);post_b,marker_b=task(b,post);dispatcher.finalize(b,terminal_artifact_hashes=[])
 write_json(status,{'state':'completed','a_schema':marker['winner_schema_id'],'b_marker':marker_b,'manifest_sha256':sha(run/'manifest.json')})
def main()->None:
 p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','freeze','preflight','run']);p.add_argument('--run',required=True,type=pathlib.Path);a=p.parse_args()
 {'prepare':prepare,'freeze':freeze}.get(a.command,lambda _:run(a.run,a.command=='preflight'))(a.run)
if __name__=='__main__':main()
