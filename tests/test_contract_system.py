from copromem.bank import ContractBank
from copromem.contracts import Contract, contract_from_failure
from copromem.experiment import (
    SOURCE_PROFILE,
    TRANSFER_PROFILE,
    build_contract_bank,
    run_experiment,
)
from copromem.synthetic import grouped_split
from copromem.types import HandoffEvent, JoinIntent, RunMode
from copromem.workflow import WorkflowEngine, run_many


def test_contract_recovers_an_incomplete_planner_handoff() -> None:
    tasks = grouped_split()["build"]
    engine = WorkflowEngine()
    build_runs = run_many(engine, tasks, SOURCE_PROFILE, RunMode.NO_MEMORY, seed=7)
    no_memory = next(
        run
        for run in build_runs
        if not run.success and run.plan.declared_cardinality is None
    )
    successful = next(run for run in build_runs if run.success)
    candidate = contract_from_failure(no_memory, successful)
    assert candidate is not None
    bank = ContractBank([candidate.admitted()])
    repaired = WorkflowEngine(bank).run(
        no_memory.task, SOURCE_PROFILE, RunMode.CONTRACT_CHECK, seed=7
    )
    assert repaired.recoveries
    assert repaired.plan.declared_cardinality == no_memory.task.actual_cardinality
    assert repaired.success


def test_counterexample_is_vetoed() -> None:
    bank, _ = build_contract_bank(seed=7)
    boundary = next(
        task
        for task in grouped_split()["final"]
        if task.intent is JoinIntent.INTENTIONAL_EXPANSION
    )
    run = WorkflowEngine(bank).run(
        boundary, TRANSFER_PROFILE, RunMode.CONTRACT_CHECK, seed=7
    )
    assert run.handoffs[0].verifier_results == ()
    assert run.recoveries == []


def test_task_id_counterexample_overrides_matching_scope() -> None:
    contract = Contract(
        "veto", "planner_to_solver", "plan is complete", "solver can run",
        "plan_cardinality_present", "planner", "replan",
        "join_preservation_scope", ("excluded_task",), ("declared_cardinality",),
    )
    event = HandoffEvent(
        "planner_to_solver", "planner", "solver", {"declared_cardinality": "one_to_one"},
        {"task_id": "excluded_task", "intent": JoinIntent.PRESERVE_ROWS.value},
    )
    assert not contract.is_eligible(event)


def test_admitted_bank_round_trips_without_executable_code(tmp_path) -> None:
    bank, _ = build_contract_bank(seed=7)
    path = tmp_path / "bank.json"
    bank.save(path)
    loaded = ContractBank.load(path)
    assert loaded.contracts[0].contract_id == bank.contracts[0].contract_id
    assert loaded.contracts[0].verifier_name == "plan_cardinality_present"
    assert loaded.contracts[0].status == "admitted"


def test_end_to_end_pilot_improves_over_simple_baseline() -> None:
    report = run_experiment(seed=7)
    source = report["final_source"]
    assert len(report["bank"]["contracts"]) == 1
    assert (
        source["contract_check"]["success_rate"] > source["text_rule"]["success_rate"]
    )
    assert report["paired_contract_vs_no_memory"]["harmful_flips"] == 0
