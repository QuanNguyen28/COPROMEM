from __future__ import annotations

import json

import pytest

from copromem.experiments.reme_copromem.runtime_identity import (
    RuntimeIdentityError, build_runtime_identity, evaluation_runtime_inputs, verify_runtime_identity,
)
from copromem.integrations.reme.bank import semantic_bank_hash
from copromem.integrations.reme.fixed_checkpoint import ReMeFixedIntegrityError, ReMeFixedIntegrityManager


def test_runtime_identity_is_path_independent_and_content_sensitive(tmp_path):
    first, second = tmp_path / "one" / "runner.py", tmp_path / "two" / "runner.py"
    first.parent.mkdir(); second.parent.mkdir(); first.write_text("print('same')\n"); second.write_text("print('same')\n")
    record = build_runtime_identity(content={"runner": first}, labels={"python": "3.test"})
    verify_runtime_identity(record, content={"runner": second}, labels={"python": "3.test"})
    second.write_text("print('changed')\n")
    with pytest.raises(RuntimeIdentityError, match="drift"):
        verify_runtime_identity(record, content={"runner": second}, labels={"python": "3.test"})


def test_missing_identity_and_changed_scorer_are_rejected(tmp_path):
    scorer = tmp_path / "scorer.py"; scorer.write_text("score=1\n")
    record = build_runtime_identity(content={"scorer": scorer})
    with pytest.raises(RuntimeIdentityError):
        verify_runtime_identity(record, content={"scorer": tmp_path / "missing.py"})
    scorer.write_text("score=2\n")
    with pytest.raises(RuntimeIdentityError):
        verify_runtime_identity(record, content={"scorer": scorer})


def test_evaluation_runtime_requires_explicit_roots_before_dispatch(tmp_path, monkeypatch):
    monkeypatch.delenv("COPROMEM_REME_SOURCE", raising=False)
    monkeypatch.delenv("COPROMEM_APPWORLD_ROOT", raising=False)
    with pytest.raises(RuntimeIdentityError, match="explicit"):
        evaluation_runtime_inputs(root=tmp_path)


def test_reme_fixed_checkpoint_is_semantic_and_chain_verified(tmp_path):
    current = [{"memory_id": "m", "text": "stable", "vector": [0.1]}]
    source = tmp_path / "source.jsonl"; source.write_text(json.dumps(current[0]) + "\n")
    def dump(path): path.write_text(source.read_text())
    manager = ReMeFixedIntegrityManager(root=tmp_path / "fixed", frozen_semantic_hash=semantic_bank_hash(source), dump_current=dump)
    first = manager.checkpoint(label="initial")
    second = manager.checkpoint(label="task-0001", predecessor_checkpoint_sha256=first["checkpoint_sha256"])
    assert manager.reconcile() == (first, second)
    source.write_text(json.dumps({**current[0], "text": "mutated"}) + "\n")
    with pytest.raises(ReMeFixedIntegrityError, match="mutated"):
        manager.checkpoint(label="task-0002", predecessor_checkpoint_sha256=second["checkpoint_sha256"])


def test_reme_fixed_forbidden_mutation_role_fails_before_dump(tmp_path):
    source = tmp_path / "source.jsonl"; source.write_text('{"memory_id":"m","vector":[]}\n')
    manager = ReMeFixedIntegrityManager(root=tmp_path / "fixed", frozen_semantic_hash=semantic_bank_hash(source),
                                         dump_current=lambda _path: pytest.fail("must not dump"),
                                         assert_no_mutation_roles=lambda: (_ for _ in ()).throw(ReMeFixedIntegrityError("fixed update role")))
    with pytest.raises(ReMeFixedIntegrityError, match="update role"):
        manager.checkpoint(label="initial")
