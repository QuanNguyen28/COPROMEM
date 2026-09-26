from copromem.appworld_comparison_adapter import AcquisitionIdentity, RawAcquisitionTrajectory, TrialInput
from copromem.appworld_live_smoke import ARMS, LOCKED_MODEL, LockedOpenRouterTransport, ModelOutcome, NativeAppWorldSmokeRunner, UnifiedSuccessorRunner
from copromem.checkpoints import RunStore
from copromem.successor_ledger import SuccessorLedger
from pathlib import Path
import json

def _parent(root):
    (root/"reservations").mkdir(parents=True)
    for i in range(10): (root/"reservations"/f"{i}.json").write_text(json.dumps({"reserved_usd": .003131748}))
    return root

def test_complete_zero_model_smoke_contract_and_restart(tmp_path):
    ledger = SuccessorLedger(RunStore(tmp_path/"next"), parent_root=_parent(tmp_path/"parent"))
    calls=[]
    def model_call(**kwargs):
        calls.append(kwargs)
        return ModelOutcome({"action":"fixture"}, 2, 1, .000001, .01, "tool_calls", LOCKED_MODEL, True)
    runner=NativeAppWorldSmokeRunner(ledger, model_call=model_call,
        native_execute=lambda task, output, limit: {"task":task,"output":output,"limit":limit},
        official_scorer=lambda task, native: task=="fac291d_1" and native["limit"]==10)
    acq=[RawAcquisitionTrajectory(AcquisitionIdentity("50e1ac9_1",0,0),"i","appworld",True),
         RawAcquisitionTrajectory(AcquisitionIdentity("50e1ac9_2",0,0),"i","appworld",False)]
    tools={"type":"function"}
    out=runner.run(acquisition=acq, trial=TrialInput("fac291d_1","i","appworld",base_prompt="P",tool_spec=tools),tools=tools,common_prompt="P")
    assert set(out["results"]) == set(ARMS) and len(calls)==4
    assert all(v["tools"] == tools and v["native"]["limit"] == 10 for v in out["results"].values())
    assert SuccessorLedger(RunStore(tmp_path/"next"), parent_root=tmp_path/"parent").attempts_used == 14

def test_locked_transport_has_only_locked_route_and_validates_native_tool():
    records=[]
    class Ledger:
        def reserve(self, key, amount, meta): records.append(("reserve", key, amount, meta))
        def settle(self, key, amount): records.append(("settle", key, amount))
    tool={"type":"function","function":{"name":"execute_python","parameters":{"type":"object","properties":{"code":{"type":"string"}},"required":["code"],"additionalProperties":False}}}
    def sender(body):
        assert body["model"] == LOCKED_MODEL and body["provider"] == {"only":["deepseek"],"allow_fallbacks":False,"require_parameters":True}
        assert body["reasoning_effort"] == "none" and body["stream"] is False and body["tool_choice"] == "auto" and body["max_tokens"] == 1024
        return {"model":LOCKED_MODEL,"provider":"DeepSeek","choices":[{"finish_reason":"tool_calls","message":{"tool_calls":[{"function":{"name":"execute_python","arguments":'{"code":"x=1"}'}}]}}],"usage":{"prompt_tokens":1,"completion_tokens":1,"cost":.000001,"completion_tokens_details":{"reasoning_tokens":0}}}
    t=LockedOpenRouterTransport(api_key="fixture",ledger=Ledger(),sender=sender)
    result=t.dispatch(key="a",metadata={"role":"executor"},prompt="p",tools=tool,upper_usd=.01)
    assert result.tool_valid and [r[0] for r in records] == ["reserve","settle"]

def test_locked_transport_rejects_multiple_or_wrong_named_native_calls():
    class Ledger:
        def reserve(self,*_): pass
        def settle(self,*_): pass
    tool={"type":"function","function":{"name":"execute_python","parameters":{"type":"object","properties":{"code":{"type":"string"}},"required":["code"],"additionalProperties":False}}}
    def sender(_):
        return {"model":LOCKED_MODEL,"provider":"DeepSeek","choices":[{"finish_reason":"tool_calls","message":{"tool_calls":[{"function":{"name":"wrong","arguments":'{"code":"x=1"}'}},{"function":{"name":"execute_python","arguments":'{"code":"x=2"}'}}]}}],"usage":{"prompt_tokens":1,"completion_tokens":1,"cost":.000001}}
    import pytest
    with pytest.raises(RuntimeError, match="fidelity gate"):
        LockedOpenRouterTransport(api_key="fixture",ledger=Ledger(),sender=sender).dispatch(key="bad",metadata={},prompt="p",tools=tool,upper_usd=.01)

def test_locked_transport_persists_latency_when_ledger_has_store(tmp_path):
    class Ledger:
        def __init__(self): self.store=RunStore(tmp_path)
        def reserve(self,*_): pass
        def settle(self,*_): pass
    tool={"type":"function","function":{"name":"execute_python","parameters":{"type":"object","required":["code"]}}}
    sender=lambda _: {"model":LOCKED_MODEL,"provider":"DeepSeek","choices":[{"finish_reason":"tool_calls","message":{"tool_calls":[{"function":{"name":"execute_python","arguments":'{"code":"x=1"}'}}]}}],"usage":{"prompt_tokens":1,"completion_tokens":1,"cost":.000001}}
    ledger=Ledger()
    LockedOpenRouterTransport(api_key="fixture",ledger=ledger,sender=sender).dispatch(key="latency",metadata={},prompt="p",tools=tool,upper_usd=.01)
    assert ledger.store.read("locked_transport", "latency")["latency_seconds"] >= 0

