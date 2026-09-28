"""Zero-leakage AppWorld adapter for the ReMe--CoProMem development pilot.

This module deliberately has no AppWorld import: callers supply the official
task executor and scorer.  That keeps lifecycle tests deterministic while the
live harness retains AppWorld's native task and scoring implementation.
"""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any, Callable, Mapping, Sequence

from ...checkpoints import RunStore
from ...copromem_memory_module import COPROMEMMemoryModule, ProceduralMemoryItem, extract_intent_constraints
from ...providers import BudgetLedger
from ...types import HandoffEvent
from ...learning import ActionObservation, ReplayOutcome, ValidationTask


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
    events: tuple[ActionObservation, ...] = ()


@dataclass(frozen=True)
class TrialInput:
    task_id: str
    intent: str
    domain: str
    sites: tuple[str, ...] = ()
    start_url: str = ""
    base_prompt: str = ""
    tool_spec: Mapping[str, Any] = field(default_factory=dict)
    structural_events: tuple[ActionObservation, ...] = ()


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


def normalize_appworld_history(history: Sequence[Mapping[str, Any]],
                               success: bool) -> tuple[ActionObservation, ...]:
    """Extract public API calls and variable flow; never retain observed values."""
    def operation_name(function: ast.AST) -> str | None:
        parts = []
        while isinstance(function, ast.Attribute):
            parts.append(function.attr)
            function = function.value
        if not isinstance(function, ast.Name):
            return None
        return ".".join((function.id, *reversed(parts)))

    events: list[ActionObservation] = []
    symbols: dict[str, str] = {}
    def slot(name: str) -> str:
        if name not in symbols:
            symbols[name] = f"var_{len(symbols) + 1}"
        return symbols[name]
    messages = list(history)
    for index, message in enumerate(messages):
        if message.get("role") != "assistant":
            continue
        try:
            tree = ast.parse(str(message.get("content", "")))
        except SyntaxError:
            continue
        response = messages[index + 1] if index + 1 < len(messages) else {}
        observed = (response.get("role") == "user" and
                    "Traceback (most recent call last)" not in str(response.get("content", "")))
        for statement in tree.body:
            direct = isinstance(statement, (ast.Expr, ast.Assign))
            calls = [node for node in ast.walk(statement)
                     if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
            for call in calls:
                operation = operation_name(call.func)
                if operation is None:
                    continue
                inputs = {keyword.arg for keyword in call.keywords if keyword.arg}
                inputs.update(slot(node.id) for arg in call.args for node in ast.walk(arg)
                              if isinstance(node, ast.Name))
                inputs.update(slot(node.id) for keyword in call.keywords
                              for node in ast.walk(keyword.value) if isinstance(node, ast.Name))
                # A loop or branch may not have executed. Keep its structure for
                # audit, but do not turn it into a usable schema without a trace.
                call_observed = bool(observed and direct)
                outputs = set()
                if isinstance(statement, ast.Assign) and len(calls) == 1:
                    outputs.update(slot(node.id) for target in statement.targets for node in ast.walk(target)
                                   if isinstance(node, ast.Name))
                if not outputs and call_observed:
                    outputs.add("observation")
                events.append(ActionObservation(
                    operation, tuple(sorted(inputs)), tuple(sorted(outputs)),
                    check="API response observed" if call_observed else "",
                    observed=call_observed))
    return tuple(events)


class AppWorldReplayEvaluator:
    """Adapter boundary: reset and score each matched guidance variant."""

    def __init__(self, reset: Callable[[ValidationTask], Any],
                 execute: Callable[[ValidationTask, Any, str], tuple[Any, float, str]],
                 score: Callable[[ValidationTask, Any], float],
                 upper_bound: Callable[[ValidationTask, str], float]) -> None:
        self.reset = reset
        self.execute = execute
        self.score = score
        self._upper_bound = upper_bound

    def upper_bound(self, task: ValidationTask, variant: str) -> float:
        return float(self._upper_bound(task, variant))

    def evaluate(self, task: ValidationTask, guidance: str, variant: str) -> ReplayOutcome:
        environment = self.reset(task)
        result, cost, artifact_id = self.execute(task, environment, guidance)
        return ReplayOutcome(float(self.score(task, result)), float(cost), str(artifact_id))


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
        self._decomposition_calls: list[dict[str, Any]] = []
        original_call = self.module.decomposer._call_json

        def recorded_call(**request: Any) -> dict[str, Any] | None:
            response = original_call(**request)
            self._decomposition_calls.append({"request_sha256": self._digest(request), "response": response})
            return response

        self.module.decomposer._call_json = recorded_call

    @staticmethod
    def _digest(value: Any) -> str:
        encoded = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, ensure_ascii=False,
            separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def retrieve_with_provenance(self, trial: TrialInput, trial_index: int) -> tuple[str, dict[str, Any]]:
        """Perform one retrieval and export every decision-bearing boundary.

        The accepted guidance is retained verbatim in the provenance bundle. This
        is deliberate: offline reproduction must not call a model, consult an
        implicit process cache, or recompute a potentially mutable decomposition.
        """
        if not trial.intent.strip():
            raise ValueError("AppWorld evaluation intent must be non-empty")
        key = (trial.task_id, trial_index)
        if self.retrieval_count.get(key, 0):
            raise RuntimeError(f"memory already retrieved for {trial.task_id} trial {trial_index}")
        pre = self.export_state(); pre_hash = self._digest(pre)
        call_start = len(self._decomposition_calls)
        task_input = {"task_id": trial.task_id, "trial_stream": trial_index, "intent": trial.intent,
                      "domain": trial.domain, "sites": list(trial.sites), "start_url": trial.start_url,
                      "base_prompt": trial.base_prompt,
                      "structural_events": [asdict(event) for event in trial.structural_events]}
        # Process-local caches are not in the exported bank. The durable JSON
        # response cache below the decomposer supplies repeated draws instead.
        self.module.decomposer._plan_cache.clear()
        self.module.decomposer._complexity_cache.clear()
        result = self.module.retrieve_memory("copromem_v2", trial.task_id, trial.intent, trial.domain,
            trial.sites, trial.start_url, trial.base_prompt, structural_events=trial.structural_events)
        self.retrieval_count[key] = 1
        post = self.export_state()
        # Retrieval must be read-only for the Fixed arm. The module may lazily
        # materialize a default schema while inspecting a task; discard that
        # transient implementation detail after retaining the returned guidance.
        if self._digest(post) != pre_hash:
            self.load_state(pre)
            post = self.export_state()
        post_hash = self._digest(post)
        guidance = result.injected_text
        if result.selected_memory_id:
            selected = next((item for item in self.module.memories
                             if item.memory_id == result.selected_memory_id), None)
            if selected is None or selected.procedure not in guidance:
                raise RuntimeError("selected procedural memory is absent from injected guidance")
        fallback = "learned" if result.selected_schema_id else ("empty" if not guidance else "exploration")
        provenance = {"version": "copromem_retrieval_provenance_v5", "task_input": task_input,
            "task_input_sha256": self._digest(task_input), "pre_state": pre, "pre_state_sha256": pre_hash,
            "post_state_sha256": post_hash, "retrieval_mutated_state": pre_hash != post_hash,
            "candidate_memory_ids": sorted(str(m.memory_id) for m in self.module.memories),
            "candidate_schema_ids": sorted(self.module.learning.schemas),
            "candidate_scores": result.candidate_scores,
            "selected_memory_id": result.selected_memory_id, "selected_schema_id": getattr(result.schema, "schema_id", None),
            "injected_procedure_ids": list(result.injected_procedure_ids),
            "separated": bool(result.separated), "should_veto": bool(result.should_veto),
            "fallback_category": fallback, "fallback_reason": fallback if fallback != "learned" else None,
            "decomposition_calls": self._decomposition_calls[call_start:],
            "model": self.module.decomposer.model,
            "guidance_bytes": guidance, "guidance_sha256": hashlib.sha256(guidance.encode()).hexdigest()}
        return guidance, provenance

    @staticmethod
    def reproduce_retrieval(frozen_bank_state: Mapping[str, Any], frozen_task_input: Mapping[str, Any],
                            frozen_provenance: Mapping[str, Any]) -> str:
        """Zero-provider-call reproduction from a complete persisted bundle."""
        digest = CoProMemAppWorldAdapter._digest
        required = {"version", "task_input", "task_input_sha256", "pre_state", "pre_state_sha256",
                    "guidance_bytes", "guidance_sha256", "retrieval_mutated_state", "decomposition_calls",
                    "selected_memory_id", "candidate_scores"}
        if not required.issubset(frozen_provenance): raise ValueError("retrieval provenance is incomplete")
        if frozen_provenance["version"] != "copromem_retrieval_provenance_v5":
            raise ValueError("legacy provenance is audit-only")
        if not str(frozen_task_input.get("intent", "")).strip(): raise ValueError("empty retrieval intent")
        if digest(dict(frozen_task_input)) != frozen_provenance["task_input_sha256"]: raise ValueError("task input changed")
        if digest(dict(frozen_bank_state)) != frozen_provenance["pre_state_sha256"]: raise ValueError("bank state changed")
        if dict(frozen_bank_state) != frozen_provenance["pre_state"]: raise ValueError("bank state provenance changed")
        if frozen_provenance["retrieval_mutated_state"]: raise ValueError("fixed retrieval mutated semantic state")
        guidance = str(frozen_provenance["guidance_bytes"])
        if hashlib.sha256(guidance.encode()).hexdigest() != frozen_provenance["guidance_sha256"]: raise ValueError("guidance hash changed")
        calls = list(frozen_provenance["decomposition_calls"])
        remaining = iter(calls)

        def replay_call(**request: Any) -> dict[str, Any] | None:
            try:
                record = next(remaining)
            except StopIteration as exc:
                raise ValueError("unrecorded decomposition call") from exc
            if digest(request) != record["request_sha256"]:
                raise ValueError("decomposition request changed")
            return record["response"]

        adapter = CoProMemAppWorldAdapter(api_key="replay" if calls else "",
            model=str(frozen_provenance.get("model", "deepseek-flash")), llm_json_call=replay_call)
        adapter.clone_from_state(dict(frozen_bank_state))
        result = adapter.module.retrieve_memory("copromem_v2", str(frozen_task_input["task_id"]),
            str(frozen_task_input["intent"]), str(frozen_task_input["domain"]),
            tuple(frozen_task_input["sites"]), str(frozen_task_input["start_url"]),
            str(frozen_task_input["base_prompt"]),
            structural_events=tuple(ActionObservation(**item) for item in frozen_task_input.get("structural_events", ())))
        if next(remaining, None) is not None:
            raise ValueError("unused decomposition response")
        if (result.injected_text != guidance or result.selected_memory_id != frozen_provenance["selected_memory_id"]
                or result.candidate_scores != frozen_provenance["candidate_scores"]
                or list(result.injected_procedure_ids) != frozen_provenance.get("injected_procedure_ids", [])
                or getattr(result.schema, "schema_id", None) != frozen_provenance["selected_schema_id"]
                or bool(result.separated) != frozen_provenance["separated"]):
            raise ValueError("retrieval decision or guidance changed")
        return guidance

    @staticmethod
    def _procedure(actions: Sequence[str]) -> str:
        useful = [a for a in actions if a and not a.startswith(("noop", "scroll"))]
        if not useful:
            return "Inspect the active AppWorld state, execute the required operation, and verify the official task outcome."
        return " -> ".join(useful)

    def ingest(self, trajectory: RawAcquisitionTrajectory, *, promote: bool = False) -> None:
        """Record every raw episode and defer positive procedure until admission."""
        identity = trajectory.identity.value
        self.module.observe_events(identity, trajectory.identity.task_id,
                                   trajectory.events, trajectory.success, trajectory.domain)
        self.module.record_episode(
            task_id=trajectory.identity.task_id,
            arm="copromem_v2",
            success=trajectory.success,
            task_state={**dict(trajectory.task_state), "intent": trajectory.intent,
                        "domain": trajectory.domain, "episode_id": identity},
            schema=None,
            handoffs=trajectory.handoffs,
            episode_id=f"trace::{identity}",
        )
        # The normalized events above are the only source for learned procedures.
        # Bare action strings carry no input/output slots or observed checks.
        if promote:
            self.module.promote_episode(identity)

    def consolidate(self) -> int:
        return self.module.consolidate_offline(min_priority=0.20)

    def prepare_trial(self, trial: TrialInput, trial_index: int) -> str:
        """Retrieve exactly once before a trial and append only registered guidance."""
        guidance, _ = self.retrieve_with_provenance(trial, trial_index)
        return guidance

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

    def semantic_state_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.export_state(), sort_keys=True,
            separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

    def load_state(self, state: dict[str, Any]) -> None:
        self.module.load_state(state)

    def clone_from_state(self, state: dict[str, Any]) -> None:
        """Restore a hash-verified semantic bank into an independent stream."""
        self.load_state(state)
        if self.export_state() != state:
            raise RuntimeError("CoProMem clone semantic state mismatch")

    def record_scored_trial(self, trial: TrialInput, trial_index: int, *, success: bool,
                            actions: Sequence[str], state_hash: str, seed: int = 0,
                            events: tuple[ActionObservation, ...] = ()) -> int:
        """Deterministic dynamic update from an already scored public trajectory."""
        if state_hash != self.semantic_state_hash():
            raise ValueError("dynamic update pre-state hash mismatch")
        decomposer = self.module.decomposer
        prior_key = decomposer.api_key
        decomposer.api_key = ""  # The post-score update must be replayable without a provider.
        decomposer._plan_cache.clear()
        decomposer._complexity_cache.clear()
        try:
            self.ingest(RawAcquisitionTrajectory(
                identity=AcquisitionIdentity(trial.task_id, seed, trial_index),
                intent=trial.intent, domain=trial.domain, success=success, actions=tuple(actions),
                task_state={"evaluation": True, "pre_update_state_hash": state_hash,
                            "trial_index": trial_index, "seed": seed},
                events=events,
            ))
            return self.consolidate()
        finally:
            decomposer.api_key = prior_key
