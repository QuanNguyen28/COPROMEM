"""Preregistered build-only induction, development replay, and independent admission audit."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
from dataclasses import asdict, replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from .checkpoints import GenerationService, RunStore, canonical, digest
from .contract_runtime import execute_policy, replay_outcome, static_schema_contract
from .induction import (
    HandoffEvidence,
    InducedContract,
    admission_decision,
    mine_candidates,
    minimize_on_development,
)
from .paired_gsm8k import GSM8KAdapter, PairedConfig
from .providers import BudgetedOpenRouterClient, BudgetLedger, model_endpoints
from .real_gsm8k_experiment import Example, fetch_split, load_env


def run_induction_pilot(
    client: Any,
    splits: dict[str, list[Example]],
    settings: dict[str, Any],
    store: RunStore,
) -> dict[str, Any]:
    seen_ids: set[str] = set()
    seen_questions: set[str] = set()
    for examples in splits.values():
        for example in examples:
            normalized = " ".join(example.question.split()).casefold()
            if example.example_id in seen_ids or normalized in seen_questions:
                raise ValueError("source/development/audit/evaluation split leakage")
            seen_ids.add(example.example_id)
            seen_questions.add(normalized)
    config = PairedConfig(seed=settings["seed"], namespace=settings["cycle_id"])
    service = GenerationService(client, store, config.namespace)
    adapter = GSM8KAdapter(service, config)
    context = {"benchmark": "gsm8k"}
    source = []
    success_memory = None
    for example in splits["build"]:
        for replicate in range(settings["build_rollouts"]):
            checkpoint, _ = adapter.checkpoint(example, "build", replicate)
            outcome = execute_policy(adapter, checkpoint, example, None, mode="none")
            if outcome["provider_failure"] is not None:
                store.write("source_failures", digest(outcome), outcome)
                continue
            evidence = HandoffEvidence(
                example.example_id,
                checkpoint.checkpoint_id,
                "planner_to_solver",
                canonical(context),
                checkpoint.artifact_json,
                outcome["success"],
                "build",
                digest(
                    {
                        "model": getattr(client, "model", "mock"),
                        "provider": getattr(client, "request_configuration", {}),
                        "planner_tokens": config.planner_tokens,
                        "temperature": 0,
                    }
                ),
            )
            store.write("source_evidence", evidence.evidence_id, asdict(evidence))
            store.write("source_outcomes", digest(outcome), outcome)
            source.append(evidence)
            if outcome["success"] and success_memory is None:
                success_memory = checkpoint.artifact_json
    proposal = mine_candidates(source)
    store.write("induction", "proposal", proposal)
    candidates = [InducedContract.load(x) for x in proposal["candidates"]]
    # Tie-breaking uses build evidence only and is fixed before seeing dev results.
    candidates.sort(
        key=lambda x: (
            -len(x.source_tasks),
            len(x.predicates),
            len(x.scope),
            x.contract_id,
        )
    )
    candidates = candidates[: settings["max_candidates"]]
    comparisons: list[dict[str, Any]] = []
    admissions = []
    admitted = []

    def evaluate(contract, split):
        rows = []
        for example in splits[split]:
            checkpoint, _ = adapter.checkpoint(example, split, 0)
            baseline = execute_policy(adapter, checkpoint, example, None, mode="none")
            treatment = execute_policy(
                adapter, checkpoint, example, contract, public_context=context
            )
            row = replay_outcome(contract, baseline, treatment, split)
            store.write("replays", digest(asdict(row)), asdict(row))
            comparisons.append(
                {"partition": split, "baseline": baseline, "treatment": treatment}
            )
            rows.append(row)
        return rows

    for candidate in candidates:
        selected, deletion_history = minimize_on_development(
            candidate, lambda contract: evaluate(contract, "dev")
        )
        dev = evaluate(selected, "dev")
        audit = evaluate(selected, "audit")
        decision = admission_decision(selected, dev, audit)
        admissions.append(
            {
                "candidate": candidate.serialize(),
                "selected": selected.serialize(),
                "deletion_history": deletion_history,
                "decision": decision,
            }
        )
        if decision["admitted"]:
            admitted.append(
                replace(
                    selected,
                    status="admitted",
                    admission_evidence=decision["evidence_digest"],
                )
            )
    # This initial cycle tests one frozen candidate at a time; no adaptive bank selection.
    evaluation = []
    static = static_schema_contract()
    for contract in admitted:
        for example in splits["evaluation"]:
            for replicate in range(settings["evaluation_replicates"]):
                checkpoint, _ = adapter.checkpoint(
                    example, "heldout_development", replicate
                )
                policies = {
                    "no_memory": (None, "none", ""),
                    "success_only_memory": (None, "none", success_memory or ""),
                    "text_rule": (contract, "text", ""),
                    "matched_sham_retry": (contract, "sham", ""),
                    "static_verifier": (static, "contract", ""),
                    "learned_contract": (contract, "contract", ""),
                }
                # The stable order is declared; a later larger study must randomize to assess service drift.
                rows = {
                    name: execute_policy(
                        adapter,
                        checkpoint,
                        example,
                        policy,
                        mode=mode,
                        public_context=context,
                        memory=memory,
                    )
                    for name, (policy, mode, memory) in policies.items()
                }
                for clause_index in range(len(contract.predicates)):
                    remaining = tuple(
                        x
                        for i, x in enumerate(contract.predicates)
                        if i != clause_index
                    )
                    if remaining:
                        ablated = replace(contract, predicates=remaining)
                        rows[f"drop_clause_{clause_index}"] = execute_policy(
                            adapter,
                            checkpoint,
                            example,
                            ablated,
                            public_context=context,
                        )
                evaluation.append(
                    {
                        "contract_id": contract.contract_id,
                        "task_id": example.example_id,
                        "replicate": replicate,
                        "arms": rows,
                    }
                )
                store.write("evaluation", digest(evaluation[-1]), evaluation[-1])
    report = {
        "settings": settings,
        "proposal": proposal,
        "admissions": admissions,
        "bank": [x.serialize() for x in admitted],
        "evaluation": evaluation,
        "source_successes": sum(x.success for x in source),
        "source_failures": sum(not x.success for x in source),
        "source_tasks": len(splits["build"]),
        "physical_costs": service.costs(),
        "status": "evaluate_frozen_candidates"
        if admitted
        else "no_admitted_contract_do_not_claim_learning_win",
        "decision": "REVISE",
        "limitations": [
            "No general semantic constraints in this grammar.",
            "Independent benign audit uses train tasks, not annotated semantic boundary families.",
            "Multiple candidate searches on dev require later independent confirmation.",
            "Empty banks and null results are retained; no threshold relaxation.",
        ],
    }
    store.write("reports", digest(report), report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()
    settings = json.loads(args.config.read_text(encoding="utf-8"))
    store = RunStore(Path(settings["output_directory"]))
    store.write("protocol", "preregistration", settings)
    provenance = {
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], text=True
        ).strip(),
        "python": platform.python_version(),
        "source_hashes": {
            p.name: digest(p.read_text(encoding="utf-8"))
            for p in sorted(Path(__file__).parent.glob("*.py"))
        },
    }
    store.bind_provenance(provenance)
    source_snapshot = {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted(Path(__file__).parent.glob("*.py"))
    }
    store.write("source_snapshots", digest(source_snapshot), source_snapshot)
    selection = store.read("dataset", "selection")
    if selection is None:
        ranked = sorted(
            fetch_split("train"),
            key=lambda x: digest([settings["selection_seed"], x.example_id]),
        )
        offset = settings["selection_offset"]
        selection = {}
        for split in ("build", "dev", "audit", "evaluation"):
            count = settings[split + "_size"]
            selection[split] = [
                {**asdict(x), "gold": str(x.gold)}
                for x in ranked[offset : offset + count]
            ]
            offset += count
        store.write("dataset", "selection", selection)
    splits = {
        name: [
            Example(x["example_id"], x["question"], Decimal(x["gold"])) for x in items
        ]
        for name, items in selection.items()
    }
    metadata = store.read("provider", "metadata")
    if metadata is None:
        store.write("provider", "metadata", model_endpoints(settings["model"]))
    key = load_env(args.env).get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not configured")
    ledger = BudgetLedger(store, settings["max_usd"], settings["max_http_attempts"])
    client = BudgetedOpenRouterClient(
        key, settings["model"], settings["provider"], ledger
    )
    report = run_induction_pilot(client, splits, settings, store)
    print(
        json.dumps(
            {
                "report_id": digest(report),
                "status": report["status"],
                "source_successes": report["source_successes"],
                "source_failures": report["source_failures"],
                "matched_pairs": report["proposal"]["matched_pairs"],
                "candidates": len(report["proposal"]["candidates"]),
                "admitted": len(report["bank"]),
                "physical_costs": report["physical_costs"],
                "charged_or_reserved_usd": ledger.charged_or_reserved,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
