from copromem.appworld_comparison_adapter import AppWorldPlumbingCallGate
from copromem.appworld_plumbing_smoke import AppWorldPlumbingSmokeRunner
from copromem.checkpoints import RunStore
from copromem.providers import BudgetExceeded


def test_executor_is_not_entered_when_hard_cap_would_be_exceeded(tmp_path):
    runner = AppWorldPlumbingSmokeRunner(AppWorldPlumbingCallGate(RunStore(tmp_path), max_calls=2))
    calls = []
    runner.executor_call("p", {}, upper_usd=1.0, executor=lambda prompt, tools: calls.append(prompt) or {})
    try:
        runner.executor_call("p2", {}, upper_usd=0.000001, executor=lambda prompt, tools: calls.append(prompt) or {})
    except BudgetExceeded:
        pass
    else:
        raise AssertionError("the executor must not start after the USD-1 reserve is exhausted")
    assert calls == ["p"]


def test_reme_lifecycle_is_registered_in_the_same_ledger(tmp_path):
    gate = AppWorldPlumbingCallGate(RunStore(tmp_path), max_calls=2)
    runner = AppWorldPlumbingSmokeRunner(gate)
    assert runner.reme_lifecycle_call(upper_usd=0.25, operation=lambda: "fixture") == "fixture"
    assert gate.charged_or_reserved == 0.25
