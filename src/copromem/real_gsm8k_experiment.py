"""Budget-capped GSM8K pilot using real planner and solver model calls."""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GSM8K_URLS = {
    "train": "https://raw.githubusercontent.com/openai/grade-school-math/master/grade_school_math/data/train.jsonl",
    "test": "https://raw.githubusercontent.com/openai/grade-school-math/master/grade_school_math/data/test.jsonl",
}
ARMS = ("no_memory", "success_only_memory", "copromem")


@dataclass(frozen=True)
class Example:
    example_id: str
    question: str
    gold: Decimal


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    usd: float = 0.0
    latency_seconds: float = 0.0


@dataclass
class CallResult:
    text: str
    usage: Usage
    model: str


@dataclass
class TaskRun:
    example: Example
    arm: str
    predicted: Decimal | None
    initial_plan_valid: bool
    final_plan_valid: bool
    recovered: bool
    recovery_verifier_passed: bool
    calls: list[Usage] = field(default_factory=list)
    provider_models: list[str] = field(default_factory=list)

    @property
    def correct(self) -> bool:
        return self.predicted == self.example.gold


class OpenRouterClient:
    def __init__(self, api_key: str, model: str, max_usd: float, max_calls: int, seed: int | None = None):
        self.api_key = api_key
        self.model = model
        self.max_usd = max_usd
        self.max_calls = max_calls
        self.seed = seed
        self.calls = 0
        self.http_attempts = 0
        self.failed_http_attempts = 0
        self.spent_usd = 0.0

    def chat(self, system: str, user: str, max_tokens: int) -> CallResult:
        if self.calls >= self.max_calls:
            raise RuntimeError(f"call budget exhausted ({self.max_calls})")
        if self.spent_usd >= self.max_usd:
            raise RuntimeError(f"USD budget exhausted (${self.max_usd:.4f})")
        request_body: dict[str, Any] = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if self.seed is not None:
            request_body["seed"] = self.seed
        payload = json.dumps(request_body).encode("utf-8")
        started = time.perf_counter()
        body: dict[str, Any] | None = None
        for retry, delay in enumerate((0.0, 0.75, 1.5)):
            if delay:
                time.sleep(delay)
            request = urllib.request.Request(
                OPENROUTER_URL,
                data=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/openai/grade-school-math",
                    "X-Title": "CoProMem GSM8K micro-pilot",
                },
                method="POST",
            )
            self.http_attempts += 1
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    body = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                self.failed_http_attempts += 1
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                if exc.code not in {429, 502, 503, 504} or retry == 2:
                    raise RuntimeError(f"OpenRouter HTTP {exc.code}: {detail}") from exc
        if body is None:
            raise RuntimeError("OpenRouter returned no response")
        latency = time.perf_counter() - started
        self.calls += 1
        raw_usage = body.get("usage") or {}
        prompt_details = raw_usage.get("prompt_tokens_details") or {}
        completion_details = raw_usage.get("completion_tokens_details") or {}
        usage = Usage(
            prompt_tokens=int(raw_usage.get("prompt_tokens") or 0),
            completion_tokens=int(raw_usage.get("completion_tokens") or 0),
            total_tokens=int(raw_usage.get("total_tokens") or 0),
            cached_tokens=int(prompt_details.get("cached_tokens") or 0),
            reasoning_tokens=int(completion_details.get("reasoning_tokens") or 0),
            usd=float(raw_usage.get("cost") or 0.0),
            latency_seconds=latency,
        )
        self.spent_usd += usage.usd
        message = body["choices"][0]["message"]["content"]
        if isinstance(message, list):
            message = "".join(str(part.get("text", "")) for part in message if isinstance(part, dict))
        return CallResult(str(message), usage, str(body.get("model") or self.model))

    def model_metadata(self) -> dict[str, Any]:
        url = "https://openrouter.ai/api/v1/model/" + self.model
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.api_key}"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8")).get("data", {})
            return {
                "id": data.get("id", self.model),
                "name": data.get("name"),
                "context_length": data.get("context_length"),
                "pricing_usd_per_token": data.get("pricing"),
                "supported_parameters": data.get("supported_parameters"),
            }
        except (OSError, ValueError):
            return {"id": self.model, "metadata_unavailable": True}


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("\"").strip("'")
    return values


