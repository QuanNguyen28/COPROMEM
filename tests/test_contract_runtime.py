from dataclasses import replace
from decimal import Decimal

import pytest

from copromem.checkpoints import GenerationService, RunStore
from copromem.contract_runtime import execute_policy, static_schema_contract
from copromem.induction_pilot import run_induction_pilot
from copromem.paired_gsm8k import GSM8KAdapter, PairedConfig
from copromem.real_gsm8k_experiment import CallResult, Example, Usage


class StructuralClient:
    model = "mock/structure"

    def __init__(self):
        self.calls = 0

    def chat(self, system, user, max_tokens, *, seed=None):
        self.calls += 1
        usage = Usage(10, 10, 20)
        if "solving agent" in system:
            return CallResult("FINAL_ANSWER: 2", usage, self.model)
        if "Repair the artifact" in user:
            return CallResult(
                '{"operations":["add"],"answer_unit":"items","check":"inverse"}',
                usage,
                self.model,
            )
        return CallResult('{"operations":["add"],"check":""}', usage, self.model)


def test_induced_and_manual_equivalent_logic_share_the_entire_recovery_path():
    client = StructuralClient()
    adapter = GSM8KAdapter(
        GenerationService(client, RunStore(), "runtime"), PairedConfig()
    )
    example = Example("dev", "Compute the sum of two ones", Decimal(2))
    checkpoint, _ = adapter.checkpoint(example, "dev", 0)
    manual = static_schema_contract()
    induced_equivalent = replace(
        manual, source_tasks=("source-a", "source-b"), source_evidence=("one", "two")
    )
    first = execute_policy(adapter, checkpoint, example, manual)
    second = execute_policy(adapter, checkpoint, example, induced_equivalent)
    assert first["triggered"] and second["triggered"]
    assert first["call_ids"] == second["call_ids"]
    assert first["logical_usd"] == second["logical_usd"]
    assert first["logical_tokens"] == second["logical_tokens"]
    assert first["success"] == second["success"]


def test_unadmitted_candidate_is_rejected_at_final_boundary():
    adapter = GSM8KAdapter(
        GenerationService(StructuralClient(), RunStore(), "runtime"), PairedConfig()
    )
    example = Example("final", "Heldout example", Decimal(2))
    checkpoint, _ = adapter.checkpoint(example, "final", 0)
    with pytest.raises(ValueError):
        execute_policy(adapter, checkpoint, example, static_schema_contract())


def test_empty_induction_bank_is_retained_and_does_not_spend_on_evaluation(tmp_path):
    splits = {
        name: [
            Example(f"{name}-{i}", f"question {name}-{i}", Decimal(2)) for i in range(2)
        ]
        for name in ("build", "dev", "audit", "evaluation")
    }
    settings = {
        "seed": 17,
        "cycle_id": "mock-induction",
        "build_rollouts": 2,
        "max_candidates": 2,
        "evaluation_replicates": 2,
    }
    report = run_induction_pilot(
        StructuralClient(), splits, settings, RunStore(tmp_path)
    )
    assert report["proposal"]["matched_pairs"] == 0
    assert report["proposal"]["candidates"] == []
    assert report["bank"] == [] and report["evaluation"] == []
    assert report["source_successes"] == 4
    assert report["physical_costs"]["physical_calls_this_invocation"] == 8


def test_induction_pilot_rejects_cross_partition_question_leakage():
    example = Example("source", "identical", Decimal(2))
    with pytest.raises(ValueError):
        run_induction_pilot(
            StructuralClient(),
            {"build": [example], "dev": [replace(example, example_id="new")]},
            {},
            RunStore(),
        )
