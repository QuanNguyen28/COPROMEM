"""Durable evaluation/update ordering for the reduced-v2 ReMe arms.

The fixed arm is deliberately absent: its evaluation bank is immutable.
Dynamic updates run only after the caller has durably committed a score.
"""
from __future__ import annotations
from typing import Any, Callable


def concrete_retrieval(agent: Any) -> list[dict[str, Any]]:
    """Return a non-empty upstream retrieval list matching its update contract."""
    try:
        records = agent.retrieved_memory_list[0][0]
    except (AttributeError, IndexError, KeyError, TypeError):
        return []
    if not isinstance(records, list) or not records or not all(isinstance(x, dict) and x for x in records):
        return []
    return records


def dynamic_post_trial_update(agent: Any, after_score: float,
                              event: Callable[[dict[str, Any]], None]) -> str:
    """Use the pinned agent's own request method after a concrete retrieval."""
    records = concrete_retrieval(agent)
    if not records:
        event({"event": "dynamic_update_skipped_empty_retrieval"})
        return "skipped_empty_retrieval"
    produced = agent.summary_memory([agent.get_traj_from_task_history(
        agent.task_ids[0], agent.history[0][0], after_score)])
    if after_score == 1 and produced:
        agent.add_memory(produced)
    # Calls the upstream AppWorld agent method, preserving its registered body.
    agent.update_memory_information(records, after_score == 1)
    agent.delete_memory()
    event({"event": "dynamic_update_complete", "retrieved_memory_count": len(records)})
    return "updated"
