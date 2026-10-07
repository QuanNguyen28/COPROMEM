from __future__ import annotations

import hashlib
import json
import pathlib

import pytest

from copromem.experiments.reme_copromem.evidence_contract import VERSION
from copromem.experiments.reme_copromem.live_summary import (
    ARMS, LedgerReconciliationError, build_live_summary, reconcile_ledger, write_live_summary,
)


HISTORICAL = 2.35384537
TASKS = tuple(f"task-{index}" for index in range(6))
SEEDS = (11001, 11002)


def _append(path: pathlib.Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle: handle.write(json.dumps(row, sort_keys=True) + "\n")


def _ledger(path: pathlib.Path, *, rows: list[dict] | None = None) -> pathlib.Path:
    for row in rows or [
        {"event": "reserve", "id": "historical-construction-carry", "usd": HISTORICAL, "role": "historical_carry_forward"},
        {"event": "settle", "id": "historical-construction-carry", "usd": HISTORICAL, "role": "historical_carry_forward"},
    ]: _append(path, row)
    return path


def _artifact(root: pathlib.Path, *, arm: str = "no_memory", task: str = TASKS[0], trial: int = 1,
              seed: int = SEEDS[0], valid: bool = True) -> pathlib.Path:
    history = [{"role": "user", "content": "public"}, {"role": "assistant", "content": "call"}]
    evidence = root / "journals" / f"{arm}-{task}-{trial}.jsonl"; evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text('{"event":"response_attested"}\n', encoding="utf-8")
    scorer = root / "journals" / f"{arm}-{task}-{trial}.scorer.jsonl"
    scorer.write_text(json.dumps({"event":"official_score", "trajectory_id":f"evaluation:{arm}:{task}:trial={trial}:seed={seed}",
                                  "task_id":task, "pass_count":1, "fail_count":0,
                                  "score_phase":"post_trajectory"}) + "\n", encoding="utf-8")
    row = {"trajectory_id": f"evaluation:{arm}:{task}:trial={trial}:seed={seed}", "arm": arm, "task_id": task,
           "trial_id": trial, "seed": seed, "after_score": 1.0, "actions": 1, "history": history,
           "history_sha256": hashlib.sha256(json.dumps(history, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
           "execution_evidence_path": str(evidence.resolve()), "execution_evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
           "execution_evidence_rows": 1, "execution_evidence_registry_sha256": "registry",
           "execution_evidence_run_relative": str(evidence.resolve().relative_to(root.resolve())),
           "execution_evidence_contract_version": VERSION,
           "official_scorer_evidence": {"path":str(scorer.resolve()), "sha256":hashlib.sha256(scorer.read_bytes()).hexdigest(),
             "trajectory_id":f"evaluation:{arm}:{task}:trial={trial}:seed={seed}", "task_id":task,
             "pass_count":1,"fail_count":0,"official_score":1.0,"score_phase":"post_trajectory",
             "history_sha256":hashlib.sha256(json.dumps(history, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}}
    if not valid: row["history_sha256"] = "bad"
    path = root / "artifacts" / task / arm / f"trial-{trial}.json"; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row), encoding="utf-8")
    return path


def _reserve_settle(path: pathlib.Path, call_id: str, role: str, amount: float = 0.1, **metadata) -> None:
    _append(path, {"event": "reserve", "id": call_id, "usd": amount, "role": role, **metadata})
    _append(path, {"event": "settle", "id": call_id, "usd": amount, "role": role, **metadata})


def test_exact_role_mapping_and_cost_reconciliation(tmp_path):
    ledger = _ledger(tmp_path / "ledger.jsonl")
    for arm in ARMS: _reserve_settle(ledger, f"executor-{arm}", f"executor:{arm}:task-0:trial=1:seed=11001")
    _reserve_settle(ledger, "fixed-life", "reme_lifecycle:reme-fixed", .2)
    _reserve_settle(ledger, "dynamic-life", "reme_lifecycle:reme-dynamic", .3)
    _reserve_settle(ledger, "fixed-embed", "reme_embedding:reme-fixed", .02)
    _reserve_settle(ledger, "dynamic-embed", "reme_embedding:reme-dynamic", .03)
    for arm in ARMS: _artifact(tmp_path, arm=arm)
    summary = build_live_summary(ledger_path=ledger, artifact_root=tmp_path / "artifacts", expected_tasks=TASKS,
        expected_seeds=SEEDS, historical_expected_usd=HISTORICAL, state="running")
    assert summary["arms"]["no_memory"]["ExecutorCalls"] == 1
    assert summary["arms"]["official_upstream_reme_fixed"]["LifecycleCalls"] == 1
    assert summary["arms"]["official_upstream_reme_dynamic"]["EmbeddingCalls"] == 1
    assert summary["settled_evaluation_cost"] == pytest.approx(.5 + .2 + .3 + .02 + .03)
    assert summary["total_ledger_exposure"] == pytest.approx(HISTORICAL + summary["settled_evaluation_cost"])


def test_reasoningbank_role_uses_the_new_registered_arm_name(tmp_path):
    ledger = _ledger(tmp_path / "ledger.jsonl")
    _reserve_settle(ledger, "rb-embed", "reasoningbank_embedding", .02)
    arms = {"no_memory", "reasoningbank"}
    summary = build_live_summary(ledger_path=ledger, artifact_root=tmp_path / "artifacts",
        expected_tasks=TASKS, expected_seeds=SEEDS, historical_expected_usd=HISTORICAL,
        registered_arms=arms, state="running")
    assert summary["arms"]["reasoningbank"]["EmbeddingCalls"] == 1


def test_reasoningbank_aliases_cannot_be_registered_together(tmp_path):
    ledger = _ledger(tmp_path / "ledger.jsonl")
    _reserve_settle(ledger, "rb-embed", "reasoningbank_embedding", .02)
    with pytest.raises(LedgerReconciliationError, match="conflicting arm identities"):
        reconcile_ledger(ledger, historical_expected_usd=HISTORICAL,
                         registered_arms={"reasoningbank", "reasoningbank_dynamic"})


@pytest.mark.parametrize("role", ["unknown:call", "reme_lifecycle:reme-dynamic-verifier", "reme_embedding:reme-dynamic-verifier", "copromem_decomposition:worker"])
def test_unknown_verifier_and_decomposition_roles_fail_closed(tmp_path, role):
    ledger = _ledger(tmp_path / "ledger.jsonl"); _reserve_settle(ledger, "bad", role)
    with pytest.raises(LedgerReconciliationError): reconcile_ledger(ledger, historical_expected_usd=HISTORICAL)


@pytest.mark.parametrize("rows", [
    [{"event":"settle","id":"orphan","usd":.1,"role":"executor:no_memory:task-0:trial=1:seed=11001"}],
    [{"event":"reserve","id":"x","usd":.1,"role":"executor:no_memory:task-0:trial=1:seed=11001"}, {"event":"reserve","id":"x","usd":.1,"role":"executor:no_memory:task-0:trial=1:seed=11001"}],
    [{"event":"reserve","id":"x","usd":.1,"role":"executor:no_memory:task-0:trial=1:seed=11001"}, {"event":"settle","id":"x","usd":.1,"role":"executor:no_memory:task-0:trial=1:seed=11001"}, {"event":"settle","id":"x","usd":.1,"role":"executor:no_memory:task-0:trial=1:seed=11001"}],
    [{"event":"reserve","id":"x","usd":-1,"role":"executor:no_memory:task-0:trial=1:seed=11001"}],
])
def test_malformed_duplicate_and_negative_ledger_rows_fail_closed(tmp_path, rows):
    ledger = _ledger(tmp_path / "ledger.jsonl"); [_append(ledger, row) for row in rows]
    with pytest.raises(LedgerReconciliationError): reconcile_ledger(ledger, historical_expected_usd=HISTORICAL)


def test_unresolved_is_visible_and_final_is_prohibited(tmp_path):
    ledger = _ledger(tmp_path / "ledger.jsonl")
    _append(ledger, {"event":"reserve", "id":"open", "usd":.1, "role":"executor:no_memory:task-0:trial=1:seed=11001"})
    _artifact(tmp_path)
    summary = build_live_summary(ledger_path=ledger, artifact_root=tmp_path / "artifacts", expected_tasks=TASKS,
        expected_seeds=SEEDS, historical_expected_usd=HISTORICAL, state="running")
    assert summary["unresolved_reservation_ids"] == ["open"]
    with pytest.raises(LedgerReconciliationError):
        build_live_summary(ledger_path=ledger, artifact_root=tmp_path / "artifacts", expected_tasks=TASKS,
            expected_seeds=SEEDS, historical_expected_usd=HISTORICAL, state="completed", final=True)


def test_multiple_executor_calls_model_provider_mismatch_and_missing_evidence(tmp_path):
    ledger = _ledger(tmp_path / "ledger.jsonl")
    _reserve_settle(ledger, "one", "executor:no_memory:task-0:trial=1:seed=11001", .1, model="m", provider="deepseek")
    _reserve_settle(ledger, "two", "executor:no_memory:task-0:trial=1:seed=11001", .2, model="m", provider="deepseek")
    artifact = _artifact(tmp_path)
    summary = build_live_summary(ledger_path=ledger, artifact_root=tmp_path / "artifacts", expected_tasks=TASKS,
        expected_seeds=SEEDS, historical_expected_usd=HISTORICAL, state="running")
    assert summary["arms"]["no_memory"]["ExecutorCalls"] == 2
    evidence = pathlib.Path(json.loads(artifact.read_text())["execution_evidence_path"]); evidence.unlink()
    with pytest.raises(LedgerReconciliationError, match="journal"):
        build_live_summary(ledger_path=ledger, artifact_root=tmp_path / "artifacts", expected_tasks=TASKS,
            expected_seeds=SEEDS, historical_expected_usd=HISTORICAL, state="running")
    bad = _ledger(tmp_path / "mismatch.jsonl")
    _append(bad, {"event":"reserve","id":"m","usd":.1,"role":"executor:no_memory:task-0:trial=1:seed=11001","model":"a"})
    _append(bad, {"event":"settle","id":"m","usd":.1,"role":"executor:no_memory:task-0:trial=1:seed=11001","model":"b"})
    with pytest.raises(LedgerReconciliationError, match="model"):
        reconcile_ledger(bad, historical_expected_usd=HISTORICAL)


def test_invalid_history_duplicate_artifact_and_predecessor_files_are_excluded(tmp_path):
    ledger = _ledger(tmp_path / "ledger.jsonl")
    _artifact(tmp_path, valid=False)
    with pytest.raises(LedgerReconciliationError, match="history"):
        build_live_summary(ledger_path=ledger, artifact_root=tmp_path / "artifacts", expected_tasks=TASKS,
            expected_seeds=SEEDS, historical_expected_usd=HISTORICAL, state="running")
    root = tmp_path / "valid"; ledger = _ledger(root / "ledger.jsonl"); original = _artifact(root)
    duplicate = root / "artifacts" / TASKS[0] / "no_memory" / "duplicate.json"; duplicate.write_bytes(original.read_bytes())
    with pytest.raises(LedgerReconciliationError, match="duplicate"):
        build_live_summary(ledger_path=ledger, artifact_root=root / "artifacts", expected_tasks=TASKS,
            expected_seeds=SEEDS, historical_expected_usd=HISTORICAL, state="running")


def test_restart_is_deterministic_and_atomic_replacement(tmp_path):
    ledger = _ledger(tmp_path / "ledger.jsonl"); _reserve_settle(ledger, "executor", "executor:no_memory:task-0:trial=1:seed=11001")
    _artifact(tmp_path)
    first = build_live_summary(ledger_path=ledger, artifact_root=tmp_path / "artifacts", expected_tasks=TASKS,
        expected_seeds=SEEDS, historical_expected_usd=HISTORICAL, state="running")
    second = build_live_summary(ledger_path=ledger, artifact_root=tmp_path / "artifacts", expected_tasks=TASKS,
        expected_seeds=SEEDS, historical_expected_usd=HISTORICAL, state="running")
    assert dict(first) == dict(second)
    output = tmp_path / "live-summary.json"; write_live_summary(output, first, updated_ns=7)
    assert json.loads(output.read_text())["updated_ns"] == 7 and not output.with_suffix(".json.tmp").exists()


def test_predecessor_artifacts_are_not_in_current_artifact_root(tmp_path):
    predecessor = tmp_path / "evaluation-002"; _artifact(predecessor)
    current = tmp_path / "evaluation-004"; ledger = _ledger(current / "ledger.jsonl")
    summary = build_live_summary(ledger_path=ledger, artifact_root=current / "artifacts", expected_tasks=TASKS,
        expected_seeds=SEEDS, historical_expected_usd=HISTORICAL, state="running")
    assert summary["completed"] == 0


def test_final_60_of_60_invariant(tmp_path):
    ledger = _ledger(tmp_path / "ledger.jsonl")
    for arm in ARMS:
        for task in TASKS:
            for trial, seed in enumerate(SEEDS, 1):
                _artifact(tmp_path, arm=arm, task=task, trial=trial, seed=seed)
                _reserve_settle(ledger, f"{arm}-{task}-{trial}", f"executor:{arm}:{task}:trial={trial}:seed={seed}", .001)
    summary = build_live_summary(ledger_path=ledger, artifact_root=tmp_path / "artifacts", expected_tasks=TASKS,
        expected_seeds=SEEDS, historical_expected_usd=HISTORICAL, state="completed", final=True)
    assert summary["completed"] == 60 and all(row["Completed"] == 12 for row in summary["arms"].values())

def test_copromem_only_summary_attributes_reme_backend_embedding_to_the_sole_copromem_arm(tmp_path):
    ledger = _ledger(tmp_path / "ledger.jsonl")
    arm = "copromem_v6_2_5_dynamic"
    _reserve_settle(ledger, "executor", f"executor:{arm}:task-0:trial=1:seed=11001", .1)
    _reserve_settle(ledger, "backend", "reme_embedding:reme-fixed", .02)
    _artifact(tmp_path, arm=arm)
    summary = build_live_summary(ledger_path=ledger, artifact_root=tmp_path / "artifacts",
        expected_tasks=TASKS, expected_seeds=SEEDS, historical_expected_usd=HISTORICAL,
        registered_arms={arm}, state="running")
    assert summary["arms"][arm]["EmbeddingCalls"] == 1
    assert summary["arms"][arm]["TotalCost"] == pytest.approx(.12)
    assert summary["settled_evaluation_cost"] == pytest.approx(.12)

def test_reme_backend_without_a_standard_or_sole_copromem_owner_fails_closed(tmp_path):
    ledger = _ledger(tmp_path / "ledger.jsonl")
    _reserve_settle(ledger, "backend", "reme_embedding:reme-fixed", .02)
    with pytest.raises(LedgerReconciliationError, match="unambiguous registered owner"):
        reconcile_ledger(ledger, historical_expected_usd=HISTORICAL, registered_arms={"no_memory"})
