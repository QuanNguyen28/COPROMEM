"""Matched GSM8K comparison with paper-faithful literature baseline adapters.

The author repositories do not expose a shared GSM8K/DeepSeek agent harness.  This
module ports their defining prompts and control flow while sharing CoProMem's data,
provider, scoring, and usage accounting.
"""

from __future__ import annotations

import argparse
import ast
import json
import operator
import re
import subprocess
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .real_gsm8k_experiment import (
    PLANNER_SYSTEM,
    CallResult,
    Example,
    OpenRouterClient,
    TaskRun,
    Usage,
    fetch_split,
    load_env,
    longest_slice,
    paired,
    parse_plan,
    run_task,
    solve_call,
    summarize_runs,
    synthesize_memories,
    verify_plan,
)

ARMS = ("expel", "agent_workflow_memory", "critic", "copromem")
REPO_URLS = {
    "expel": "https://github.com/LeapLabTHU/ExpeL",
    "agent_workflow_memory": "https://github.com/zorazrw/agent-workflow-memory",
    "critic": "https://github.com/microsoft/ProphetNet/tree/master/CRITIC",
}

EXPEL_INDUCTION_SYSTEM = """You extract concise, general, high-level rules from agent experience.
Contrast successful and failed trials when both exist. Rules must help future math planning,
must not mention particular trials or copy their numeric answers, and must avoid duplicates.
Return at most four numbered rules and no other text."""

AWM_INDUCTION_SYSTEM = """Given successful task trajectories, extract common reusable workflows.
A workflow is a common sub-routine with example-specific values abstracted out. Each workflow
must have at least two steps. Do not generate similar or overlapping workflows. Return at most
four numbered workflows and no other text."""

CRITIC_PROGRAM_SYSTEM = """Write Python code to solve the math word problem. Store the result in
a variable named answer. Return only executable Python code, without markdown fences."""

CRITIC_REVIEW_SYSTEM = """You are verifying a Python solution to a math word problem using an
external interpreter report. Briefly identify any semantic or computational problem. If it is
correct, say that no correction is needed. Do not write replacement code yet."""

CRITIC_CORRECT_SYSTEM = """Correct a Python solution using the question, previous code, external
interpreter feedback, and critique. Return only executable Python code that stores the result in
a variable named answer. Do not use imports, files, network, reflection, or system operations."""


def _repo_revision(path: Path) -> str | None:
    # An empty vendor directory otherwise resolves the *parent project's* HEAD,
    # silently mislabelling baseline provenance as a successful reproduction.
    if not (path / ".git").exists():
        return None
    try:
        root = subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if Path(root).resolve() != path.resolve():
            return None
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _usage_dict(usages: list[Usage]) -> dict[str, Any]:
    total_tokens = sum(item.total_tokens for item in usages)
    return {
        "agent_calls": len(usages),
        "prompt_tokens": sum(item.prompt_tokens for item in usages),
        "completion_tokens": sum(item.completion_tokens for item in usages),
        "total_tokens": total_tokens,
        "cost_usd": sum(item.usd for item in usages),
        "latency_seconds": sum(item.latency_seconds for item in usages),
    }


def collect_build_experiences(
    client: Any, build: list[Example]
) -> tuple[list[TaskRun], list[dict[str, Any]]]:
    runs: list[TaskRun] = []
    plans: list[dict[str, Any]] = []
    for example in build:
        run, plan = run_task(client, example, "no_memory", None, False)
        runs.append(run)
        plans.append(plan)
    return runs, plans


def _format_experiences(runs: list[TaskRun], plans: list[dict[str, Any]]) -> str:
    items = []
    for run, plan in zip(runs, plans):
        items.append(
            "TASK: " + run.example.question + "\n"
            "TRAJECTORY: planner artifact="
            + json.dumps(plan, sort_keys=True)
            + f"; predicted={run.predicted}\nOUTCOME: {'SUCCESS' if run.correct else 'FAILURE'}"
        )
    return "\n\n".join(items)


