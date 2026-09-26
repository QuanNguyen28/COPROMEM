"""Deterministic contract for the paid AppWorld plumbing smoke.

Live AppWorld and DeepSeek are injected boundaries; tests use fixtures and do
not contact either service.  The production entry point must supply the WSL
native executor and official scorer to these same boundaries.
"""
from __future__ import annotations
from dataclasses import dataclass
from time import perf_counter_ns
from typing import Any, Callable, Mapping, Sequence
import json
import time
import urllib.request

from .appworld_comparison_adapter import CoProMemAppWorldAdapter, RawAcquisitionTrajectory, TrialInput, no_memory_prompt
from .reme_paper_lifecycle import ReMeMemory, ReMePaperLifecycle
from .successor_ledger import SuccessorLedger
from .appworld_acquisition_gate import AcquisitionJournal, AcquisitionRef
from .checkpoints import RunStore, digest

ARMS = ("no_memory", "reme_fixed", "reme_dynamic", "copromem_v2")

LOCKED_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
LOCKED_MODEL = "deepseek/deepseek-v4.1-flash"


class LockedOpenRouterTransport:
    """The sole paid boundary for the frozen exact-ID successor pilot."""

    def __init__(self, *, api_key: str, ledger: Any, sender: Callable[[dict[str, Any]], dict[str, Any]] | None = None):
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY required")
        self.api_key, self.ledger, self.sender = api_key, ledger, sender

    @staticmethod
    def request_body(prompt: str, tools: Mapping[str, Any]) -> dict[str, Any]:
        # The frozen route permits one declared tool only.  Combined with the
        # response gate below this is the provider-neutral way of disabling
        # parallel tool execution: an answer must contain exactly one call to
        # this one schema.
        if not isinstance(tools.get("function"), Mapping) or not isinstance(tools["function"].get("name"), str):
            raise ValueError("locked transport requires one named native function tool")
        return {"model": LOCKED_MODEL, "messages": [{"role": "user", "content": prompt}],
                "tools": [dict(tools)], "tool_choice": "auto", "max_tokens": 1024,
                "stream": False, "reasoning_effort": "none",
                "provider": {"only": ["deepseek"], "allow_fallbacks": False,
                             "require_parameters": True}}

    def dispatch(self, *, key: str, metadata: dict[str, Any], prompt: str, tools: Mapping[str, Any], upper_usd: float) -> ModelOutcome:
        self.ledger.reserve(key, upper_usd, metadata)
        body = self.request_body(prompt, tools)
        started = time.perf_counter()
        try:
            if self.sender is not None:
                raw = self.sender(body)
            else:
                req = urllib.request.Request(LOCKED_OPENROUTER_URL, data=json.dumps(body).encode(),
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=45) as response:
                    raw = json.loads(response.read().decode())
        except Exception:
            # reservation deliberately remains charged/reserved on ambiguity
            raise RuntimeError("locked OpenRouter dispatch failed") from None
        choice = (raw.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        calls = message.get("tool_calls") or []
        tool_valid = False
        output: dict[str, Any] = {}
        expected_name = tools["function"]["name"]
        parameters = tools["function"].get("parameters") or {}
        required = set(parameters.get("required") or ())
        if len(calls) == 1:
            try:
                function = calls[0]["function"]
                arguments = json.loads(function["arguments"])
                exact_function = calls[0].get("type", "function") == "function" and function["name"] == expected_name
                required_present = required.issubset(arguments) if isinstance(arguments, dict) else False
                code_valid = "code" not in required or (isinstance(arguments.get("code"), str) and bool(arguments["code"].strip()))
                result_valid = "result" not in required or isinstance(arguments.get("result"), dict)
                tool_valid = isinstance(arguments, dict) and exact_function and required_present and code_valid and result_valid
                output = arguments if tool_valid else {}
            except (KeyError, TypeError, json.JSONDecodeError):
                pass
        usage = raw.get("usage") or {}
        cost = usage.get("cost")
        if cost is None:
            raise RuntimeError("OpenRouter cost missing; reservation retained")
        actual = float(cost)
        self.ledger.settle(key, actual)
        reasoning = int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or usage.get("reasoning_tokens") or 0)
        provider = raw.get("provider") or (raw.get("metadata") or {}).get("provider")
        outcome = ModelOutcome(output, int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0), actual,
            time.perf_counter() - started, str(choice.get("finish_reason")), str(raw.get("model")), tool_valid)
        validation = {"exact_model": outcome.model == LOCKED_MODEL, "resolved_provider": str(provider).lower() == "deepseek", "zero_reasoning": reasoning == 0, "tool_finish": outcome.finish_reason == "tool_calls", "valid_tool": tool_valid}
        if hasattr(self.ledger, "store"):
            self.ledger.store.write("locked_transport", key, {"response_model": outcome.model, "provider": provider, "finish_reason": outcome.finish_reason, "tool_call_count": len(calls), "usage": {"prompt_tokens": outcome.prompt_tokens, "completion_tokens": outcome.completion_tokens, "reasoning_tokens": reasoning}, "latency_seconds": outcome.latency_seconds, "actual_usd": actual, "validation": validation})
        if not all(validation.values()):
            raise RuntimeError("locked OpenRouter fidelity gate failed")
        return outcome

