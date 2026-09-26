from copromem.tool_transport_guard import bounded_native_feedback, is_completion_truncation


def test_identifies_only_exact_output_cap_truncation():
    assert is_completion_truncation({"finish_reason":"length","response_model":"deepseek-flash","tokens":{"completion":128}}, max_tokens=128)
    assert not is_completion_truncation({"finish_reason":"tool_calls","response_model":"deepseek-flash","tokens":{"completion":128}}, max_tokens=128)
    assert not is_completion_truncation({"finish_reason":"length","response_model":"other","tokens":{"completion":128}}, max_tokens=128)


def test_bounded_feedback_is_serializable_and_limited():
    text = bounded_native_feedback({"ok": True, "output": "x" * 4000})
    assert len(text) == 3000
