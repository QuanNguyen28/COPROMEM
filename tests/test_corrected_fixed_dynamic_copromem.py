from src.copromem.appworld_comparison_adapter import CoProMemAppWorldAdapter, TrialInput
from src.copromem.copromem_memory_module import MemoryInjectionResult

def test_task_intent_is_required_and_retrieved_once():
    a=CoProMemAppWorldAdapter(api_key="x",model="m",llm_json_call=lambda **_: None)
    observed=[]
    def retrieve(arm, task_id, intent, domain, *args):
        observed.append((arm,task_id,intent,domain))
        return MemoryInjectionResult(arm=arm,injected_text=f"guidance:{intent}")
    a.module.retrieve_memory=retrieve
    trial=TrialInput(task_id="t",intent="intent one",domain="appworld")
    other=TrialInput(task_id="u",intent="intent two",domain="appworld")
    first=a.prepare_trial(trial,1)
    second=a.prepare_trial(other,1)
    assert a.retrieval_count[("t",1)]==1
    assert observed == [("copromem_v2","t","intent one","appworld"),
                        ("copromem_v2","u","intent two","appworld")]
    assert first != second and "intent one" in first and "intent two" in second
    try: a.prepare_trial(TrialInput(task_id="u",intent="",domain="appworld"),1)
    except Exception: pass
    else: raise AssertionError("empty intent must be rejected by corrected runner gate")

def test_fixed_and_dynamic_start_hash_identical_and_do_not_share_state():
    fixed=CoProMemAppWorldAdapter(api_key="x",model="m",llm_json_call=lambda **_: None)
    initial=fixed.export_state(); dynamic=CoProMemAppWorldAdapter(api_key="x",model="m",llm_json_call=lambda **_: None)
    dynamic.clone_from_state(initial)
    assert fixed.semantic_state_hash()==dynamic.semantic_state_hash()
    dynamic.module.record_episode("dynamic_only","copromem_v2",False,{"intent":"x"},None,episode_id="dynamic-only")
    assert fixed.semantic_state_hash()!=dynamic.semantic_state_hash()

if __name__=="__main__":
    test_task_intent_is_required_and_retrieved_once()
    test_fixed_and_dynamic_start_hash_identical_and_do_not_share_state()
    print("PASS corrected CoProMem intent gate")