def parse_number(text: str) -> Decimal | None:
    cleaned = text.strip().replace(",", "").replace("$", "").replace("%", "")
    try:
        if "/" in cleaned and re.fullmatch(r"[-+]?\d+(?:\.\d+)?/[-+]?\d+(?:\.\d+)?", cleaned):
            numerator, denominator = cleaned.split("/", 1)
            return Decimal(numerator) / Decimal(denominator)
        return Decimal(cleaned)
    except (InvalidOperation, ZeroDivisionError):
        return None


def extract_gold(answer: str) -> Decimal:
    marker = answer.rsplit("####", 1)[-1].strip()
    value = parse_number(marker)
    if value is None:
        raise ValueError(f"unparseable GSM8K gold answer: {marker!r}")
    return value


def extract_prediction(text: str) -> Decimal | None:
    matches = re.findall(r"FINAL_ANSWER\s*:\s*([-+$]?\s*[\d,]+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?%?)", text, re.I)
    return parse_number(matches[-1].replace(" ", "")) if matches else None


def fetch_split(split: str) -> list[Example]:
    with urllib.request.urlopen(GSM8K_URLS[split], timeout=60) as response:
        lines = response.read().decode("utf-8").splitlines()
    examples = []
    for index, line in enumerate(lines):
        item = json.loads(line)
        examples.append(Example(f"{split}-{index:04d}", item["question"], extract_gold(item["answer"])))
    return examples


def longest_slice(examples: list[Example], count: int) -> list[Example]:
    """Answer-blind deterministic stress slice, returned in dataset order."""

    chosen = sorted(examples, key=lambda item: (-len(item.question), item.example_id))[:count]
    return sorted(chosen, key=lambda item: item.example_id)


def parse_plan(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}
    try:
        value = json.loads(match.group(0))
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def verify_plan(plan: dict[str, Any], required_fields: Iterable[str] = ("operations", "answer_unit", "check")) -> list[str]:
    violations: list[str] = []
    for name in required_fields:
        value = plan.get(name)
        if value is None or value == "" or value == []:
            violations.append(f"missing_or_empty:{name}")
    operations = plan.get("operations")
    if operations is not None and not isinstance(operations, list):
        violations.append("operations_must_be_list")
    elif isinstance(operations, list) and any(not isinstance(item, str) for item in operations):
        violations.append("operations_must_contain_strings")
    return violations


PLANNER_SYSTEM = """You are the planning agent in a math workflow. Produce an observable compact plan, not hidden chain-of-thought. Return ONLY JSON with keys operations (list of short calculation steps), answer_unit (string), and check (short independent verification). Do not give the final numeric answer."""
SOLVER_SYSTEM = """You are the solving agent. Solve the problem using the supplied planning artifact. Be concise and end with exactly FINAL_ANSWER: <number>."""


def plan_call(client: Any, example: Example, success_memory: dict[str, Any] | None = None) -> tuple[dict[str, Any], CallResult]:
    memory = ""
    if success_memory:
        memory = "\nA prior successful plan artifact (format/pattern only):\n" + json.dumps(success_memory, sort_keys=True)
    result = client.chat(PLANNER_SYSTEM, f"Problem:\n{example.question}{memory}", max_tokens=220)
    return parse_plan(result.text), result


def repair_call(client: Any, example: Example, plan: dict[str, Any], violations: list[str]) -> tuple[dict[str, Any], CallResult]:
    contract = {
        "interface": "planner_to_solver",
        "required_fields": ["operations", "answer_unit", "check"],
        "verifier": "non-empty typed fields",
        "recovery": "return_to_planner",
    }
    user = (
        f"Problem:\n{example.question}\nInvalid artifact:\n{json.dumps(plan, sort_keys=True)}"
        f"\nVerifier violations: {violations}\nExecutable contract: {json.dumps(contract, sort_keys=True)}"
        "\nRepair the artifact. Return ONLY the required JSON and no final answer."
    )
    result = client.chat(PLANNER_SYSTEM, user, max_tokens=220)
    return parse_plan(result.text), result


