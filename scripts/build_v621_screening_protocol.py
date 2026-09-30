#!/usr/bin/env python3
"""Freeze the public-ID-only v6.2.1 descriptor-screening candidate pool."""
from __future__ import annotations
import argparse, hashlib, json, pathlib, subprocess, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]; sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from copromem.experiments.reme_copromem.v61_custody import classify, digest

def sha(path: pathlib.Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def main() -> None:
 p=argparse.ArgumentParser(); p.add_argument('--out',required=True,type=pathlib.Path); a=p.parse_args()
 inv=ROOT/'research/reme_copromem_fixed_dynamic_review/v62-medium-public-test-normal-inventory.json'
 policy=ROOT/'research/reme_copromem_fixed_dynamic_review/copromem_v621_task_conditioned_retrieval_policy.json'
 registry=ROOT/'research/reme_copromem_fixed_dynamic_review/appworld_public_tool_schema_registry_v5_3.json'
 ids=set(json.loads(inv.read_text(encoding='utf-8'))['task_ids']); custody=classify(ROOT,inv,include_research=False,candidate_ids=ids)
 excluded=set(custody['hard_exclusion'])|set(custody['ambiguous_exclusion']); candidates=sorted(ids-excluded)
 result={'version':'v6.2.1-engineering-descriptor-screening-protocol-v1','stage':'A_pre_descriptor_access','split':'test_normal','payloads_opened':False,'provider_calls':0,
  'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
  'inventory_sha256':sha(inv),'method_policy_sha256':sha(policy),'registry_sha256':json.loads(registry.read_text())['registry_sha256'],
  'descriptor_extractor_sha256':sha(ROOT/'src/copromem/experiments/reme_copromem/descriptor_screening_v621.py'),
  'compatibility_classifier_sha256':sha(ROOT/'src/copromem/experiments/reme_copromem/task_conditioned_retrieval_v621.py'),
  'descriptor_schema':['task_id','instruction_sha256','instruction_feature_sha256','public_apps','canonical_public_operation_candidates','terminal_effect_class','descriptor_sha256','compatibility_class','compatible_schema_ids','candidate_features','registry_sha256','screening_sha256'],
  'hard_exclusion_set_sha256':digest(sorted(custody['hard_exclusion'])),'ambiguous_exclusion_set_sha256':digest(sorted(custody['ambiguous_exclusion'])),
  'candidate_count':len(candidates),'ordered_candidate_list_sha256':digest(candidates),'ordered_candidate_ids':candidates,
  'selection_rule':'scan canonical task_id order; first two compatible; first subsequent incompatible; no replacement'}
 a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
