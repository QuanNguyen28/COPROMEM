from pathlib import Path
import pytest
from copromem.experiments.reme_copromem.contrastive_v6_dispatcher import ContrastiveV6Dispatcher
from copromem.contrastive_graph_v6 import digest

def _registry(): return {"registry_sha256":"r","operations":[{"operation":"apis.x.read","app":"x","function_name":"read","access_mode":"read","required_parameters":[],"output_slots":[]},{"operation":"apis.x.write","app":"x","function_name":"write","access_mode":"write","required_parameters":[],"output_slots":[]}],"dependency_edges":[]}
def test_dispatcher_has_no_v53_lifecycle_import():
 import inspect, copromem.experiments.reme_copromem.contrastive_v6_dispatcher as m
 assert "task_boundary" not in inspect.getsource(m)
def test_same_task_retrievals_share_pre_state_and_reuse(tmp_path):
 d=ContrastiveV6Dispatcher(tmp_path,_registry(),lambda **_: {},policy_sha256="p")
 r=d.prepare("A",{},[["apis.x.write"],["apis.x.write"]])
 assert len(r)==2 and r[0]["pre_state_sha256"]==r[1]["pre_state_sha256"]==digest({})

def _plan(**_):
 return ({"plan_sha256":"plan","schema_id":"schema_A"},{"graph_hashes":["g1","g2"]})
def _validate(_): return {"passed":True,"reason":None,"plan_sha256":"plan"}
def _commit(state, plan):
 post={**state,"contrastive_v6_schemas":{"schema_A":{"required_operations":["apis.x.write"]}}}
 return post,{"state":"committed","winner_schema_id":"schema_A","validation":_validate(plan),"before_state_sha256":digest(state),"after_state_sha256":digest(post)}
def test_complete_batch_is_durable_and_restart_does_not_repeat_executor(tmp_path):
 calls=[]
 def executor(**kwargs):
  calls.append(kwargs["trial"]); return {"arm":kwargs["arm"],"trial":kwargs["trial"],"after_score":1.0,"evidence_path":"fixture"}
 d=ContrastiveV6Dispatcher(tmp_path,_registry(),executor,policy_sha256="p",planner=_plan,validator=_validate,committer=_commit)
 trials=[{"arm":"copromem_v6_dynamic","trial":1},{"arm":"copromem_v6_dynamic","trial":2}]
 post,marker=d.execute_batch("A",{},[["apis.x.write"],["apis.x.write"]],trials)
 assert marker["state"]=="committed" and calls==[1,2]
 assert d.reconcile("A",{},ledger_reconciled=True)=="complete"
 d.execute_batch("A",{},[["apis.x.write"],["apis.x.write"]],trials)
 assert calls==[1,2]
 for transition in ("initialized","task_pre_state_frozen","retrievals_materialized","trajectories_complete","batch_ready","plan_persisted","validation_persisted","commit_persisted","next_task_authorized"):
  assert (tmp_path/"state-machine"/"A"/f"{transition}.json").exists()
def test_unsettled_or_state_mismatch_fails_closed(tmp_path):
 d=ContrastiveV6Dispatcher(tmp_path,_registry(),lambda **_: {},policy_sha256="p")
 d.prepare("A",{},[["apis.x.write"],["apis.x.write"]])
 with pytest.raises(ValueError,match="unsettled"): d.reconcile("A",{},ledger_reconciled=False)
 with pytest.raises(ValueError,match="pre-state"): d.reconcile("A",{"x":1},ledger_reconciled=True)
def test_transition_records_are_immutable(tmp_path):
 d=ContrastiveV6Dispatcher(tmp_path,_registry(),lambda **_: {},policy_sha256="p")
 d._record("A","initialized",x=1)
 with pytest.raises(ValueError,match="immutable"): d._record("A","initialized",x=2)
def test_b_is_blocked_after_a_rejection_and_authorized_after_commit(tmp_path):
 d=ContrastiveV6Dispatcher(tmp_path,_registry(),lambda **_: {},policy_sha256="p",planner=_plan,validator=_validate,committer=_commit)
 with pytest.raises(ValueError,match="unopened"): d.authorize_b("A","B")
 d._record("A","commit_persisted",marker=_commit({},_plan()[0])[1],post_state=_commit({},_plan()[0])[0],post_state_sha256=digest(_commit({},_plan()[0])[0]))
 auth=d.authorize_b("A","B")
 assert auth["authorized_from_task"]=="A" and auth["selected_schema_id"]=="schema_A"
 assert d.finalize("A",terminal_artifact_hashes=["a1"])["reconciliation"]=="complete"
