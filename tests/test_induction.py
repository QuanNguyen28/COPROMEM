from dataclasses import replace

import pytest

from copromem.checkpoints import canonical
from copromem.induction import (
    HandoffEvidence,
    InducedContract,
    Predicate,
    ReplayOutcome,
    admission_decision,
    mine_candidates,
    minimize_on_development,
)


def traces(field="procedure", context=None):
    result = []
    for task in ("source-a", "source-b"):
        for success in (True, False):
            artifact = {field: ["a", "b"] if success else [], "optional": "explanation"}
            result.append(
                HandoffEvidence(
                    task,
                    f"{task}-{success}",
                    "producer_to_consumer",
                    canonical(context or {}),
                    canonical(artifact),
                    success,
                    "build",
                    "fixed-model-config",
                )
            )
    return result


def learned():
    return InducedContract.load(mine_candidates(traces())["candidates"][0])


def replay(contract, prefix, partition, count, beneficial=False, harmful=False):
    return [
        ReplayOutcome(
            f"{prefix}-{i}",
            f"checkpoint-{prefix}-{i}",
            contract.contract_id,
            partition,
            not (beneficial and i == 0),
            not (harmful and i == 0),
            i == 0,
            i == 0,
        )
        for i in range(count)
    ]


@pytest.mark.parametrize(
    "field", ["procedure", "join_strategy", "tool_arguments", "unseen_field"]
)
def test_field_names_come_from_evidence_not_hardcoded_logic(field):
    report = mine_candidates(traces(field))
    assert report["matched_source_tasks"] == 2
    contract = InducedContract.load(report["candidates"][0])
    assert {clause.path for clause in contract.predicates} == {(field,)}
    assert contract.violations({field: []})
    assert not contract.violations({field: ["new", "values"]})
    assert InducedContract.load(contract.serialize()) == contract


def test_success_failure_counts_across_different_tasks_are_not_pairs():
    evidence = traces()
    evidence = [
        replace(item, task_id=item.task_id + str(item.success)) for item in evidence
    ]
    assert mine_candidates(evidence)["candidates"] == []


def test_same_task_with_different_execution_context_is_not_matched():
    evidence = [replace(item, execution_context=str(item.success)) for item in traces()]
    assert mine_candidates(evidence)["matched_pairs"] == 0


def test_duplicate_source_trajectories_do_not_create_independent_support():
    evidence = traces()[:2] * 5
    report = mine_candidates(evidence)
    assert report["unique_records"] == 2
    assert report["matched_source_tasks"] == 1
    assert report["candidates"] == []


def test_successful_counterexample_prevents_universal_presence_claim():
    evidence = traces()
    evidence.append(
        replace(
            evidence[0],
            checkpoint_id="successful-empty",
            artifact_json=canonical({"procedure": []}),
        )
    )
    assert mine_candidates(evidence)["candidates"] == []


def test_unpaired_success_is_also_a_source_counterexample():
    evidence = traces()
    evidence.append(
        replace(
            evidence[0],
            task_id="unpaired-success",
            checkpoint_id="unpaired",
            artifact_json=canonical({"procedure": []}),
        )
    )
    assert mine_candidates(evidence)["candidates"] == []


def test_scope_is_induced_only_from_public_context_and_vetoes_other_context():
    report = mine_candidates(traces(context={"workflow": "counted"}))
    scoped = next(InducedContract.load(x) for x in report["candidates"] if x["scope"])
    assert scoped.eligible("producer_to_consumer", {"workflow": "counted"})
    assert not scoped.eligible("producer_to_consumer", {"workflow": "freeform"})
    assert not scoped.eligible("producer_to_consumer", {})


@pytest.mark.parametrize("partition", ["dev", "audit", "final"])
def test_nonbuild_data_cannot_enter_induction(partition):
    with pytest.raises(ValueError):
        mine_candidates([replace(traces()[0], partition=partition)])


def test_admission_requires_independent_benefit_and_zero_harm():
    contract = learned()
    dev = replay(contract, "dev", "dev", 4, beneficial=True)
    audit = replay(contract, "audit", "audit", 2)
    decision = admission_decision(contract, dev, audit)
    assert decision["admitted"]
    admitted = replace(
        contract, status="admitted", admission_evidence=decision["evidence_digest"]
    )
    assert InducedContract.load(admitted.serialize()) == admitted
    assert not admission_decision(
        contract, dev, replay(contract, "audit", "audit", 2, harmful=True)
    )["admitted"]
    assert not admission_decision(contract, replay(contract, "dev", "dev", 4), audit)[
        "admitted"
    ]
    assert not admission_decision(contract, dev[:1], audit)["admitted"]


def test_admission_rejects_wrong_contract_partition_and_leakage():
    contract = learned()
    dev = replay(contract, "dev", "dev", 4, beneficial=True)
    audit = replay(contract, "audit", "audit", 2)
    with pytest.raises(ValueError):
        admission_decision(contract, [replace(dev[0], contract_id="other")], audit)
    with pytest.raises(ValueError):
        admission_decision(contract, [replace(dev[0], partition="final")], audit)
    with pytest.raises(ValueError):
        admission_decision(contract, [replace(dev[0], task_id="source-a")], audit)


def test_safe_language_rejects_code_and_treats_bool_as_distinct_from_number():
    with pytest.raises(ValueError):
        Predicate(("x",), "eval", "dangerous-code")
    assert not Predicate(("x",), "type", "number").holds({"x": True})
    assert not Predicate(("x",), "nonempty").holds({"x": "  "})
    assert Predicate(("x",), "nonempty").holds({"x": 0})
    assert Predicate(("nested", "x"), "nonempty").holds({"nested": {"x": [1]}})


def test_minimization_reads_only_dev_and_keeps_required_clause():
    contract = replace(
        learned(),
        predicates=(
            Predicate(("procedure",), "nonempty"),
            Predicate(("optional",), "present"),
        ),
    )

    def evaluate(candidate):
        essential = Predicate(("procedure",), "nonempty") in candidate.predicates
        return replay(candidate, "dev", "dev", 4, beneficial=essential)

    minimized, history = minimize_on_development(contract, evaluate)
    assert minimized.predicates == (Predicate(("procedure",), "nonempty"),)
    assert history
    with pytest.raises(ValueError):
        minimize_on_development(
            contract, lambda x: replay(x, "final", "final", 4, beneficial=True)
        )
