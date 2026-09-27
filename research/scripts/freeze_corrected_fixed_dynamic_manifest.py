#!/usr/bin/env python3
"""Freeze ID-only custody allocation before any evaluation payload is opened."""
from __future__ import annotations
import hashlib,json,pathlib
ROOT=pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM"); OUT=ROOT/"artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v1"
ACQ=["22cc237_1","22cc237_2","27e1026_1","27e1026_2","287e338_1","287e338_2","29caf6f_1","29caf6f_2","2a163ab_1","2a163ab_2","302c169_1","302c169_2"]
EVAL=["3aa1a22_1","2d9f728_1","a30375d_1","f323bae_1","ff58e36_1","325d6ec_1","bde252e_1","32616b5_1","b9c5c9a_1","ffe6d5e_1","0a9d82a_1","522e5e5_1","90adc3f_1","f861c32_1","9dabbc9_1","fd1f8fa_1"]
def main():
  if len({x[:7] for x in EVAL})!=16 or len({x[:7] for x in ACQ})<6:raise SystemExit("family allocation invariant")
  obj={"protocol":"corrected_fixed_dynamic_appworld_v1","label":"exploratory exact-ID custody; faithful ReMe adaptation","git_commit":"abc3fb0e83e9b1ca45cfa362c21be10bbec11a38","acquisition":{"split":"train","task_ids":ACQ,"trajectories_per_task":2,"seeds":[7201,7202]},"evaluation":{"split":"test_normal","task_ids":EVAL,"trial_ids":[1,2,3,4]},"arms":["no_memory","official_upstream_reme_fixed","official_upstream_reme_dynamic","copromem_fixed","copromem_dynamic"],"limits":{"actions":30,"input_tokens":32768,"completion_tokens":2048,"temperature":0.7,"top_p":1.0},"route":{"model":"deepseek/deepseek-v4.1-flash","provider_only":"deepseek","fallbacks":False,"reasoning_effort":"none","stream":False},"embedding":{"model":"openai/text-embedding-3-small","provider_only":"azure","dimensions":1024},"budget":{"hard_cap_usd":140.0,"registered_conservative_usd":131.991797},"custody":{"exact_id_clean":True,"family_clean_where_inventory_permitted":True,"claim":"exploratory exact-ID custody only"}}
  raw=json.dumps(obj,sort_keys=True,separators=(",",":")).encode(); OUT.mkdir(parents=True,exist_ok=True); (OUT/"manifest.json").write_bytes(raw); (OUT/"manifest.sha256").write_text(hashlib.sha256(raw).hexdigest()+"\n")
  print((OUT/"manifest.sha256").read_text().strip())
if __name__=="__main__":main()
