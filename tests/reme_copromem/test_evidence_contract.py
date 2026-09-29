from __future__ import annotations

import hashlib
import json
import pathlib

import pytest

from copromem.experiments.reme_copromem.evidence_contract import (
    EvidenceContractError, VERSION, bind, bind_zero_action, load_artifact, validate,
)
from copromem.integrations.reme.upstream_executor import AppWorldProxy


REGISTRY = "09325ae59f351b4b18ae5127a456890c844515b872277ba4c133ffbd9c5c4423"


def _fixture(tmp_path: pathlib.Path) -> tuple[pathlib.Path, dict[str, object]]:
    journal = tmp_path / "journals" / "evaluation_no_memory_fixture.execution-evidence.jsonl"
    journal.parent.mkdir(parents=True)
    # Sanitized metadata only; it intentionally contains no task instruction.
    journal.write_text('{"monotonic_index":0,"callable_registry_sha256":"%s"}\n' % REGISTRY, encoding="utf-8")
    row = bind(journal=journal, run_root=tmp_path, registry_sha256=REGISTRY)
    return journal, row


def test_valid_sanitized_evaluation_004_metadata_is_accepted(tmp_path):
    journal, row = _fixture(tmp_path)
    assert row["execution_evidence_contract_version"] == VERSION
    assert validate(row, run_root=tmp_path, expected_registry_sha256=REGISTRY) == journal.resolve()
    assert row["execution_evidence_sha256"] == hashlib.sha256(journal.read_bytes()).hexdigest()
    assert row["execution_evidence_rows"] == 1


@pytest.mark.parametrize("field,value", [
    ("execution_evidence_path", None),
    ("execution_evidence_sha256", "0" * 64),
    ("execution_evidence_rows", 2),
    ("execution_evidence_registry_sha256", "different"),
    ("execution_evidence_run_relative", "elsewhere/journal.jsonl"),
    ("execution_evidence_contract_version", "unknown"),
])
def test_missing_or_conflicting_contract_fields_fail_closed(tmp_path, field, value):
    _journal, row = _fixture(tmp_path)
    row[field] = value
    with pytest.raises(EvidenceContractError):
        validate(row, run_root=tmp_path, expected_registry_sha256=REGISTRY)


def test_duplicate_or_renamed_fields_are_rejected(tmp_path):
    journal, row = _fixture(tmp_path)
    artifact = tmp_path / "artifact.json"
    artifact.write_text(
        '{"execution_evidence_path":%s,"execution_evidence_path":"renamed",'
        '"execution_evidence_sha256":%s}' % (json.dumps(str(journal)), json.dumps(row["execution_evidence_sha256"])),
        encoding="utf-8",
    )
    with pytest.raises(EvidenceContractError, match="duplicate"):
        load_artifact(artifact)
    renamed = dict(row); renamed["evidence_path"] = renamed.pop("execution_evidence_path")
    with pytest.raises(EvidenceContractError, match="missing"):
        validate(renamed, run_root=tmp_path)


def test_artifact_to_journal_binding_rejects_tamper(tmp_path):
    journal, row = _fixture(tmp_path)
    journal.write_text('{"tampered":true}\n', encoding="utf-8")
    with pytest.raises(EvidenceContractError, match="hash"):
        validate(row, run_root=tmp_path)


