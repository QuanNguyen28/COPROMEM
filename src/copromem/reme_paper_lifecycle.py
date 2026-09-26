"""Stateful, testable representation of the paper-era AppWorld ReMe lifecycle.

This is a harness adapter, not a replacement for ReMe's distillation prompts or
vector store.  The live implementation must route its operations to the pinned
``reme_v3`` service; this class makes the fixed/dynamic state boundaries and
allowed mutations explicit for deterministic preflight tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class ReMeMemory:
    memory_id: str
    utility: int = 0
    frequency: int = 0
    validated: bool = True


@dataclass
class ReMeTrialState:
    memories: dict[str, ReMeMemory] = field(default_factory=dict)

    def clone(self) -> "ReMeTrialState":
        return ReMeTrialState({key: ReMeMemory(**vars(value)) for key, value in self.memories.items()})


class ReMePaperLifecycle:
    """Fixed freezes after acquisition; dynamic follows the paper-era runner.

    Dynamic update order mirrors ``appworld_react_agent.py``: add a validated
    trajectory memory, remove that new addition on failure, update frequency and
    utility for retrieved memories, then apply utility/frequency pruning.  Each
    evaluation trial stream receives an independent clone of the acquired pool;
    it may evolve across scenarios in that stream but never leaks into another
    trial stream.
    """

    def __init__(self, acquired: Iterable[ReMeMemory], *, dynamic: bool) -> None:
        self.dynamic = dynamic
        self.acquired = ReMeTrialState({item.memory_id: ReMeMemory(**vars(item)) for item in acquired})
        self.trial_streams: dict[int, ReMeTrialState] = {}

    def state_for_trial_stream(self, stream: int) -> ReMeTrialState:
        if stream not in self.trial_streams:
            self.trial_streams[stream] = self.acquired.clone()
        return self.trial_streams[stream]

    def after_evaluation(
        self,
        *,
        stream: int,
        retrieved_ids: Iterable[str],
        success: bool,
        validated_addition: ReMeMemory | None,
        frequency_threshold: int = 5,
        utility_threshold: float = 0.5,
    ) -> None:
        if not self.dynamic:
            return
        state = self.state_for_trial_stream(stream)
        # Paper-era runner creates an addition, then deletes that new item if
        # the trajectory failed.  Invalid additions never enter the pool.
        if validated_addition is not None and validated_addition.validated and success:
            state.memories[validated_addition.memory_id] = ReMeMemory(**vars(validated_addition))
        for memory_id in retrieved_ids:
            item = state.memories.get(memory_id)
            if item is None:
                continue
            item.frequency += 1
            if success:
                item.utility += 1
        # Utility is a success/frequency ratio.  This retains the paper-runner
        # alpha=5, beta=.5 behavior while making zero-frequency safe.
        state.memories = {
            key: item for key, item in state.memories.items()
            if item.frequency < frequency_threshold
            or (item.utility / item.frequency if item.frequency else 0.0) >= utility_threshold
        }