def solve_call(client: Any, example: Example, plan: dict[str, Any]) -> tuple[Decimal | None, CallResult]:
    user = f"Problem:\n{example.question}\nPlanning artifact:\n{json.dumps(plan, sort_keys=True)}"
    result = client.chat(SOLVER_SYSTEM, user, max_tokens=320)
    return extract_prediction(result.text), result


def run_task(
    client: Any,
    example: Example,
    arm: str,
    success_memory: dict[str, Any] | None,
    contract_admitted: bool,
) -> tuple[TaskRun, dict[str, Any]]:
    plan, planner = plan_call(client, example, success_memory if arm == "success_only_memory" else None)
    usages = [planner.usage]
    models = [planner.model]
    initial_valid = not verify_plan(plan)
    recovered = False
    recovery_passed = False
    if arm == "copromem" and contract_admitted:
        violations = verify_plan(plan)
        if violations:
            recovered = True
            plan, repair = repair_call(client, example, plan, violations)
            usages.append(repair.usage)
            models.append(repair.model)
            recovery_passed = not verify_plan(plan)
    predicted, solver = solve_call(client, example, plan)
    usages.append(solver.usage)
    models.append(solver.model)
    return (
        TaskRun(
            example=example,
            arm=arm,
            predicted=predicted,
            initial_plan_valid=initial_valid,
            final_plan_valid=not verify_plan(plan),
            recovered=recovered,
            recovery_verifier_passed=recovery_passed,
            calls=usages,
            provider_models=models,
        ),
        plan,
    )


def synthesize_memories(
    build_runs: list[TaskRun],
    build_plans: list[dict[str, Any]],
    prior_memory: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    success_memory = next((plan for run, plan in zip(build_runs, build_plans) if run.correct and not verify_plan(plan)), None)
    failed = [run for run in build_runs if not run.correct]
    failed_with_violation = [run for run, plan in zip(build_runs, build_plans) if not run.correct and verify_plan(plan)]
    successful_valid = [run for run, plan in zip(build_runs, build_plans) if run.correct and not verify_plan(plan)]
    prior_evidence = (prior_memory or {}).get("evidence", {})
    cumulative_evidence = {
        "build_failures": len(failed) + int(prior_evidence.get("build_failures", 0)),
        "failures_with_observable_violation": len(failed_with_violation)
        + int(prior_evidence.get("failures_with_observable_violation", 0)),
        "successful_valid_handoffs": len(successful_valid)
        + int(prior_evidence.get("successful_valid_handoffs", 0)),
    }
    admitted = bool(
        cumulative_evidence["failures_with_observable_violation"]
        and cumulative_evidence["successful_valid_handoffs"]
    )
    contract = {
        "admitted": admitted,
        "interface": "planner_to_solver",
        "required_fields": ["operations", "answer_unit", "check"] if admitted else [],
        "verifier": "non-empty typed fields",
        "recovery": "return_to_planner",
        "current_run_evidence": {
            "build_failures": len(failed),
            "failures_with_observable_violation": len(failed_with_violation),
            "successful_valid_handoffs": len(successful_valid),
        },
        "evidence": cumulative_evidence,
        "reused_prior_contract": bool(admitted and prior_memory),
    }
    return success_memory, contract


def load_cumulative_memory(paths: list[Path]) -> dict[str, Any]:
    evidence = {
        "build_failures": 0,
        "failures_with_observable_violation": 0,
        "successful_valid_handoffs": 0,
    }
    loaded: list[str] = []
    for path in paths:
        report = json.loads(path.read_text(encoding="utf-8"))
        contract = report.get("memory_construction", {}).get("copromem_contract", {})
        source_evidence = contract.get("current_run_evidence") or contract.get("evidence") or {}
        for name in evidence:
            evidence[name] += int(source_evidence.get(name, 0))
        loaded.append(str(path))
    return {"evidence": evidence, "source_reports": loaded}


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1)]