def induce_expel(
    client: Any, runs: list[TaskRun], plans: list[dict[str, Any]]
) -> CallResult:
    prompt = (
        "Extract generally applicable insights from these experiences:\n\n"
        + _format_experiences(runs, plans)
    )
    result = client.chat(EXPEL_INDUCTION_SYSTEM, prompt, max_tokens=420)
    # OpenRouter-compatible providers occasionally return a null content field. Retry the
    # same paper prompt so an empty induction is never silently benchmarked as memory.
    for _ in range(2):
        if result.text.strip().lower() not in {"", "none", "null"}:
            break
        result = client.chat(EXPEL_INDUCTION_SYSTEM, prompt, max_tokens=420)
    return result


def induce_awm(
    client: Any, runs: list[TaskRun], plans: list[dict[str, Any]]
) -> CallResult:
    successful = [(run, plan) for run, plan in zip(runs, plans) if run.correct]
    selected = successful or list(zip(runs, plans))
    text = _format_experiences(
        [item[0] for item in selected], [item[1] for item in selected]
    )
    return client.chat(
        AWM_INDUCTION_SYSTEM,
        "Extract reusable math workflows:\n\n" + text,
        max_tokens=420,
    )


def memory_plan_call(
    client: Any, example: Example, label: str, memory: str
) -> tuple[dict[str, Any], CallResult]:
    user = (
        f"Problem:\n{example.question}\n\n{label} (use only when relevant; ignore numeric answers):\n"
        f"{memory}"
    )
    result = client.chat(PLANNER_SYSTEM, user, max_tokens=220)
    return parse_plan(result.text), result


def run_memory_task(client: Any, example: Example, arm: str, memory: str) -> TaskRun:
    label = "Experiential rules" if arm == "expel" else "Reusable workflows"
    plan, planner = memory_plan_call(client, example, label, memory)
    predicted, solver = solve_call(client, example, plan)
    valid = not verify_plan(plan)
    return TaskRun(
        example=example,
        arm=arm,
        predicted=predicted,
        initial_plan_valid=valid,
        final_plan_valid=valid,
        recovered=False,
        recovery_verifier_passed=False,
        calls=[planner.usage, solver.usage],
        provider_models=[planner.model, solver.model],
    )


_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCTIONS = {"abs": abs, "min": min, "max": max, "sum": sum, "round": round}


def _eval_expr(node: ast.AST, values: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name) and node.id in values:
        return values[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        return _BINARY[type(node.op)](
            _eval_expr(node.left, values), _eval_expr(node.right, values)
        )
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval_expr(node.operand, values))
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval_expr(item, values) for item in node.elts]
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FUNCTIONS
    ):
        if node.keywords:
            raise ValueError("keyword arguments are not allowed")
        return _FUNCTIONS[node.func.id](
            *[_eval_expr(item, values) for item in node.args]
        )
    raise ValueError(f"unsupported syntax: {type(node).__name__}")


def extract_code(text: str) -> str:
    fenced = re.search(r"```(?:python)?\s*(.*?)```", text, re.IGNORECASE | re.DOTALL)
    return (fenced.group(1) if fenced else text).strip()