def _zero_action_fixture(tmp_path: pathlib.Path) -> dict[str, object]:
    manifest = {"git_commit": "frozen-source"}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "runtime-identity.json").write_text(json.dumps({"runtime": "fixture"}), encoding="utf-8")
    journal = tmp_path / "journals" / "telemetry.jsonl"; journal.parent.mkdir()
    journal.write_bytes(b"")
    scorer = tmp_path / "journals" / "scorer.jsonl"
    scorer.write_text(json.dumps({"event":"official_score", "trajectory_id":"evaluation:no_memory:t:trial=1:seed=1",
                                  "task_id":"t", "pass_count":1,"fail_count":0,
                                  "score_phase":"post_trajectory"}) + "\n", encoding="utf-8")
    call_id = "executor-call"
    (tmp_path / "ledger.jsonl").write_text(
        json.dumps({"event":"reserve","id":call_id,"role":"executor:no_memory:t:trial=1:seed=1"}) + "\n" +
        json.dumps({"event":"settle","id":call_id,"role":"executor:no_memory:t:trial=1:seed=1","usd":0.01}) + "\n",
        encoding="utf-8")
    (tmp_path / "progress.jsonl").write_text(json.dumps(
        {"event":"call_settled", "id":call_id, "finish_reason":"length", "completion_tokens":2048,
         "tool_call_present":False, "content_sha256":"a" * 64}) + "\n", encoding="utf-8")
    return bind_zero_action(
        journal=journal, scorer_journal=scorer, run_root=tmp_path, registry_sha256=REGISTRY,
        trajectory_id="evaluation:no_memory:t:trial=1:seed=1", after_score=1.0,
        termination="truncation_termination",
        executor_record={"id":call_id,"finish_reason":"length","completion_tokens":2048,
                         "tool_call_present":False,"content_sha256":"a" * 64},
        manifest_sha256=hashlib.sha256((tmp_path / "manifest.json").read_bytes()).hexdigest(),
        source_commit="frozen-source", task_id="t", arm="no_memory", trial_id=1, seed=1,
        history_sha256="history", runtime_identity_sha256=hashlib.sha256(
            (tmp_path / "runtime-identity.json").read_bytes()).hexdigest())


def test_settled_length_terminal_zero_action_is_canonically_bound(tmp_path):
    row = _zero_action_fixture(tmp_path)
    row.update({"trajectory_id":"evaluation:no_memory:t:trial=1:seed=1", "task_id":"t", "arm":"no_memory",
                "trial_id":1, "seed":1, "history_sha256":"history", "after_score":1.0})
    assert row["execution_evidence_rows"] == 0
    assert validate(row, run_root=tmp_path, expected_registry_sha256=REGISTRY).read_bytes() == b""


@pytest.mark.parametrize("mutation", ["score", "termination", "settlement", "trajectory"])
def test_zero_action_tampering_fails_closed(tmp_path, mutation):
    row = _zero_action_fixture(tmp_path)
    row.update({"trajectory_id":"evaluation:no_memory:t:trial=1:seed=1", "task_id":"t", "arm":"no_memory",
                "trial_id":1, "seed":1, "history_sha256":"history", "after_score":1.0})
    if mutation == "score": row["after_score"] = 0.0
    elif mutation == "trajectory": row["trajectory_id"] = "other"
    else:
        zero = dict(row["zero_action_evidence"])
        zero["termination" if mutation == "termination" else "executor_settlement_id"] = "completed" if mutation == "termination" else "other"
        row["zero_action_evidence"] = zero
    with pytest.raises(EvidenceContractError):
        validate(row, run_root=tmp_path)


def test_nonzero_action_or_normal_empty_journal_is_rejected(tmp_path):
    row = _zero_action_fixture(tmp_path)
    row.update({"trajectory_id":"evaluation:no_memory:t:trial=1:seed=1", "task_id":"t", "arm":"no_memory",
                "trial_id":1, "seed":1, "history_sha256":"history", "after_score":1.0, "actions":1})
    with pytest.raises(EvidenceContractError):
        # The contract does not trust an artifact's action count alone; a
        # normal termination cannot receive the registered zero-action proof.
        zero = dict(row["zero_action_evidence"]); zero["termination"] = "completed"; row["zero_action_evidence"] = zero
        validate(row, run_root=tmp_path)