@dataclass(frozen=True)
class ModelOutcome:
    output: Mapping[str, Any]
    prompt_tokens: int
    completion_tokens: int
    actual_usd: float
    latency_seconds: float
    finish_reason: str
    model: str
    tool_valid: bool


class NativeAppWorldSmokeRunner:
    """All arms share exactly one executor, tool schema, action cap and scorer."""
    def __init__(self, ledger: SuccessorLedger, *, model_call: Callable[..., ModelOutcome],
                 native_execute: Callable[[str, Mapping[str, Any], int], Mapping[str, Any]],
                 official_scorer: Callable[[str, Mapping[str, Any]], bool]):
        self.ledger, self.model_call = ledger, model_call
        self.native_execute, self.official_scorer = native_execute, official_scorer
        self.records: list[dict[str, Any]] = []

    def _call(self, *, arm: str, role: str, task_id: str, phase: str, trial: int, iteration: int,
              prompt: str, tools: Mapping[str, Any], upper_usd: float = 0.006) -> Mapping[str, Any]:
        key = str(perf_counter_ns())
        meta = {"arm": arm, "role": role, "task_id": task_id, "phase": phase,
                "trial": trial, "iteration": iteration, "model": LOCKED_MODEL}
        self.ledger.reserve(key, upper_usd, meta)
        outcome = self.model_call(prompt=prompt, tools=tools, max_tokens=1024)
        self.ledger.settle(key, outcome.actual_usd)
        self.records.append({**meta, "tokens": {"prompt": outcome.prompt_tokens, "completion": outcome.completion_tokens},
                             "latency_seconds": outcome.latency_seconds, "finish_reason": outcome.finish_reason,
                             "tool_valid": outcome.tool_valid, "actual_usd": outcome.actual_usd,
                             "response_model": outcome.model})
        if outcome.model != LOCKED_MODEL or not outcome.tool_valid:
            raise RuntimeError("locked transport fidelity gate failed")
        return outcome.output

    def run(self, *, acquisition: Sequence[RawAcquisitionTrajectory], trial: TrialInput,
            tools: Mapping[str, Any], common_prompt: str) -> dict[str, Any]:
        if len(acquisition) != 2 or trial.task_id != "fac291d_1":
            raise ValueError("only the registered exposed smoke manifest is accepted")
        if trial.base_prompt != common_prompt or trial.tool_spec != tools:
            raise ValueError("all arms must receive the same executor prompt and tools")
        # Shared acquisition is recorded once; all methods receive its identical
        # public trajectory evidence, not independent arm-specific rollouts.
        copromem = CoProMemAppWorldAdapter(api_key="", decomposition_call_cap=0)
        for item in acquisition:
            copromem.ingest(item)
        copromem.consolidate()
        acquired = [ReMeMemory(f"shared::{item.identity.value}") for item in acquisition if item.success]
        reme_fixed, reme_dynamic = ReMePaperLifecycle(acquired, dynamic=False), ReMePaperLifecycle(acquired, dynamic=True)
        injected = copromem.prepare_trial(trial, 0)
        prompts = {"no_memory": no_memory_prompt(trial),
                   "reme_fixed": common_prompt + "\n\n" + "\n".join(reme_fixed.acquired.memories),
                   "reme_dynamic": common_prompt + "\n\n" + "\n".join(reme_dynamic.state_for_trial_stream(0).memories),
                   "copromem_v2": common_prompt + ("\n\n" + injected if injected else "")}
        results = {}
        for arm in ARMS:
            output = self._call(arm=arm, role="executor", task_id=trial.task_id, phase="evaluation",
                                trial=0, iteration=0, prompt=prompts[arm], tools=tools)
            native = self.native_execute(trial.task_id, output, 10)
            success = bool(self.official_scorer(trial.task_id, native))
            if arm == "reme_dynamic":
                reme_dynamic.after_evaluation(stream=0, retrieved_ids=reme_dynamic.state_for_trial_stream(0).memories,
                                               success=success, validated_addition=None)
            results[arm] = {"success": success, "prompt": prompts[arm], "tools": tools, "native": native}
        return {"results": results, "records": self.records, "copromem_state": copromem.export_state()}


