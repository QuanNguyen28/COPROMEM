"""Fail-closed call boundary for the exposure-labelled AppWorld plumbing smoke.

This is deliberately not an efficacy runner.  It only ensures that any future
executor or ReMe lifecycle callback is registered with the same append-only
USD-1 gate used by the CoProMem decomposition adapter.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from .appworld_comparison_adapter import AppWorldPlumbingCallGate


class AppWorldPlumbingSmokeRunner:
    """Route every potential paid role through one pre-request reservation gate."""

    def __init__(self, call_gate: AppWorldPlumbingCallGate) -> None:
        self.call_gate = call_gate

    def executor_call(
        self,
        prompt: str,
        tools: Mapping[str, Any],
        *,
        upper_usd: float,
        executor: Callable[[str, Mapping[str, Any]], Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        self.call_gate.reserve("executor", upper_usd)
        return executor(prompt, tools)

    def reme_lifecycle_call(
        self,
        *,
        upper_usd: float,
        operation: Callable[[], Any],
    ) -> Any:
        self.call_gate.reserve("reme_lifecycle", upper_usd)
        return operation()