def summarize_runs(runs: list[TaskRun]) -> dict[str, Any]:
    count = len(runs)
    correct = sum(run.correct for run in runs)
    usages = [usage for run in runs for usage in run.calls]
    task_latencies = [sum(usage.latency_seconds for usage in run.calls) for run in runs]
    total_tokens = sum(item.total_tokens for item in usages)
    total_usd = sum(item.usd for item in usages)
    recoveries = [run for run in runs if run.recovered]
    parsed = [run for run in runs if run.predicted is not None]
    absolute_errors = [float(abs(run.predicted - run.example.gold)) for run in parsed if not run.correct]
    return {
        "task_success": {
            "pass_at_1": correct / count,
            "correct": correct,
            "task_count": count,
            "answer_parse_rate": len(parsed) / count,
        },
        "task_specific": {
            "exact_numeric_match_rate": correct / count,
            "median_absolute_error_on_parsed_failures": statistics.median(absolute_errors) if absolute_errors else None,
            "initial_plan_schema_pass_rate": sum(run.initial_plan_valid for run in runs) / count,
            "final_plan_schema_pass_rate": sum(run.final_plan_valid for run in runs) / count,
        },
        "efficiency": {
            "agent_calls": len(usages),
            "calls_per_task": len(usages) / count,
            "total_tokens": total_tokens,
            "tokens_per_task": total_tokens / count,
            "successful_tasks_per_1k_tokens": (correct * 1000 / total_tokens) if total_tokens else None,
            "mean_task_latency_seconds": statistics.mean(task_latencies),
            "p50_task_latency_seconds": percentile(task_latencies, 0.50),
            "p95_task_latency_seconds": percentile(task_latencies, 0.95),
        },
        "cost": {
            "total_usd": total_usd,
            "usd_per_task": total_usd / count,
            "usd_per_success": (total_usd / correct) if correct else None,
            "prompt_tokens": sum(item.prompt_tokens for item in usages),
            "completion_tokens": sum(item.completion_tokens for item in usages),
            "cached_tokens": sum(item.cached_tokens for item in usages),
            "reasoning_tokens": sum(item.reasoning_tokens for item in usages),
        },
        "agent_system": {
            "recovery_activation_rate": len(recoveries) / count,
            "recovery_verifier_pass_rate": (
                sum(run.recovery_verifier_passed for run in recoveries) / len(recoveries) if recoveries else None
            ),
            "recovered_task_success_rate": (
                sum(run.correct for run in recoveries) / len(recoveries) if recoveries else None
            ),
            "provider_models": sorted({model for run in runs for model in run.provider_models}),
        },
    }


def paired(reference: list[TaskRun], treatment: list[TaskRun]) -> dict[str, int]:
    beneficial = sum(not old.correct and new.correct for old, new in zip(reference, treatment))
    harmful = sum(old.correct and not new.correct for old, new in zip(reference, treatment))
    return {"beneficial_flips": beneficial, "harmful_flips": harmful, "net_gain": beneficial - harmful}


def compact_tasks(runs: list[TaskRun]) -> list[dict[str, Any]]:
    return [
        {
            "id": run.example.example_id,
            "gold": str(run.example.gold),
            "predicted": str(run.predicted) if run.predicted is not None else None,
            "correct": run.correct,
            "initial_plan_valid": run.initial_plan_valid,
            "final_plan_valid": run.final_plan_valid,
            "recovered": run.recovered,
            "calls": len(run.calls),
        }
        for run in runs
    ]