def test_unified_acquisition_journals_before_each_next_dispatch(tmp_path):
    class Ledger:
        def reserve(self,*a): pass
        def settle(self,*a): pass
    count=[0]
    def sender(_):
        count[0]+=1
        code="x=1" if count[0]==1 else "x=2"
        return {"model":LOCKED_MODEL,"provider":"DeepSeek","choices":[{"finish_reason":"tool_calls","message":{"tool_calls":[{"function":{"name":"execute_python","arguments":json.dumps({"code":code})}}]}}],"usage":{"prompt_tokens":1,"completion_tokens":1,"cost":.000001}}
    runner=UnifiedSuccessorRunner(store=RunStore(tmp_path), transport=LockedOpenRouterTransport(api_key="fixture",ledger=Ledger(),sender=sender),
        start_world=lambda task,phase:{"instruction":"fixture"}, act=lambda world,code:{"ok":True,"completed":code=="x=2"}, finish=lambda world:{"success":True}, tools={"type":"function","function":{"name":"execute_python","parameters":{"type":"object","required":["code"]}}}, base_system_prompt="P")
    out=runner.run_acquisition({"acquisition":{"task_ids":["abc1234_1"],"seeds":[7]}})
    assert out[0]["official_score"]["success"] and len(list((tmp_path/"acquisition_actions").glob("*.json"))) == 2

def test_unified_manifest_gate_prevents_evaluation_on_insufficient_acquisition(tmp_path):
    class Ledger:
        def reserve(self,*a): pass
        def settle(self,*a): pass
    def sender(_):
        return {"model":LOCKED_MODEL,"provider":"DeepSeek","choices":[{"finish_reason":"tool_calls","message":{"tool_calls":[{"function":{"name":"execute_python","arguments":'{"code":"x=1"}'}}]}}],"usage":{"prompt_tokens":1,"completion_tokens":1,"cost":.000001}}
    runner=UnifiedSuccessorRunner(store=RunStore(tmp_path), transport=LockedOpenRouterTransport(api_key="fixture",ledger=Ledger(),sender=sender), start_world=lambda *_:{"instruction":"x"}, act=lambda *_:{"ok":True,"completed":True}, finish=lambda _:{"success":False}, tools={"type":"function","function":{"name":"execute_python","parameters":{"type":"object","required":["code"]}}}, base_system_prompt="P")
    out=runner.run_manifest({"acquisition":{"task_ids":["abc1234_1"],"seeds":[1]},"evaluation":{"task_ids":["def5678_1"],"seeds":[2]}}, lambda *_: (_ for _ in ()).throw(AssertionError("must not construct lifecycle")))
    assert out["status"] == "acquisition_gate_failed"

def test_unified_evaluation_uses_lifecycle_memory_and_checkpointed_update(tmp_path):
    class Ledger:
        def reserve(self,*_): pass
        def settle(self,*_): pass
    def sender(_):
        return {"model":LOCKED_MODEL,"provider":"DeepSeek","choices":[{"finish_reason":"tool_calls","message":{"tool_calls":[{"function":{"name":"execute_python","arguments":'{"code":"x=1"}'}}]}}],"usage":{"prompt_tokens":1,"completion_tokens":1,"cost":.000001}}
    events=[]
    class Lifecycle:
        def memory_for(self, **kwargs): events.append(("memory", kwargs["arm"])); return "failure-derived evidence" if kwargs["arm"] != "no_memory" else ""
        def after_trial(self, **kwargs): events.append(("after", kwargs["arm"], kwargs["result"]["official_score"]["success"]))
    runner=UnifiedSuccessorRunner(store=RunStore(tmp_path), transport=LockedOpenRouterTransport(api_key="fixture",ledger=Ledger(),sender=sender), start_world=lambda *_:{"instruction":"x"}, act=lambda *_:{"completed":True}, finish=lambda _:{"success":False}, tools={"type":"function","function":{"name":"execute_python","parameters":{"type":"object","required":["code"]}}}, base_system_prompt="P")
    rows=runner.run_evaluation({"evaluation":{"task_ids":["abc1234_1"],"seeds":[7]}},{},Lifecycle())
    assert len(rows) == 4 and len([item for item in events if item[0] == "memory"]) == 4
    assert len([item for item in events if item[0] == "after"]) == 4

def test_successor_reachability_excludes_direct_and_forced_routes():
    root=Path(__file__).parents[1]
    text="\n".join((root/p).read_text(encoding="utf-8") for p in ["src/copromem/appworld_live_smoke.py","scripts/run_openrouter_successor_pilot.py","scripts/run_failure_informed_exploratory_pilot.py"])
    assert "api.deepseek.com" not in text and "DEEPSEEK_API_KEY" not in text
    assert '"tool_choice": {"type": "function"' not in text
    assert "LockedOpenRouterTransport" in text
    # The successor entry point invokes only the locked dispatch boundary; it
    # cannot invoke urllib or a legacy model-call callback itself.
    entry=(root/"scripts/run_openrouter_successor_pilot.py").read_text(encoding="utf-8")
    assert ".dispatch(" in entry and "urlopen(" not in entry and "model_call" not in entry
    exploratory=(root/"scripts/run_failure_informed_exploratory_pilot.py").read_text(encoding="utf-8")
    assert "LockedOpenRouterTransport" in exploratory and "llm_json_call=self._decompose" in exploratory
    assert "urlopen(" not in exploratory and "DEEPSEEK_API_KEY" not in exploratory
