"""Zero-leakage AppWorld adapter for the ReMe--CoProMem development pilot.

This module deliberately has no AppWorld import: callers supply the official
task executor and scorer.  That keeps lifecycle tests deterministic while the
live harness retains AppWorld's native task and scoring implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from .checkpoints import RunStore
from .copromem_memory_module import COPROMEMMemoryModule, ProceduralMemoryItem
from .providers import BudgetLedger
from .types import HandoffEvent


@dataclass(frozen=True)
class AcquisitionIdentity:
    task_id: str
    seed: int
    trajectory_index: int

    @property
    def value(self) -> str:
        return f"{self.task_id}::seed={self.seed}::trajectory={self.trajectory_index}"


@dataclass(frozen=True)
class RawAcquisitionTrajectory:
    identity: AcquisitionIdentity
    intent: str
    domain: str
    success: bool
    actions: tuple[str, ...] = ()
    task_state: Mapping[str, Any] = field(default_factory=dict)
    handoffs: tuple[HandoffEvent, ...] = ()


@dataclass(frozen=True)
class TrialInput:
    task_id: str
    intent: str
    domain: str
    sites: tuple[str, ...] = ()
    start_url: str = ""
    base_prompt: str = ""
    tool_spec: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrialResult:
    task_id: str
    trial_index: int
    injected_memory: str
    prompt: str
    scorer_input: Mapping[str, Any]
    tool_spec: Mapping[str, Any]
    success: bool


def no_memory_prompt(trial: TrialInput) -> str:
    """Baseline prompt constructor: deliberately returns no memory text."""
    return trial.base_prompt


class AppWorldPlumbingCallGate:
    """Append-only, fail-closed paid-call gate for the exposure-labelled smoke.

    The smoke runner must reserve the conservative maximum for every executor,
    ReMe, or decomposition request *before* a provider request is constructed.
    This wrapper retains reservations after an interrupted request, so the
    charged-plus-reserved exposure cannot be used again by a resumed run.
    """

    def __init__(self, store: RunStore, *, max_usd: float = 1.0, max_calls: int = 64) -> None:
        if max_usd != 1.0:
            raise ValueError("the plumbing smoke is fixed at a USD 1 hard cap")
        self.store = store
        self.ledger = BudgetLedger(store, max_usd=max_usd, max_attempts=max_calls)

    @property
    def charged_or_reserved(self) -> float:
        return self.ledger.charged_or_reserved

    def reserve(self, role: str, upper_usd: float) -> str:
        if role not in {"executor", "reme_lifecycle", "copromem_decomposition"}:
            raise ValueError("unregistered paid-call role")
        key = self.ledger.reserve(upper_usd)
        self.store.write("plumbing_call_roles", key, {"role": role, "upper_usd": upper_usd})
        return key


class CoProMemAppWorldAdapter:
    """Adapt the actual ``copromem_v2`` lifecycle to a common AppWorld harness.

    The adapter disables only generic seed memories.  Recursive decomposition,
    observed-memory retrieval, pattern separation, subtask binding, trace
    recording, and schema consolidation remain the implementation's own logic.
    """

    def __init__(
        self,
        *,
        api_key: str = "",
        model: str = "deepseek-flash",
        provider_only: str | None = None,
        reasoning_effort: str | None = None,
        llm_json_call: Callable[..., dict[str, Any] | None] | None = None,
        decomposition_call_cap: int = 320,
        call_gate: AppWorldPlumbingCallGate | None = None,
        decomposition_reserve_usd: float = 0.0,
    ) -> None:
        self.module = COPROMEMMemoryModule(
            api_key=api_key,
            model=model,
            include_contract_guidance=False,
            seed_default_memories=False,
            provider_only=provider_only,
            reasoning_effort=reasoning_effort,
            llm_json_call=llm_json_call,
        )
        if call_gate is not None and decomposition_reserve_usd <= 0:
            raise ValueError("a registered decomposition upper bound is required with a call gate")
        self.call_gate = call_gate
        self.decomposition_reserve_usd = decomposition_reserve_usd
        # When a key is provided, retain native LLM decomposition.  The cap is
        # registered in the pilot ledger instead of silently forcing fallback.
        self.module.decomposer.max_llm_calls = decomposition_call_cap
        if call_gate is not None:
            self.module.decomposer.before_llm_call = lambda: call_gate.reserve(
                "copromem_decomposition", decomposition_reserve_usd
            )
        self.decomposition_call_cap = decomposition_call_cap
        self.retrieval_count: dict[tuple[str, int], int] = {}

    @staticmethod
    def _procedure(actions: Sequence[str]) -> str:
        useful = [a for a in actions if a and not a.startswith(("noop", "scroll"))]
        if not useful:
            return "Inspect the active AppWorld state, execute the required operation, and verify the official task outcome."
        return " -> ".join(useful)

    def ingest(self, trajectory: RawAcquisitionTrajectory) -> None:
        """Record every raw episode and defer positive procedure until admission."""
        identity = trajectory.identity.value
        result = self.module.retrieve_memory(
            "copromem_v2",
            task_id=identity,
            intent=trajectory.intent,
            domain=trajectory.domain,
        )
        self.module.record_episode(
            task_id=trajectory.identity.task_id,
            arm="copromem_v2",
            success=trajectory.success,
            task_state={**dict(trajectory.task_state), "intent": trajectory.intent,
                        "domain": trajectory.domain, "episode_id": identity},
            schema=result.schema,
            handoffs=trajectory.handoffs,
            episode_id=f"trace::{identity}",
        )
        if trajectory.success:
            self.module.add_memory(
                ProceduralMemoryItem(
                    memory_id=f"mem::{identity}",
                    intent=trajectory.intent,
                    title=f"Observed AppWorld procedure for {trajectory.identity.task_id}",
                    description="Successful shared acquisition trajectory.",
                    procedure=self._procedure(trajectory.actions),
                    domain=trajectory.domain,
                    success=True,
                    schema_id=result.schema.schema_id if result.schema else None,
                    source="appworld_shared_acquisition",
                ),
                defer_until_admitted=True,
            )

    def consolidate(self) -> int:
        return self.module.consolidate_offline(min_priority=0.20)

    def prepare_trial(self, trial: TrialInput, trial_index: int) -> str:
        """Retrieve exactly once before a trial and append only registered guidance."""
        key = (trial.task_id, trial_index)
        if self.retrieval_count.get(key, 0):
            raise RuntimeError(f"memory already retrieved for {trial.task_id} trial {trial_index}")
        result = self.module.retrieve_memory(
            "copromem_v2", trial.task_id, trial.intent, trial.domain,
            trial.sites, trial.start_url, trial.base_prompt,
        )
        self.retrieval_count[key] = 1
        return result.injected_text

    def run_trial(
        self,
        trial: TrialInput,
        trial_index: int,
        executor: Callable[[str, Mapping[str, Any]], Mapping[str, Any]],
        official_scorer: Callable[[Mapping[str, Any]], bool],
    ) -> TrialResult:
        injected = self.prepare_trial(trial, trial_index)
        prompt = trial.base_prompt + ("\n\n" + injected if injected else "")
        # The executor receives the same tools and scorer payload shape as every
        # arm.  CoProMem changes only the prompt's registered guidance suffix.
        output = executor(prompt, trial.tool_spec)
        scorer_input = {"task_id": trial.task_id, "output": output}
        return TrialResult(
            task_id=trial.task_id,
            trial_index=trial_index,
            injected_memory=injected,
            prompt=prompt,
            scorer_input=scorer_input,
            tool_spec=trial.tool_spec,
            success=bool(official_scorer(scorer_input)),
        )

    def export_state(self) -> dict[str, Any]:
        return self.module.export_state()

    def load_state(self, state: dict[str, Any]) -> None:
        self.module.load_state(state)
