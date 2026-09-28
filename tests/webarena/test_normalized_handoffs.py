from copromem.benchmarks.webarena.benchmark import normalize_handoffs
from copromem.types import HandoffEvent, VerificationResult


def test_public_handoff_normalization_excludes_task_values():
    handoff = HandoffEvent(
        "agent_to_browser", "agent", "browser",
        {"action": "click(123)", "target": "secret account"},
        {"page": "private result"},
        (VerificationResult("accepted", True, "browser accepted action", 0.05),),
    )
    event, = normalize_handoffs([handoff])
    assert event.operation == "click"
    assert event.input_slots == ("action", "target")
    assert event.output_slots == ("page",)
    assert "secret account" not in repr(event)
    assert "private result" not in repr(event)
