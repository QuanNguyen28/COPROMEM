import pytest

from copromem.locked_lifecycle_json import LockedLifecycleJsonTransport, StrictLifecycleJsonError, parse_exact_json_object
from copromem.appworld_live_smoke import LOCKED_MODEL


@pytest.mark.parametrize("text", [
    '{"is_compound":false,"rationale":"direct"}',
])
def test_exact_json_accepts_valid_complexity(text):
    assert parse_exact_json_object(text, "copromem_complexity_v1")["is_compound"] is False


@pytest.mark.parametrize("text", [
    'Answer: {"is_compound":false,"rationale":"direct"}',
    '```json\n{"is_compound":false,"rationale":"direct"}\n```',
    '{"is_compound":false,"rationale":"direct"',
    '{"is_compound":false,"is_compound":true,"rationale":"direct"}',
    '{"is_compound":false,"rationale":"direct"}{"is_compound":false,"rationale":"other"}',
    '{"is_compound":"false","rationale":"direct"}',
    '{"is_compound":false,"rationale":"direct","extra":1}',
])
def test_exact_json_rejects_commentary_truncation_duplicates_multiple_and_schema_errors(text):
    with pytest.raises(StrictLifecycleJsonError):
        parse_exact_json_object(text, "copromem_complexity_v1")


def test_json_transport_has_no_tools_and_records_hashes(tmp_path):
    from copromem.checkpoints import RunStore
    class Ledger:
        def __init__(self): self.store=RunStore(tmp_path); self.events=[]
        def reserve(self,*args): self.events.append(("reserve", args[0]))
        def settle(self,*args): self.events.append(("settle", args[0]))
    def sender(body):
        assert "tools" not in body and "tool_choice" not in body
        assert body["model"] == LOCKED_MODEL and body["reasoning_effort"] == "none" and body["stream"] is False
        return {"model":LOCKED_MODEL,"provider":"DeepSeek","choices":[{"finish_reason":"stop","message":{"content":'{"is_compound":false,"rationale":"direct"}'}}],"usage":{"prompt_tokens":2,"completion_tokens":3,"cost":.000001,"completion_tokens_details":{"reasoning_tokens":0}}}
    ledger=Ledger()
    outcome=LockedLifecycleJsonTransport(api_key="fixture",ledger=ledger,sender=sender).dispatch(key="x",metadata={},system_prompt="s",user_prompt="u",schema_name="copromem_complexity_v1",upper_usd=.01)
    record=ledger.store.read("locked_lifecycle_json", "x")
    assert outcome.output["rationale"] == "direct" and record["raw_response_sha256"] and record["parsed_output_sha256"]
    assert ledger.events == [("reserve", "x"), ("settle", "x")]