def safe_execute_arithmetic(text: str) -> tuple[Decimal | None, str]:
    """Execute straight-line arithmetic without running arbitrary generated Python."""

    code = extract_code(text)
    try:
        tree = ast.parse(code, mode="exec")
        values: dict[str, Any] = {}
        for statement in tree.body:
            if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
                raise ValueError("only single-target assignments are allowed")
            target = statement.targets[0]
            if not isinstance(target, ast.Name) or target.id.startswith("_"):
                raise ValueError("only public variable assignments are allowed")
            values[target.id] = _eval_expr(statement.value, values)
        if "answer" not in values:
            raise ValueError("missing answer variable")
        answer = Decimal(str(values["answer"]))
        if not answer.is_finite():
            raise ValueError("answer is not finite")
        return answer, f"Done; answer = {answer}"
    except (
        SyntaxError,
        ValueError,
        TypeError,
        ZeroDivisionError,
        OverflowError,
        InvalidOperation,
    ) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def run_critic_task(client: Any, example: Example) -> tuple[TaskRun, dict[str, Any]]:
    initial = client.chat(
        CRITIC_PROGRAM_SYSTEM, f"Question: {example.question}", max_tokens=400
    )
    initial_prediction, initial_report = safe_execute_arithmetic(initial.text)
    review_user = (
        f"Question: {example.question}\nPrevious code:\n{extract_code(initial.text)}\n"
        f"Execution: {initial_report}\nOutput: answer = {initial_prediction}\n"
        "What's the problem with the above code?"
    )
    review = client.chat(CRITIC_REVIEW_SYSTEM, review_user, max_tokens=220)
    correction_user = (
        review_user + f"\nCritique: {review.text}\nHere's a better solution:"
    )
    correction = client.chat(CRITIC_CORRECT_SYSTEM, correction_user, max_tokens=400)
    prediction, final_report = safe_execute_arithmetic(correction.text)
    # The released CRITIC evaluator propagates the last non-null executable answer when
    # a proposed correction fails to execute. Preserve that semantics for GSM8K scoring.
    if prediction is None and initial_prediction is not None:
        prediction = initial_prediction
        final_report = (
            final_report + "; retained prior executable answer per CRITIC evaluator"
        )
    usages = [initial.usage, review.usage, correction.usage]
    models = [initial.model, review.model, correction.model]
    return (
        TaskRun(
            example=example,
            arm="critic",
            predicted=prediction,
            initial_plan_valid=initial_prediction is not None,
            final_plan_valid=prediction is not None,
            recovered=True,
            recovery_verifier_passed=prediction is not None,
            calls=usages,
            provider_models=models,
        ),
        {
            "initial_prediction": str(initial_prediction)
            if initial_prediction is not None
            else None,
            "initial_execution": initial_report,
            "final_execution": final_report,
            "critique": review.text,
        },
    )