def test_terminal_score_phase_selects_post_trajectory_score(tmp_path):
    journal = tmp_path / "journal.jsonl"; journal.write_text('{"event":"response_attested"}\n', encoding="utf-8")
    scorer = tmp_path / "scorer.jsonl"
    scorer.write_text("\n".join(json.dumps(row) for row in [
        {"event": "official_score", "trajectory_id": "trajectory", "task_id": "task", "pass_count": 0,
         "fail_count": 1, "score_phase": "pre_trajectory"},
        {"event": "official_score", "trajectory_id": "trajectory", "task_id": "task", "pass_count": 1,
         "fail_count": 0, "score_phase": "post_trajectory"},
    ]) + "\n", encoding="utf-8")
    row = {"trajectory_id": "trajectory", "task_id": "task", "after_score": 1.0,
           "history_sha256": "history", **bind(journal=journal, run_root=tmp_path, registry_sha256=REGISTRY,
           scorer_journal=scorer, trajectory_id="trajectory", task_id="task", after_score=1.0,
           history_sha256="history")}
    assert row["official_scorer_evidence"]["score_phase"] == "post_trajectory"
    assert validate(row, run_root=tmp_path, expected_registry_sha256=REGISTRY) == journal.resolve()


def test_ambiguous_terminal_score_phase_fails_closed(tmp_path):
    journal = tmp_path / "journal.jsonl"; journal.write_text('{"event":"response_attested"}\n', encoding="utf-8")
    scorer = tmp_path / "scorer.jsonl"
    scorer.write_text("\n".join(json.dumps({"event": "official_score", "trajectory_id": "trajectory",
        "task_id": "task", "pass_count": 1, "fail_count": 0, "score_phase": "post_trajectory"}) for _ in range(2)) + "\n", encoding="utf-8")
    with pytest.raises(EvidenceContractError, match="terminal scorer"):
        bind(journal=journal, run_root=tmp_path, registry_sha256=REGISTRY, scorer_journal=scorer,
             trajectory_id="trajectory", task_id="task", after_score=1.0, history_sha256="history")


def test_proxy_produces_one_explicit_terminal_score_phase(tmp_path, monkeypatch):
    journal = tmp_path / "proxy-scorer.jsonl"
    proxy = AppWorldProxy.__new__(AppWorldProxy)
    proxy.task_id = "task"; proxy.journal_trajectory_id = "trajectory"; proxy.journal_path = journal
    proxy._score_phase = "pre_trajectory"
    monkeypatch.setattr(proxy, "_send", lambda _request: {"pass_count": 1, "fail_count": 0})
    proxy.evaluate(); proxy.mark_post_trajectory_score(); proxy.evaluate()
    phases = [json.loads(line)["score_phase"] for line in journal.read_text(encoding="utf-8").splitlines()]
    assert phases == ["pre_trajectory", "post_trajectory"]


@pytest.mark.parametrize("mutation", ["finish_reason", "completion_tokens", "tool_call", "scorer", "settlement", "runtime"])
def test_zero_action_required_bindings_fail_closed(tmp_path, mutation):
    row = _zero_action_fixture(tmp_path)
    row.update({"trajectory_id":"evaluation:no_memory:t:trial=1:seed=1", "task_id":"t", "arm":"no_memory",
                "trial_id":1, "seed":1, "history_sha256":"history", "after_score":1.0})
    if mutation == "scorer":
        scorer = pathlib.Path(row["zero_action_evidence"]["scorer_evidence_path"])
        scorer.write_text(json.dumps({"event":"official_score", "trajectory_id":"evaluation:no_memory:t:trial=1:seed=1",
                                      "task_id":"t", "pass_count":0, "fail_count":1,
                                      "score_phase":"post_trajectory"}) + "\n", encoding="utf-8")
    elif mutation == "settlement":
        (tmp_path / "ledger.jsonl").write_text("", encoding="utf-8")
    elif mutation == "runtime":
        (tmp_path / "runtime-identity.json").write_text('{"runtime":"tampered"}', encoding="utf-8")
    else:
        progress = json.loads((tmp_path / "progress.jsonl").read_text(encoding="utf-8"))
        progress[{"finish_reason": "finish_reason", "completion_tokens": "completion_tokens", "tool_call": "tool_call_present"}[mutation]] = (
            "stop" if mutation == "finish_reason" else (2047 if mutation == "completion_tokens" else True))
        (tmp_path / "progress.jsonl").write_text(json.dumps(progress) + "\n", encoding="utf-8")
    with pytest.raises(EvidenceContractError):
        validate(row, run_root=tmp_path, expected_registry_sha256=REGISTRY)