def run_experiment(
    client: Any,
    build: list[Example],
    evaluation: list[Example],
    model_metadata: dict[str, Any] | None = None,
    prior_memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    build_runs: list[TaskRun] = []
    build_plans: list[dict[str, Any]] = []
    for example in build:
        run, plan = run_task(client, example, "no_memory", None, False)
        build_runs.append(run)
        build_plans.append(plan)
    success_memory, contract = synthesize_memories(build_runs, build_plans, prior_memory)

    arm_runs: dict[str, list[TaskRun]] = {}
    for arm in ARMS:
        arm_runs[arm] = [
            run_task(client, example, arm, success_memory, bool(contract["admitted"]))[0]
            for example in evaluation
        ]
    build_metrics = summarize_runs(build_runs)
    arm_metrics = {arm: summarize_runs(runs) for arm, runs in arm_runs.items()}
    total_measured_usd = build_metrics["cost"]["total_usd"] + sum(
        metrics["cost"]["total_usd"] for metrics in arm_metrics.values()
    )
    total_calls = build_metrics["efficiency"]["agent_calls"] + sum(
        metrics["efficiency"]["agent_calls"] for metrics in arm_metrics.values()
    )
    return {
        "protocol": {
            "benchmark": "GSM8K",
            "dataset_source": GSM8K_URLS,
            "sampling": "answer-blind longest-question stress slice; not representative random sampling",
            "build_tasks": len(build),
            "evaluation_tasks": len(evaluation),
            "arms": list(ARMS),
            "temperature": 0,
            "request_seed": getattr(client, "seed", None),
            "model": model_metadata or {},
        },
        "memory_construction": {
            "success_only_memory_available": success_memory is not None,
            "success_only_source": "first correct build trajectory with verifier-valid plan",
            "copromem_contract": contract,
            "prior_memory": prior_memory or {"evidence": {}, "source_reports": []},
            "construction_agent_calls": 0,
        },
        "build_collection": {"metrics": build_metrics, "tasks": compact_tasks(build_runs)},
        "evaluation": {
            arm: {"metrics": arm_metrics[arm], "tasks": compact_tasks(arm_runs[arm])} for arm in ARMS
        },
        "paired": {
            "copromem_vs_no_memory": paired(arm_runs["no_memory"], arm_runs["copromem"]),
            "copromem_vs_success_only_memory": paired(
                arm_runs["success_only_memory"], arm_runs["copromem"]
            ),
        },
        "experiment_totals": {
            "measured_agent_calls": total_calls,
            "measured_cost_usd": total_measured_usd,
            "http_attempts": getattr(client, "http_attempts", total_calls),
            "failed_http_attempts": getattr(client, "failed_http_attempts", 0),
        },
        "limitations": [
            "Only four evaluation tasks; metrics are descriptive and have very high uncertainty.",
            "The answer-blind stress slice is not a representative estimate of GSM8K accuracy.",
            "GSM8K may be present in model training data; this does not establish contamination-free generalization.",
            "The procedural contract is admitted from tiny observational evidence and is not statistically validated.",
            "Provider inference can be nondeterministic even at temperature zero.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a budget-capped real-agent GSM8K micro-pilot")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--model", default="google/gemma-3-4b-it")
    parser.add_argument("--build-size", type=int, default=3)
    parser.add_argument("--eval-size", type=int, default=4)
    parser.add_argument("--max-usd", type=float, default=0.02)
    parser.add_argument("--max-calls", type=int, default=40)
    parser.add_argument("--seed", type=int, default=None, help="Provider sampling seed; task slice stays fixed")
    parser.add_argument(
        "--prior-report",
        type=Path,
        action="append",
        default=[],
        help="Prior report whose build evidence is accumulated into the contract bank (repeatable)",
    )
    parser.add_argument("--output", type=Path, default=Path("artifacts/gsm8k_real_micro.json"))
    args = parser.parse_args()
    key = load_env(args.env).get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is missing from the env file")
    client = OpenRouterClient(key, args.model, args.max_usd, args.max_calls, args.seed)
    build = longest_slice(fetch_split("train"), args.build_size)
    evaluation = longest_slice(fetch_split("test"), args.eval_size)
    prior_memory = load_cumulative_memory(args.prior_report) if args.prior_report else None
    report = run_experiment(client, build, evaluation, client.model_metadata(), prior_memory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for arm in ARMS:
        metrics = report["evaluation"][arm]["metrics"]
        print(
            f"{arm}: accuracy={metrics['task_success']['pass_at_1']:.3f}, "
            f"calls/task={metrics['efficiency']['calls_per_task']:.2f}, "
            f"tokens/task={metrics['efficiency']['tokens_per_task']:.1f}, "
            f"cost=${metrics['cost']['total_usd']:.6f}"
        )
    print(
        f"Total: {report['experiment_totals']['measured_agent_calls']} calls, "
        f"${report['experiment_totals']['measured_cost_usd']:.6f}; wrote {args.output}"
    )


if __name__ == "__main__":
    main()