def _compact(
    runs: list[TaskRun], details: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    result = []
    for index, run in enumerate(runs):
        item = {
            "id": run.example.example_id,
            "gold": str(run.example.gold),
            "predicted": str(run.predicted) if run.predicted is not None else None,
            "correct": run.correct,
            "initial_artifact_valid": run.initial_plan_valid,
            "final_artifact_valid": run.final_plan_valid,
            "calls": len(run.calls),
        }
        if details is not None:
            item["method_details"] = details[index]
        result.append(item)
    return result


def run_literature_benchmark(
    client: Any,
    build: list[Example],
    evaluation: list[Example],
    model_metadata: dict[str, Any] | None = None,
    vendor_root: Path = Path("vendor"),
    checkpoint_path: Path | None = None,
) -> dict[str, Any]:
    build_runs, build_plans = collect_build_experiences(client, build)
    success_memory, contract = synthesize_memories(build_runs, build_plans)
    expel_memory = induce_expel(client, build_runs, build_plans)
    awm_memory = induce_awm(client, build_runs, build_plans)

    arm_runs: dict[str, list[TaskRun]] = {}

    def checkpoint(stage: str) -> None:
        if checkpoint_path is None:
            return
        payload = {
            "status": "in_progress",
            "completed_stage": stage,
            "request_seed": getattr(client, "seed", None),
            "build_task_ids": [item.example_id for item in build],
            "evaluation_task_ids": [item.example_id for item in evaluation],
            "expel_memory": expel_memory.text,
            "agent_workflow_memory": awm_memory.text,
            "completed_arms": {
                name: {"metrics": summarize_runs(runs), "tasks": _compact(runs)}
                for name, runs in arm_runs.items()
            },
            "provider_calls_so_far": getattr(client, "calls", None),
            "provider_cost_usd_so_far": getattr(client, "spent_usd", None),
        }
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    checkpoint("memory_construction")
    arm_runs["expel"] = [
        run_memory_task(client, item, "expel", expel_memory.text) for item in evaluation
    ]
    checkpoint("expel")
    arm_runs["agent_workflow_memory"] = [
        run_memory_task(client, item, "agent_workflow_memory", awm_memory.text)
        for item in evaluation
    ]
    checkpoint("agent_workflow_memory")
    critic_pairs = [run_critic_task(client, item) for item in evaluation]
    arm_runs["critic"] = [item[0] for item in critic_pairs]
    critic_details = [item[1] for item in critic_pairs]
    checkpoint("critic")
    arm_runs["copromem"] = [
        run_task(client, item, "copromem", success_memory, bool(contract["admitted"]))[
            0
        ]
        for item in evaluation
    ]
    checkpoint("copromem")

    build_metrics = summarize_runs(build_runs)
    arm_metrics = {name: summarize_runs(runs) for name, runs in arm_runs.items()}
    induction_usages = [expel_memory.usage, awm_memory.usage]
    all_usages = (
        [usage for run in build_runs for usage in run.calls]
        + induction_usages
        + [usage for runs in arm_runs.values() for run in runs for usage in run.calls]
    )
    revisions = {
        "expel": _repo_revision(vendor_root / "ExpeL"),
        "agent_workflow_memory": _repo_revision(vendor_root / "agent-workflow-memory"),
        "critic": _repo_revision(vendor_root / "ProphetNet"),
    }
    return {
        "protocol": {
            "benchmark": "GSM8K",
            "sampling": "answer-blind longest-question stress slice; deterministic and not representative",
            "build_tasks": len(build),
            "evaluation_tasks": len(evaluation),
            "arms": list(ARMS),
            "temperature": 0,
            "request_seed": getattr(client, "seed", None),
            "model": model_metadata or {},
        },
        "implementation_provenance": {
            "repositories": {
                name: {"url": REPO_URLS[name], "revision": revisions[name]}
                for name in REPO_URLS
            },
            "expel": "Adapted released insight-extraction rule operations to GSM8K build trajectories.",
            "agent_workflow_memory": "Adapted released offline workflow induction and workflow injection.",
            "critic": "Adapted released GSM8K program-of-thought interpreter critique/correction flow; restricted arithmetic interpreter replaces arbitrary exec.",
            "copromem": "Native repository planner-to-solver executable contract arm.",
        },
        "memory_construction": {
            "shared_build_collection": {
                "metrics": build_metrics,
                "tasks": _compact(build_runs),
            },
            "expel": {
                "memory": expel_memory.text,
                "usage": _usage_dict([expel_memory.usage]),
            },
            "agent_workflow_memory": {
                "memory": awm_memory.text,
                "usage": _usage_dict([awm_memory.usage]),
            },
            "critic": {"persistent_memory": False, "construction_agent_calls": 0},
            "copromem": {"contract": contract, "construction_agent_calls": 0},
        },
        "evaluation": {
            name: {
                "metrics": arm_metrics[name],
                "tasks": _compact(
                    arm_runs[name], critic_details if name == "critic" else None
                ),
            }
            for name in ARMS
        },
        "paired_vs_copromem": {
            name: paired(arm_runs[name], arm_runs["copromem"])
            for name in ARMS
            if name != "copromem"
        },
        "experiment_totals": {
            "measured_agent_calls": len(all_usages),
            "measured_tokens": sum(item.total_tokens for item in all_usages),
            "measured_cost_usd": sum(item.usd for item in all_usages),
            "http_attempts": getattr(client, "http_attempts", len(all_usages)),
            "failed_http_attempts": getattr(client, "failed_http_attempts", 0),
        },
        "limitations": [
            "Twenty answer-blind stress-slice items give descriptive, high-uncertainty results.",
            "These are GSM8K adapters, not exact reproductions of the papers' original task suites.",
            "ExpeL and AWM share a small build set; their published systems used richer experience collections.",
            "CRITIC receives one critique/correction iteration and has a larger per-task call budget.",
            "Provider inference may be nondeterministic even at temperature zero and a request seed.",
            "GSM8K may be present in model training data.",
        ],
    }


def reconcile_report(
    client: Any,
    report_path: Path,
    output_path: Path,
    build: list[Example],
    evaluation: list[Example],
    rerun_expel: bool = True,
) -> dict[str, Any]:
    """Repair provider-null ExpeL induction and apply CRITIC's released carry-forward scoring."""

    report = json.loads(report_path.read_text(encoding="utf-8"))
    added_usages: list[Usage] = []
    if rerun_expel:
        rebuilt_runs, rebuilt_plans = collect_build_experiences(client, build)
        expel_memory = induce_expel(client, rebuilt_runs, rebuilt_plans)
        if expel_memory.text.strip().lower() in {"", "none", "null"}:
            raise RuntimeError("ExpeL induction remained empty after provider retries")
        expel_runs = [
            run_memory_task(client, item, "expel", expel_memory.text)
            for item in evaluation
        ]
        report["evaluation"]["expel"] = {
            "metrics": summarize_runs(expel_runs),
            "tasks": _compact(expel_runs),
        }
        report["memory_construction"]["expel"] = {
            "memory": expel_memory.text,
            "usage": _usage_dict([expel_memory.usage]),
            "rebuild_metrics": summarize_runs(rebuilt_runs),
        }
        added_usages = [usage for run in rebuilt_runs for usage in run.calls] + [
            expel_memory.usage
        ]
        added_usages += [usage for run in expel_runs for usage in run.calls]
    else:
        report["validity"] = report.get("validity", {})
        report["validity"]["expel"] = (
            "excluded: induction returned provider-null content (literal None)"
        )

    # CRITIC's reference evaluator uses the latest non-null prediction, so a failed
    # correction does not erase a valid initial answer.
    critic_tasks = report["evaluation"]["critic"]["tasks"]
    effective_correct: dict[str, bool] = {}
    parsed_errors: list[float] = []
    parsed_count = 0
    for task in critic_tasks:
        if task.get("predicted") is None:
            initial = task.get("method_details", {}).get("initial_prediction")
            if initial is not None:
                task["predicted"] = initial
                task["final_artifact_valid"] = True
        predicted = task.get("predicted")
        correct = False
        if predicted is not None:
            parsed_count += 1
            try:
                correct = Decimal(str(predicted)) == Decimal(str(task["gold"]))
                if not correct:
                    parsed_errors.append(
                        float(abs(Decimal(str(predicted)) - Decimal(str(task["gold"]))))
                    )
            except (InvalidOperation, ValueError):
                correct = False
        task["correct"] = correct
        effective_correct[task["id"]] = correct
    critic_metrics = report["evaluation"]["critic"]["metrics"]
    count = len(critic_tasks)
    correct_count = sum(effective_correct.values())
    critic_metrics["task_success"]["correct"] = correct_count
    critic_metrics["task_success"]["pass_at_1"] = correct_count / count
    critic_metrics["task_success"]["answer_parse_rate"] = parsed_count / count
    critic_metrics["task_specific"]["exact_numeric_match_rate"] = correct_count / count
    critic_metrics["task_specific"]["final_plan_schema_pass_rate"] = (
        parsed_count / count
    )
    critic_metrics["task_specific"]["median_absolute_error_on_parsed_failures"] = (
        sorted(parsed_errors)[(len(parsed_errors) - 1) // 2] if parsed_errors else None
    )
    total_tokens = critic_metrics["efficiency"]["total_tokens"]
    critic_metrics["efficiency"]["successful_tasks_per_1k_tokens"] = (
        correct_count * 1000 / total_tokens if total_tokens else None
    )
    total_cost = critic_metrics["cost"]["total_usd"]
    critic_metrics["cost"]["usd_per_success"] = (
        total_cost / correct_count if correct_count else None
    )
    critic_metrics["agent_system"]["recovered_task_success_rate"] = (
        correct_count / count
    )

    def task_map(name: str) -> dict[str, bool]:
        return {
            item["id"]: bool(item["correct"])
            for item in report["evaluation"][name]["tasks"]
        }

    copromem_correct = task_map("copromem")
    paired: dict[str, dict[str, int]] = {}
    for name in ("expel", "agent_workflow_memory", "critic"):
        baseline = task_map(name)
        beneficial = sum(
            not baseline[item] and copromem_correct[item] for item in copromem_correct
        )
        harmful = sum(
            baseline[item] and not copromem_correct[item] for item in copromem_correct
        )
        paired[name] = {
            "beneficial_flips": beneficial,
            "harmful_flips": harmful,
            "net_gain": beneficial - harmful,
        }
    report["paired_vs_copromem"] = paired

    report["reconciliation"] = {
        "reason": "ExpeL induction returned provider-null content in the first run; CRITIC now follows the released carry-forward evaluator.",
        "expel_rebuild_and_rerun": _usage_dict(added_usages),
        "critic_effective_prediction_policy": "retain initial executable answer when correction execution is null/invalid",
        "original_report": str(report_path),
    }
    report["experiment_totals"]["reconciled_agent_calls"] = report["experiment_totals"][
        "measured_agent_calls"
    ] + len(added_usages)
    report["experiment_totals"]["reconciled_measured_cost_usd"] = report[
        "experiment_totals"
    ]["measured_cost_usd"] + sum(item.usd for item in added_usages)
    report["status"] = "reconciled"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Historical unpaired literature adaptations; not a current research comparison"
    )
    parser.add_argument(
        "--allow-legacy-protocol",
        action="store_true",
        help="Explicitly opt into the historical unpaired test-slice protocol and legacy transport",
    )
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--model", default="deepseek/deepseek-v4-flash")
    parser.add_argument("--build-size", type=int, default=10)
    parser.add_argument("--eval-size", type=int, default=20)
    parser.add_argument("--max-usd", type=float, default=1.0)
    parser.add_argument("--max-calls", type=int, default=240)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--vendor-root", type=Path, default=Path("vendor"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/gsm8k_literature_seed42_20test.json"),
    )
    parser.add_argument(
        "--repair-report",
        type=Path,
        default=None,
        help="Reconcile a completed report's provider-null ExpeL/CRITIC outputs",
    )
    parser.add_argument(
        "--local-reconcile",
        action="store_true",
        help="Only reconcile saved CRITIC outputs; make no provider calls",
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error(
            "choose a new output path; existing research reports must be preserved"
        )
    if not args.allow_legacy_protocol and not (
        args.repair_report and args.local_reconcile
    ):
        parser.error(
            "legacy protocol is not a valid current comparison; use induction_pilot or explicitly opt in for historical work"
        )
    if args.repair_report and args.local_reconcile:
        report = reconcile_report(
            None, args.repair_report, args.output, [], [], rerun_expel=False
        )
        for arm in ARMS:
            metrics = report["evaluation"][arm]["metrics"]
            print(
                f"{arm}: accuracy={metrics['task_success']['pass_at_1']:.3f}, calls/task={metrics['efficiency']['calls_per_task']:.2f}, cost=${metrics['cost']['total_usd']:.6f}"
            )
        print(f"Locally reconciled report: {args.output}")
        return
    key = load_env(args.env).get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is missing from the env file")
    client = OpenRouterClient(key, args.model, args.max_usd, args.max_calls, args.seed)
    build = longest_slice(fetch_split("train"), args.build_size)
    evaluation = longest_slice(fetch_split("test"), args.eval_size)
    if args.repair_report:
        report = reconcile_report(
            client,
            args.repair_report,
            args.output,
            build,
            evaluation,
            rerun_expel=not args.local_reconcile,
        )
        for arm in ARMS:
            metrics = report["evaluation"][arm]["metrics"]
            print(
                f"{arm}: accuracy={metrics['task_success']['pass_at_1']:.3f}, calls/task={metrics['efficiency']['calls_per_task']:.2f}, cost=${metrics['cost']['total_usd']:.6f}"
            )
        print(f"Reconciled report: {args.output}")
        return
    checkpoint_path = args.output.with_suffix(".checkpoint.json")
    report = run_literature_benchmark(
        client,
        build,
        evaluation,
        client.model_metadata(),
        args.vendor_root,
        checkpoint_path,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for arm in ARMS:
        metrics = report["evaluation"][arm]["metrics"]
        print(
            f"{arm}: accuracy={metrics['task_success']['pass_at_1']:.3f}, "
            f"calls/task={metrics['efficiency']['calls_per_task']:.2f}, "
            f"tokens/task={metrics['efficiency']['tokens_per_task']:.1f}, "
            f"cost=${metrics['cost']['total_usd']:.6f}"
        )
    totals = report["experiment_totals"]
    print(
        f"Total: {totals['measured_agent_calls']} calls, ${totals['measured_cost_usd']:.6f}; wrote {args.output}"
    )


if __name__ == "__main__":
    main()
