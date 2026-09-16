"""Shared-checkpoint intervention protocol; no claim of learned schema logic.

Historical schema admission is retained as a labelled control while a separate
induction pipeline is developed. All six arms act at the same saved handoff.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from .checkpoints import (
    Generation,
    GenerationService,
    PlannerCheckpoint,
    RecordedCallError,
    RunStore,
    canonical,
    digest,
    matched_seed,
)
from .real_gsm8k_experiment import (
    PLANNER_SYSTEM,
    SOLVER_SYSTEM,
    Example,
    TaskRun,
    Usage,
    extract_prediction,
    parse_plan,
    synthesize_memories,
    verify_plan,
)

ARMS = (
    "no_memory",
    "success_only_memory",
    "text_rule",
    "sham_retry",
    "static_verifier",
    "copromem",
)


@dataclass(frozen=True)
class PairedConfig:
    seed: int = 17
    replicates: int = 1
    planner_tokens: int = 220
    solver_tokens: int = 320
    bootstrap_draws: int = 2000
    namespace: str = "gsm8k-shared-checkpoint-v1"
    evaluation_role: str = "development"

    def __post_init__(self) -> None:
        if (
            self.replicates < 1
            or min(self.planner_tokens, self.solver_tokens, self.bootstrap_draws) < 1
        ):
            raise ValueError(
                "replicates, token caps and bootstrap draws must be positive"
            )
        if self.evaluation_role not in {"development", "audit", "final"}:
            raise ValueError("unknown evaluation role")


class CanonicalAdapter(Protocol):
    """Method-independent public handoff, continuation and scoring boundary."""

    def checkpoint(
        self, example: Example, split: str, replicate: int
    ) -> tuple[PlannerCheckpoint, Generation]: ...

    def solve(
        self, checkpoint: PlannerCheckpoint, artifact: dict[str, Any], memory: str = ""
    ) -> Generation: ...

    def score(self, example: Example, text: str) -> bool: ...


class GSM8KAdapter:
    def __init__(self, service: GenerationService, config: PairedConfig):
        self.service = service
        self.config = config

    def checkpoint(
        self, example: Example, split: str, replicate: int
    ) -> tuple[PlannerCheckpoint, Generation]:
        generated = self.service.call(
            PLANNER_SYSTEM,
            f"Problem:\n{example.question}",
            self.config.planner_tokens,
            matched_seed(self.config.seed, example.example_id, "planner", replicate),
        )
        checkpoint = PlannerCheckpoint(
            example.example_id,
            example.question,
            split,
            "gsm8k",
            replicate,
            canonical(parse_plan(generated.text)),
            generated.request_id,
        )
        checkpoint.save(self.service.store)
        return checkpoint, generated

    def solve(
        self, checkpoint: PlannerCheckpoint, artifact: dict[str, Any], memory: str = ""
    ) -> Generation:
        prompt = f"Problem:\n{checkpoint.question}\nPlanning artifact:\n{json.dumps(artifact, sort_keys=True)}"
        if memory:
            prompt += (
                "\nPrior memory (use only if relevant, never copy instance answers):\n"
                + memory
            )
        return self.service.call(
            SOLVER_SYSTEM,
            prompt,
            self.config.solver_tokens,
            matched_seed(
                self.config.seed, checkpoint.task_id, "solver", checkpoint.replicate
            ),
        )

    def repair(
        self,
        checkpoint: PlannerCheckpoint,
        plan: dict[str, Any],
        violations: list[str],
        sham: bool,
    ) -> Generation:
        prompt = f"Problem:\n{checkpoint.question}\nCurrent artifact:\n{json.dumps(plan, sort_keys=True)}"
        if sham:
            prompt += "\nReview and regenerate the artifact. Return ONLY the required JSON and no final answer."
        else:
            contract = {
                "interface": "planner_to_solver",
                "required_fields": ["operations", "answer_unit", "check"],
                "verifier": "non-empty typed fields",
                "recovery": "return_to_planner",
            }
            prompt += (
                f"\nVerifier violations: {violations}\nExecutable contract: {json.dumps(contract, sort_keys=True)}"
                "\nRepair the artifact. Return ONLY the required JSON and no final answer."
            )
        return self.service.call(
            PLANNER_SYSTEM,
            prompt,
            self.config.planner_tokens,
            matched_seed(
                self.config.seed, checkpoint.task_id, "recovery", checkpoint.replicate
            ),
        )

    def score(self, example: Example, text: str) -> bool:
        return extract_prediction(text) == example.gold


def _validate_splits(build: list[Example], evaluation: list[Example]) -> None:
    if not build or not evaluation:
        raise ValueError("nonempty build and evaluation sets are required")
    for split in (build, evaluation):
        ids = [item.example_id for item in split]
        questions = [" ".join(item.question.split()).casefold() for item in split]
        if len(ids) != len(set(ids)) or len(questions) != len(set(questions)):
            raise ValueError("duplicate task ID or question within a split")
    if {item.example_id for item in build} & {item.example_id for item in evaluation}:
        raise ValueError("build/evaluation task ID leakage")
    if {" ".join(x.question.split()).casefold() for x in build} & {
        " ".join(x.question.split()).casefold() for x in evaluation
    }:
        raise ValueError("build/evaluation question leakage")


def resume_arm(
    adapter: GSM8KAdapter,
    checkpoint: PlannerCheckpoint,
    example: Example,
    arm: str,
    success_memory: dict[str, Any] | None,
    historical_contract: dict[str, Any],
) -> dict[str, Any]:
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm}")
    if (
        example.example_id != checkpoint.task_id
        or example.question != checkpoint.question
    ):
        raise ValueError("checkpoint/task mismatch")
    initial_id = checkpoint.checkpoint_id
    plan = checkpoint.artifact()
    violations = verify_plan(plan)
    calls: list[Generation] = []
    recovery = False
    memory = ""
    failure: str | None = None
    solver: Generation | None = None
    try:
        if arm == "success_only_memory" and success_memory is not None:
            memory = canonical(success_memory)
        elif arm == "text_rule":
            memory = "Check that the plan has non-empty operations, answer_unit, and an independent check before solving."
        active = arm in {"static_verifier", "sham_retry"} or (
            arm == "copromem" and historical_contract["admitted"]
        )
        if active and violations:
            recovery = True
            repaired = adapter.repair(checkpoint, plan, violations, arm == "sham_retry")
            calls.append(repaired)
            plan = parse_plan(repaired.text)
        solver = adapter.solve(checkpoint, plan, memory)
        calls.append(solver)
    except RecordedCallError as exc:
        failure = str(exc)
    if checkpoint.checkpoint_id != initial_id:
        raise RuntimeError("an arm mutated its immutable checkpoint")
    predicted = extract_prediction(solver.text) if solver else None
    return {
        "id": example.example_id,
        "replicate": checkpoint.replicate,
        "arm": arm,
        "checkpoint_id": initial_id,
        "initial_artifact_sha256": digest(checkpoint.artifact()),
        "final_artifact_sha256": digest(plan),
        "gold": str(example.gold),
        "predicted": str(predicted) if predicted is not None else None,
        "correct": adapter.score(example, solver.text) if solver else False,
        "initial_plan_valid": not violations,
        "final_plan_valid": not verify_plan(plan),
        "recovered": recovery,
        "artifact_changed": canonical(plan) != checkpoint.artifact_json,
        "memory_injected": bool(memory),
        "recovery_verifier_passed": recovery and not verify_plan(plan),
        "failure": failure,
        "call_ids": [item.request_id for item in calls],
        "calls": len(calls),
        "logical_usage": [item.usage for item in calls],
        "provider_models": sorted({item.model for item in calls}),
        "solver_request_id": solver.request_id if solver else None,
        "solver_seed": matched_seed(
            adapter.config.seed, checkpoint.task_id, "solver", checkpoint.replicate
        ),
        "recovery_seed": matched_seed(
            adapter.config.seed, checkpoint.task_id, "recovery", checkpoint.replicate
        ),
    }


def paired_summary(
    reference: list[dict[str, Any]],
    treatment: list[dict[str, Any]],
    config: PairedConfig,
) -> dict[str, Any]:
    def index(items: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
        indexed = {(item["id"], item["replicate"]): item for item in items}
        if len(indexed) != len(items):
            raise ValueError("duplicate paired row")
        return indexed

    old, new = index(reference), index(treatment)
    if old.keys() != new.keys() or not old:
        raise ValueError("paired rows do not match")
    beneficial = harmful = 0
    details = []
    clusters: dict[str, list[int]] = {}
    for key in sorted(old):
        first, second = old[key], new[key]
        if first["checkpoint_id"] != second["checkpoint_id"]:
            raise ValueError("paired checkpoint mismatch")
        delta = int(second["correct"]) - int(first["correct"])
        beneficial += delta == 1
        harmful += delta == -1
        clusters.setdefault(key[0], []).append(delta)
        details.append(
            {
                "id": key[0],
                "replicate": key[1],
                "delta": delta,
                "treatment_recovered": second["recovered"],
                "same_solver_request": first["solver_request_id"]
                == second["solver_request_id"],
            }
        )
    means = [sum(values) / len(values) for values in clusters.values()]
    rng = random.Random(config.seed)
    samples = sorted(
        sum(rng.choices(means, k=len(means))) / len(means)
        for _ in range(config.bootstrap_draws)
    )
    return {
        "beneficial_flips": beneficial,
        "harmful_flips": harmful,
        "net_gain": beneficial - harmful,
        "mean_accuracy_delta": sum(means) / len(means),
        "task_cluster_bootstrap_ci95": [
            samples[int(0.025 * len(samples))],
            samples[min(len(samples) - 1, int(0.975 * len(samples)))],
        ],
        "unique_tasks": len(clusters),
        "paired_rows": len(old),
        "details": details,
        "inference": "descriptive pilot; a narrow or degenerate bootstrap interval is not proof of superiority",
    }


def _metrics(
    rows: list[dict[str, Any]], planner_usage: list[dict[str, Any]]
) -> dict[str, Any]:
    usage = planner_usage + [item for row in rows for item in row["logical_usage"]]
    correct = sum(row["correct"] for row in rows)
    recoveries = [row for row in rows if row["recovered"]]
    return {
        "task_success": {
            "pass_at_1": correct / len(rows),
            "correct": correct,
            "task_count": len(rows),
        },
        "efficiency": {
            "agent_calls": len(usage),
            "calls_per_task": len(usage) / len(rows),
            "total_tokens": sum(item["total_tokens"] for item in usage),
            "tokens_per_task": sum(item["total_tokens"] for item in usage) / len(rows),
            "latency_seconds": sum(item["latency_seconds"] for item in usage),
        },
        "cost": {
            "total_usd": sum(item["usd"] for item in usage),
            "usd_per_task": sum(item["usd"] for item in usage) / len(rows),
            "usd_per_success": sum(item["usd"] for item in usage) / correct
            if correct
            else None,
            "prompt_tokens": sum(item["prompt_tokens"] for item in usage),
            "completion_tokens": sum(item["completion_tokens"] for item in usage),
        },
        "agent_system": {
            "recovery_activation_rate": len(recoveries) / len(rows),
            "recovered_task_success_rate": sum(row["correct"] for row in recoveries)
            / len(recoveries)
            if recoveries
            else None,
            "provider_failures": sum(row["failure"] is not None for row in rows),
        },
    }


def run_paired_experiment(
    client: Any,
    build: list[Example],
    evaluation: list[Example],
    model_metadata: dict[str, Any] | None = None,
    prior_memory: dict[str, Any] | None = None,
    *,
    config: PairedConfig | None = None,
    store_path: Path | None = None,
    arms: tuple[str, ...] = ARMS,
) -> dict[str, Any]:
    _validate_splits(build, evaluation)
    if (
        not arms
        or len(set(arms)) != len(arms)
        or not set(arms) <= set(ARMS)
        or "no_memory" not in arms
    ):
        raise ValueError("invalid or duplicated arm set")
    request_seed = getattr(client, "seed", None)
    config = config or PairedConfig(seed=17 if request_seed is None else request_seed)
    store = RunStore(store_path)
    manifest = {
        "config": asdict(config),
        "arms": sorted(arms),
        "model": model_metadata or {},
        "build": [
            {"id": x.example_id, "question_hash": digest(x.question)} for x in build
        ],
        "evaluation": [
            {"id": x.example_id, "question_hash": digest(x.question)}
            for x in evaluation
        ],
        "prior_memory": prior_memory,
    }
    store.write("protocol", "manifest", manifest)
    service = GenerationService(client, store, config.namespace)
    adapter = GSM8KAdapter(service, config)
    build_runs: list[TaskRun] = []
    build_plans: list[dict[str, Any]] = []
    for example in build:
        checkpoint, planner = adapter.checkpoint(example, "build", 0)
        solved = adapter.solve(checkpoint, checkpoint.artifact())
        valid = not verify_plan(checkpoint.artifact())
        build_runs.append(
            TaskRun(
                example,
                "build",
                extract_prediction(solved.text),
                valid,
                valid,
                False,
                False,
                [Usage(**planner.usage), Usage(**solved.usage)],
                [planner.model, solved.model],
            )
        )
        build_plans.append(checkpoint.artifact())
    memory, contract = synthesize_memories(build_runs, build_plans, prior_memory)
    contract["origin"] = (
        "handwritten_schema_with_observational_admission; not learned contract induction"
    )
    rows: dict[str, list[dict[str, Any]]] = {arm: [] for arm in arms}
    planners: list[dict[str, Any]] = []
    for example in evaluation:
        for replicate in range(config.replicates):
            checkpoint, planner = adapter.checkpoint(
                example, config.evaluation_role, replicate
            )
            planners.append(planner.usage)
            order = sorted(arms)
            random.Random(
                matched_seed(config.seed, example.example_id, "arm_order", replicate)
            ).shuffle(order)
            for arm in order:
                row = resume_arm(adapter, checkpoint, example, arm, memory, contract)
                row_key = digest([digest(manifest), checkpoint.checkpoint_id, arm])
                # Failed calls remain in failure logs; a completed row is immutable.
                if row["failure"] is None:
                    store.write("outcomes", row_key, row)
                rows[arm].append(row)
    costs = service.costs()
    return {
        "protocol": {
            **manifest,
            "benchmark": "GSM8K",
            "shared_upstream_checkpoint": True,
            "memory_placement": "solver context at common handoff; not original planner-memory baseline",
            "sham_policy": "static-schema-triggered retry; same token/call caps and seed, no violation details",
            "max_downstream_calls_per_task_per_arm": 2,
            "same_effective_requests": "content-addressed response reuse within matching replicate",
            "cost_convention": "arm costs include one logical planner share; physical collection costs counted once",
        },
        "memory_construction": {
            "success_only_memory_available": memory is not None,
            "copromem_contract": contract,
        },
        "evaluation": {
            arm: {"metrics": _metrics(rows[arm], planners), "tasks": rows[arm]}
            for arm in arms
        },
        "paired": {
            f"{arm}_vs_no_memory": paired_summary(rows["no_memory"], rows[arm], config)
            for arm in arms
            if arm != "no_memory"
        }
        | (
            {
                "copromem_vs_static_verifier": paired_summary(
                    rows["static_verifier"], rows["copromem"], config
                )
            }
            if {"static_verifier", "copromem"} <= set(arms)
            else {}
        ),
        "experiment_totals": {
            **costs,
            "measured_agent_calls": costs["physical_calls_this_invocation"],
            "measured_cost_usd": costs["physical_usd_this_invocation"],
            "failed_http_attempts": getattr(client, "failed_http_attempts", 0),
        },
        "limitations": [
            "The historical copromem arm is an observationally admitted handwritten schema, not learned logic.",
            "Shared checkpoints isolate upstream variation; different downstream prompts remain stochastic.",
            "Cache coupling gives identical requests one common draw, not independent replications.",
            "Actual token counts and calls can differ; the caps and recovery route are shared.",
            "GSM8K schema validity is not semantic correctness. This pilot cannot establish a memory-learning win.",
        ],
    }
