import pytest
from copromem.direct_deepseek_smoke_transport import DirectDeepSeekSmokeTransport
def test_transport_is_paid_dispatch_disabled_by_default():
    with pytest.raises(RuntimeError): DirectDeepSeekSmokeTransport().call(prompt="x",tools={},max_tokens=128)
def test_transport_shape_and_zero_reasoning_fixture():
    seen={}
    def dispatch(body):
        seen.update(body)
        return {"model":"deepseek-flash","latency_seconds":.1,"usage":{"prompt_tokens":1,"completion_tokens":1,"cost":.000001},"choices":[{"finish_reason":"tool_calls","message":{"tool_calls":[{"function":{"arguments":"{}"}}]}}]}
    out=DirectDeepSeekSmokeTransport(dispatch).call(prompt="p",tools={"t":1},max_tokens=128)
    assert out.tool_valid and seen["reasoning_effort"]=="none" and seen["stream"] is False
