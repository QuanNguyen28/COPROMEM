from __future__ import annotations

import hashlib
import json
import pathlib

import pytest

from copromem.experiments.reme_copromem.evidence_contract import (
    EvidenceContractError, VERSION, bind, load_artifact, validate,
)


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
