"""End-to-end synthetic pilot: build a contract bank, freeze it, then evaluate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .bank import ContractBank
from .metrics import clustered_bootstrap_success_delta, paired, summarize
from .replay import compare_at_checkpoint, minimize_by_clause_deletion
from .synthetic import grouped_split
from .synthesis import evaluate_scope_and_counterexamples, propose_contracts
from .types import CostLedger, RoleProfile, RunMode, as_jsonable
from .workflow import WorkflowEngine, run_many


SOURCE_PROFILE = RoleProfile(
    name="source-executor",
    planner_omission_rate=0.62,
    solver_ignore_plan_rate=0.03,
    reviewer_detection_rate=0.65,
)
TRANSFER_PROFILE = RoleProfile(
    name="swapped-solver",
    planner_omission_rate=0.62,
    solver_ignore_plan_rate=0.10,
    reviewer_detection_rate=0.45,
)


def build_contract_bank(seed: int) -> tuple[ContractBank, dict[str, object]]:
    splits = grouped_split()
    collection_engine = WorkflowEngine()
    build_runs = run_many(collection_engine, splits["build"], SOURCE_PROFILE, RunMode.NO_MEMORY, seed)
    candidates = propose_contracts(build_runs)
    if not candidates:
        raise RuntimeError("synthetic build set did not yield an observable handoff candidate")

    # Bounded proposal set; this implementation admits the first valid typed
    # hypothesis. A real extractor may return up to three candidates per failure.
    candidate = candidates[0]
    replay = compare_at_checkpoint(candidate, splits["build"], SOURCE_PROFILE, seed)
    minimized, minimized_replay = minimize_by_clause_deletion(candidate, splits["dev"], SOURCE_PROFILE, seed)
    boundaries = [task for task in splits["audit"] if task.intent.value == "intentional_expansion"]
    scope_tasks = [task for task in splits["dev"] if task.requires_cardinality_rationale]
    scope = evaluate_scope_and_counterexamples(minimized, scope_tasks, boundaries, TRANSFER_PROFILE, seed)
    bank = ContractBank()
    decision = bank.admit(minimized, minimized_replay, scope)
    if not decision.admitted:
        raise RuntimeError("candidate unexpectedly failed admission: " + "; ".join(decision.reasons))

    lifecycle = CostLedger(
        trace_collection_cost=sum(run.cost.runtime_cost for run in build_runs),
        extraction_cost=float(len(candidates)),
        replay_cost=float(replay.checkpoint_count * 4 + minimized_replay.checkpoint_count * 4),
        boundary_cost=float(len(boundaries) + len(scope_tasks)),
    )
    return bank, {
        "candidate_count": len(candidates),
        "admission": as_jsonable(decision),
        "replay_before_minimization": as_jsonable(replay),
        "replay_after_minimization": as_jsonable(minimized_replay),
        "scope_and_transfer": as_jsonable(scope),
        "minimization": {
            "initial_required_fields": list(candidate.required_fields),
            "retained_required_fields": list(minimized.required_fields),
            "claim": "empirically 1-minimal for tested field-deletion set",
        },
        "lifecycle_build_cost": lifecycle.lifecycle_cost,
    }


def run_experiment(seed: int = 7) -> dict[str, object]:
    bank, construction = build_contract_bank(seed)
    final_tasks = grouped_split()["final"]
    source_engine = WorkflowEngine(bank)
    transfer_engine = WorkflowEngine(bank)

    source_arms = {
        mode.value: run_many(source_engine, final_tasks, SOURCE_PROFILE, mode, seed)
        for mode in (RunMode.NO_MEMORY, RunMode.TEXT_RULE, RunMode.SHAM_RETRY, RunMode.STATIC_VERIFIER, RunMode.CONTRACT_CHECK)
    }
    transfer_arms = {
        mode.value: run_many(transfer_engine, final_tasks, TRANSFER_PROFILE, mode, seed)
        for mode in (RunMode.NO_MEMORY, RunMode.TEXT_RULE, RunMode.CONTRACT_CHECK)
    }
    reference = source_arms[RunMode.NO_MEMORY.value]
    contract_runs = source_arms[RunMode.CONTRACT_CHECK.value]
    interval = clustered_bootstrap_success_delta(reference, contract_runs, seed)
    return {
        "protocol": {
            "domain": "public join-cardinality planning artifact",
            "split_policy": "template groups are disjoint across build/dev/audit/final",
            "arms": [mode.value for mode in (RunMode.NO_MEMORY, RunMode.TEXT_RULE, RunMode.SHAM_RETRY, RunMode.STATIC_VERIFIER, RunMode.CONTRACT_CHECK)],
            "seed": seed,
        },
        "bank": {"contracts": [as_jsonable(contract) for contract in bank.contracts]},
        "construction": construction,
        "final_source": {name: as_jsonable(summarize(runs)) for name, runs in source_arms.items()},
        "final_transfer_executor_swap": {name: as_jsonable(summarize(runs)) for name, runs in transfer_arms.items()},
        "paired_contract_vs_no_memory": as_jsonable(paired(reference, contract_runs)),
        "clustered_95pct_ci_success_delta": list(interval),
        "notes": [
            "The static-verifier arm separates the learned-contract admission protocol from verifier value.",
            "Intentional expansions are vetoed by scope; they are reported during admission rather than counted as eligible coverage.",
            "This is a synthetic feasibility demonstration, not evidence for claims on DS-1000, AFTER, or LLM agents.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the reproducible CoProMem synthetic pilot")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output", type=Path, default=Path("artifacts/synthetic_report.json"))
    args = parser.parse_args()
    report = run_experiment(args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    contract_count = len(report["bank"]["contracts"])
    source = report["final_source"][RunMode.CONTRACT_CHECK.value]["success_rate"]
    baseline = report["final_source"][RunMode.NO_MEMORY.value]["success_rate"]
    print(f"Admitted {contract_count} contract(s). Final success: no-memory={baseline:.3f}, contract={source:.3f}")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