class UnifiedSuccessorRunner:
    """Manifest-driven real runner; native worker/scorer remain injected boundaries."""
    def __init__(self, *, store: RunStore, transport: LockedOpenRouterTransport,
                 start_world: Callable[[str, str], Mapping[str, Any]],
                 act: Callable[[Mapping[str, Any], str], Mapping[str, Any]],
                 finish: Callable[[Mapping[str, Any]], Mapping[str, Any]],
                 tools: Mapping[str, Any], base_system_prompt: str):
        self.store, self.transport = store, transport
        self.start_world, self.act, self.finish = start_world, act, finish
        self.tools, self.base_system_prompt = tools, base_system_prompt

    def _trajectory(self, *, task_id: str, seed: int, phase: str, arm: str, injected_memory: str = "", trajectory_index: int = 0) -> dict[str, Any]:
        ref = AcquisitionRef(task_id, seed, trajectory_index)
        journal = AcquisitionJournal(self.store, ref)
        done = self.store.read("acquisition_scores", ref.key) if phase == "acquisition" else self.store.read("evaluation_scores", ref.key + "--" + arm)
        if done is not None:
            return done
        world = self.start_world(task_id, phase)
        base = self.base_system_prompt + "\nTask:\n" + str(world["instruction"])
        self.store.write("trajectory_context", ref.key + "--" + phase + "--" + arm,
                         {"task_id": task_id, "phase": phase, "arm": arm, "instruction": str(world["instruction"]), "tool_schema_sha256": digest(self.tools)})
        if injected_memory:
            base += "\n\n" + injected_memory
        if phase == "acquisition":
            journal.start(task_manifest_sha256=digest({"task_id": task_id}), base_prompt_sha256=digest(base), tool_schema_sha256=digest(self.tools))
        for iteration in range(30):
            key = f"{phase}--{task_id}--{seed}--{arm}--{iteration}"
            if self.store.read("reservations", key) is not None:
                # A prior charged/retained dispatch has no action to replay.
                # Score this fresh native world and terminalize without a call.
                score = self.finish(world)
                failure = {"task_id": task_id, "seed": seed, "arm": arm, "official_score": score, "protocol_failure": "prior_reserved_dispatch", "iteration": iteration}
                if phase == "acquisition": failure["trace_sha256"] = journal.finish(official_score=score)
                else: self.store.write("evaluation_scores", ref.key + "--" + arm, failure)
                return failure
            try:
                outcome = self.transport.dispatch(key=key, metadata={"phase": phase, "task_id": task_id, "seed": seed, "arm": arm, "iteration": iteration, "role": "executor", "model": LOCKED_MODEL}, prompt=base, tools=self.tools, upper_usd=0.003072)
            except RuntimeError as exc:
                score = self.finish(world)
                failure = {"task_id": task_id, "seed": seed, "arm": arm, "official_score": score, "protocol_failure": type(exc).__name__, "iteration": iteration}
                if phase == "acquisition":
                    failure["trace_sha256"] = journal.finish(official_score=score)
                else:
                    self.store.write("evaluation_scores", ref.key + "--" + arm, failure)
                return failure
            code = outcome.output["code"]
            if phase == "acquisition":
                journal.plan_action(iteration, code=code)
            try:
                native = self.act(world, code)
            except Exception as exc:
                score = self.finish(world)
                failure = {"task_id": task_id, "seed": seed, "arm": arm, "official_score": score, "protocol_failure": "native_worker_" + type(exc).__name__, "iteration": iteration}
                if phase == "acquisition": failure["trace_sha256"] = journal.finish(official_score=score)
                else: self.store.write("evaluation_scores", ref.key + "--" + arm, failure)
                return failure
            if phase == "acquisition":
                journal.action(iteration, code=code, native_output=native, completed=bool(native.get("completed")))
            self.store.write("native_actions", key, {"task_id": task_id, "phase": phase, "arm": arm, "iteration": iteration, "code_sha256": digest(code), "completed": bool(native.get("completed"))})
            if native.get("completed"):
                break
            base += "\nPrevious native output: " + str(native.get("summary", "action completed"))[:3000]
        score = self.finish(world)
        if phase == "acquisition":
            trace = journal.finish(official_score=score)
            return {"task_id": task_id, "seed": seed, "official_score": score, "trace_sha256": trace}
        result = {"task_id": task_id, "seed": seed, "arm": arm, "official_score": score}
        self.store.write("evaluation_scores", ref.key + "--" + arm, result)
        return result

    def run_acquisition(self, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [self._trajectory(task_id=task, seed=seed, phase="acquisition", arm="shared", trajectory_index=index)
                for task in manifest["acquisition"]["task_ids"] for index, seed in enumerate(manifest["acquisition"]["seeds"])]

    @staticmethod
    def acquisition_gate(rows: Sequence[Mapping[str, Any]]) -> bool:
        successes = [row for row in rows if bool((row.get("official_score") or {}).get("success"))]
        return len(successes) >= 3 and len({str(row["task_id"]).split("_")[0] for row in successes}) >= 3

    def run_evaluation(
        self,
        manifest: Mapping[str, Any],
        memories: Mapping[str, str],
        lifecycle: Any | None = None,
    ) -> list[dict[str, Any]]:
        """Evaluate all frozen arms; only the registered memory suffix differs."""
        rows = []
        for task in manifest["evaluation"]["task_ids"]:
            for seed in manifest["evaluation"]["seeds"]:
                for arm in ARMS:
                    memory = "" if arm == "no_memory" else str(memories.get(arm, ""))
                    if lifecycle is not None:
                        memory = str(lifecycle.memory_for(task_id=task, seed=seed, arm=arm, fallback=memory))
                    row = self._trajectory(task_id=task, seed=seed, phase="evaluation", arm=arm,
                                           injected_memory=memory)
                    if lifecycle is not None:
                        lifecycle.after_trial(task_id=task, seed=seed, arm=arm, result=row)
                    rows.append(row)
        return rows

    def run_manifest(self, manifest: Mapping[str, Any], lifecycle: Callable[[Sequence[Mapping[str, Any]], LockedOpenRouterTransport], Mapping[str, str]]) -> dict[str, Any]:
        acquisition = self.run_acquisition(manifest)
        if not self.acquisition_gate(acquisition):
            self.store.write("pilot_terminal", "acquisition_gate", {"status": "acquisition_gate_failed", "acquisition": acquisition})
            return {"status": "acquisition_gate_failed", "acquisition": acquisition}
        memories = lifecycle(acquisition, self.transport)
        required = {"reme_fixed", "reme_dynamic", "copromem_v2"}
        if set(memories) != required or len(set(memories.values())) < 2 or any(not value.strip() for value in memories.values()):
            raise RuntimeError("lifecycle provenance/memory gate failed")
        evaluation = self.run_evaluation(manifest, memories)
        self.store.write("pilot_terminal", "complete", {"status": "complete", "acquisition_count": len(acquisition), "evaluation_count": len(evaluation)})
        return {"status": "complete", "acquisition": acquisition, "evaluation": evaluation}
