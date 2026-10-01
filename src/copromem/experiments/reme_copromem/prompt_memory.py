"""Canonical executor-memory slot formatting and exact prompt inspection.

The locked AppWorld executor receives ``previous_memories`` objects, not a
ReasoningBank retrieval record.  Keeping the slot formatter here makes that
boundary explicit: retrieval methods own their rendered guidance, while this
module owns the one executor-facing representation of that guidance.
"""
from __future__ import annotations

from typing import Any


def render_executor_memory_slot(guidance: str) -> str:
    """Return the exact source-agent text for one supplied memory item."""
    return "" if not guidance else (
        "Experience 1:\n When to use: Retrieved procedural guidance\n Content: "
        + guidance + "\n"
    )


def count_exact_memory_slot(value: Any, slot: str) -> int:
    """Count exact slot bytes across the post-``prompt_messages`` structure."""
    if not slot:
        return 0
    if isinstance(value, str):
        return value.count(slot)
    if isinstance(value, dict):
        return sum(count_exact_memory_slot(item, slot) for item in value.values())
    if isinstance(value, list):
        return sum(count_exact_memory_slot(item, slot) for item in value)
    return 0
