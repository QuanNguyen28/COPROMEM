from __future__ import annotations

import hashlib
import json
from pathlib import Path

from copromem.experiments.reme_copromem.evidence_contract import VERSION, bind
from copromem.experiments.reme_copromem.recovery_import import import_scored_artifact
from copromem.experiments.reme_copromem.live_summary import reconcile_ledger
from copromem.experiments.reme_copromem.runner import AppendOnlyLedger


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def test_import_rebinds_only_derived_journal_locations(tmp_path: Path):
    source, target = tmp_path / "source", tmp_path / "target"
    history = [{"role": "assistant", "content": "call"}]
    history_sha = hashlib.sha256(json.dumps(history, ensure_ascii=False, sort_keys=True,
                                            separators=(",", ":")).encode("utf-8")).hexdigest()
    trajectory = "evaluation:arm:task:trial=1:seed=1"
    execution = source / "journals" / "execution.jsonl"
    scorer = source / "journals" / "scorer.jsonl"
    _write(execution, {"callable_registry_sha256": "registry", "monotonic_index": 0})
    _write(scorer, {"event": "official_score", "score_phase": "post_trajectory", "trajectory_id": trajectory,
                    "task_id": "task", "pass_count": 1, "fail_count": 0})
    artifact = {"arm": "arm", "task_id": "task", "trial_id": 1, "seed": 1, "trajectory_id": trajectory,
                "after_score": 1.0, "actions": 1, "history": history, "history_sha256": history_sha}
    artifact.update(bind(journal=execution, run_root=source, registry_sha256="registry", scorer_journal=scorer,
                         trajectory_id=trajectory, task_id="task", after_score=1.0, history_sha256=history_sha))
    source_artifact = source / "artifacts" / "task" / "arm" / "trial-1.json"
    _write(source_artifact, artifact)
    target_artifact = target / "artifacts" / "task" / "arm" / "trial-1.json"
    record = import_scored_artifact(source_artifact=source_artifact, source_run=source,
                                    target_artifact=target_artifact, target_run=target,
                                    source_manifest_sha256="manifest")
    carried = json.loads(target_artifact.read_text(encoding="utf-8"))
    assert record["source_artifact_sha256"] == _sha(source_artifact)
    assert carried["carried_completed_from"]["source_manifest_sha256"] == "manifest"
    assert carried["execution_evidence_path"].startswith(str(target.resolve()))
    assert _sha(source_artifact) != _sha(target_artifact)
    assert execution.read_bytes() == (target / "journals" / execution.name).read_bytes()


def test_recovery_import_uses_one_historical_carry_and_does_not_recharge_prefix(tmp_path: Path):
    """A successor ledger starts clean; predecessor settlements remain audit evidence."""
    ledger_path = tmp_path / "ledger.jsonl"
    ledger = AppendOnlyLedger(ledger_path, 100.0, {"executor:no_memory:task:trial=1:seed=1": 1.0})
    ledger.reserve("historical-construction-carry", 2.435839694, {"role": "historical_carry_forward"})
    ledger.settle("historical-construction-carry", 2.435839694, {"role": "historical_carry_forward"})
    recovered = reconcile_ledger(ledger_path, historical_expected_usd=2.435839694,
                                 registered_arms={"no_memory"})
    assert not recovered.unresolved_reservation_ids
    assert float(recovered.historical_settled_exposure) == 2.435839694
    assert float(recovered.settled_evaluation_cost) == 0.0
