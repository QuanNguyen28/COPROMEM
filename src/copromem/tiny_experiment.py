"""Tiny three-arm experiment for the central CoProMem claim.

The matched arms are no memory, memory distilled only from successful build
trajectories, and an admitted executable contract.  This remains a synthetic
mechanism check; it is not an LLM benchmark or evidence of external validity.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import fields
from pathlib import Path

from .experiment import SOURCE_PROFILE, build_contract_bank
from .metrics import paired, summarize
from .synthetic import grouped_split
from .types import JoinIntent, PlanArtifact, RunMode, WorkflowRun, as_jsonable
from .workflow import WorkflowEngine, run_many


def learn_success_only_fields(runs: list[WorkflowRun]) -> tuple[str, ...]:
    """Remember populated plan fields from successes, without reading failures."""

    successful_plans = [run.plan for run in runs if run.success]
    return tuple(
        field.name
        for field in fields(PlanArtifact)
        if any(getattr(plan, field.name) is not None for plan in successful_plans)
    )


def run_tiny_experiment(seed: int = 7) -> dict[str, object]:
    splits = grouped_split()
    build_runs = run_many(
        WorkflowEngine(), splits["build"], SOURCE_PROFILE, RunMode.NO_MEMORY, seed
    )
    success_memory_fields = learn_success_only_fields(build_runs)
    bank, construction = build_contract_bank(seed)

    # Two held-out template groups (six tasks) keep the experiment quick while
    # retaining one-to-one, one-to-many, and many-to-one cases in each group.
    final_tasks = [
        task
        for task in splits["final"]
        if task.group_id.endswith(("00", "01"))
        and task.intent is JoinIntent.PRESERVE_ROWS
    ]
    arms = {
        RunMode.NO_MEMORY.value: run_many(
            WorkflowEngine(), final_tasks, SOURCE_PROFILE, RunMode.NO_MEMORY, seed
        ),
        RunMode.SUCCESS_ONLY_MEMORY.value: run_many(
            WorkflowEngine(success_memory_fields=success_memory_fields),
            final_tasks,
            SOURCE_PROFILE,
            RunMode.SUCCESS_ONLY_MEMORY,
            seed,
        ),
        RunMode.CONTRACT_CHECK.value: run_many(
            WorkflowEngine(bank),
            final_tasks,
            SOURCE_PROFILE,
            RunMode.CONTRACT_CHECK,
            seed,
        ),
    }
    no_memory = arms[RunMode.NO_MEMORY.value]
    success_only = arms[RunMode.SUCCESS_ONLY_MEMORY.value]
    contract = arms[RunMode.CONTRACT_CHECK.value]
    rates = {name: as_jsonable(summarize(runs)) for name, runs in arms.items()}

    return {
        "protocol": {
            "claim": "executable failure-derived contracts outperform no memory and success-only memory",
            "task_count": len(final_tasks),
            "held_out_groups": sorted({task.group_id for task in final_tasks}),
            "seed": seed,
            "synthetic_only": True,
        },
        "success_only_memory": {
            "source": "successful build trajectories only",
            "successful_trajectory_count": sum(run.success for run in build_runs),
            "remembered_plan_fields": list(success_memory_fields),
        },
        "copromem": {
            "admitted_contract_count": len(bank.contracts),
            "admission": construction["admission"],
        },
        "arms": rates,
        "paired_copromem_vs_no_memory": as_jsonable(paired(no_memory, contract)),
        "paired_copromem_vs_success_only": as_jsonable(paired(success_only, contract)),
        "claim_supported_in_this_run": (
            rates[RunMode.CONTRACT_CHECK.value]["success_rate"]
            > rates[RunMode.NO_MEMORY.value]["success_rate"]
            and rates[RunMode.CONTRACT_CHECK.value]["success_rate"]
            > rates[RunMode.SUCCESS_ONLY_MEMORY.value]["success_rate"]
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the tiny three-arm CoProMem experiment"
    )
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/tiny_experiment.json")
    )
    args = parser.parse_args()
    report = run_tiny_experiment(args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    rates = {name: metrics["success_rate"] for name, metrics in report["arms"].items()}
    print(
        "Success rates: "
        + ", ".join(f"{name}={rate:.3f}" for name, rate in rates.items())
    )
    print(f"Claim supported in this run: {report['claim_supported_in_this_run']}")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
