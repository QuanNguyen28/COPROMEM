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
                              event: Callable[[dict[str, Any]], None], *,
                              summary_persists: bool = False) -> str:
    """Use the pinned agent's own request method after a concrete retrieval."""
    records = concrete_retrieval(agent)
    # Upstream dynamic reflection is outcome-driven, not retrieval-gated:
    # a successful trajectory may create a new memory even when recall was
    # empty.  Only metadata updates require an existing retrieved record.
    produced = agent.summary_memory([agent.get_traj_from_task_history(
        agent.task_ids[0], agent.history[0][0], after_score)])
    if after_score == 1 and produced:
        if summary_persists:
            # The pinned legacy ReMe service's summary_task_memory route is
            # registered with its vector-store persistence operation.  Calling
            # add_task_memory again would duplicate an already-admitted
            # summary, so preserve the upstream outcome while avoiding a
            # duplicate insertion through this explicitly recorded boundary.
            event({"event": "dynamic_summary_persisted_by_registered_flow",
                   "memory_summary_count": len(produced)})
        else:
            agent.add_memory(produced)
    if records:
        # Calls the upstream AppWorld agent method, preserving its request body.
        agent.update_memory_information(records, after_score == 1)
    else:
        event({"event": "dynamic_update_skipped_empty_retrieval"})
    agent.delete_memory()
    event({"event": "dynamic_update_complete", "retrieved_memory_count": len(records),
           "memory_summary_produced": bool(produced)})
    return "updated" if records else "updated_without_retrieval"
