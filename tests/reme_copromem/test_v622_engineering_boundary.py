from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from copromem.contrastive_graph_v6 import Graph, commit, digest
from copromem.experiments.reme_copromem.copromem_dynamic_checkpoint import (
    CoProMemDynamicCheckpointError,
    CoProMemDynamicCheckpointManager,
)
from copromem.semantic_graph_v61 import semantic_plan
from scripts import run_v622_semantic_spine_engineering as runner
from copromem.experiments.reme_copromem import task_conditioned_retrieval_v622 as v622
from copromem.experiments.reme_copromem import task_conditioned_retrieval_v621 as v621

from .test_v622_semantic_spine_retrieval import QUERY, REGISTRY, _schema, _state


def test_versioned_runner_uses_v622_retrieval_and_reproduces_before_dispatch():
    state = _state(_schema(required=["apis.docs.browse", "apis.music.search_artist",
                                      "apis.music.follow_artist"]))
    guidance, provenance = runner._retrieval_record(
        state=state, query_operations=QUERY["canonical_query_operations"],
        registry_sha256=REGISTRY["registry_sha256"], task_query=QUERY, callable_registry=REGISTRY)
    assert guidance == v622.reproduce_retrieval(state, QUERY, REGISTRY, provenance)
    assert "apis.docs.browse" not in guidance
    assert provenance["policy_version"] == v622.POLICY_VERSION
    assert runner.PROTOCOL.startswith("v6_2_2_")
    assert all("v6_2_2" in arm for arm in runner.ARMS if arm.startswith("copromem"))


def test_versioned_runner_rejects_old_allocation_and_binds_new_policy(tmp_path):
    bank = tmp_path / "bank"; bank.mkdir()
    for name, value in (("fixed-bank.json", {}), ("semantic-admission-gate.json", {"passed": True}),
                        ("recovery-report.json", {})):
        (bank / name).write_text(json.dumps(value), encoding="utf-8")
    audit = {"selected_task_ids": ["one", "two", "three"], "payloads_opened": False,
             "selection_source": "public_pre_execution_metadata_only", "compatible_task_count": 2,
             "negative_control_count": 1, "historical_settled_exposure_usd": 0.0,
             "copromem_bank": {"path": str(bank.resolve()),
                 "fixed_bank_file_sha256": runner.base.file_sha(bank / "fixed-bank.json"),
                 "admission_gate_file_sha256": runner.base.file_sha(bank / "semantic-admission-gate.json"),
                 "recovery_report_file_sha256": runner.base.file_sha(bank / "recovery-report.json")}}
    path = tmp_path / runner.ALLOCATION_NAME
    path.write_text(json.dumps(audit), encoding="utf-8")
    with pytest.raises(RuntimeError, match="semantic-spine policy"):
        runner._configure(tmp_path)
    audit["retrieval_policy_version"] = v622.POLICY_VERSION
    path.write_text(json.dumps(audit), encoding="utf-8")
    names = ("PROTOCOL", "ARMS", "COPRO_FIXED_ARM", "COPRO_DYNAMIC_ARM", "HISTORICAL_EXPOSURE",
             "derive_task_query", "validate_task_query", "retrieval_record", "reproduce_retrieval",
             "semantic_task_batch_update", "COPRO", "identities")
    before = {name: getattr(runner.base, name) for name in names}
    try:
        runner._configure(tmp_path)
        assert runner.base.retrieval_record is runner._retrieval_record
        assert runner.base.semantic_task_batch_update is runner.semantic_spine_task_batch_update
        assert runner.base.COPRO_FIXED_ARM == "copromem_v6_2_2_fixed"
        assert runner.base.HISTORICAL_EXPOSURE == 0.0
    finally:
        for name, value in before.items():
            setattr(runner.base, name, value)


def _learned_bank() -> tuple[dict, dict]:
    nodes = tuple(
        {"operation": operation, "effect_class": effect, "public_required": required,
         "output_slots": output, "index": index}
        for index, (operation, effect, required, output) in enumerate((
            ("apis.music.search_artist", "read", [], ["artist_id"]),
            ("apis.music.follow_artist", "write", ["artist_id"], ["followed"]),
        ))
    )
    graph = Graph("public-registry", nodes, (), digest({"nodes": nodes}))
    audit = {"semantic_projection_sha256": "projection", "provenance_sha256": "attested"}
    plan = semantic_plan([graph, graph], [], {}, [audit, audit])
    state, marker = commit({}, plan)
    assert marker["state"] == "committed"
    return state, marker


def test_v622_preserves_v621_learning_commit_bank_format_and_state_hashes():
    state, marker = _learned_bank()
    before = copy.deepcopy(state)
    before_hash = digest(before)
    guidance, provenance = v622.retrieve(state, QUERY, REGISTRY)
    assert guidance
    assert state == before and digest(state) == before_hash
    assert marker["after_state_sha256"] == before_hash
    assert set(state) == {"contrastive_v6_schemas"}
    schema_id = marker["winner_schema_id"]
    assert state["contrastive_v6_schemas"][schema_id]["policy_version"] == "copromem-v6.1-semantic-graph-v1"
    assert v622.reproduce_retrieval(state, QUERY, REGISTRY, provenance) == guidance


def test_v622_leaves_v621_source_and_dynamic_prefix_policy_unchanged(tmp_path):
    v621_path = Path(v621.__file__)
    # This digest pins the frozen v6.2.1 retrieval implementation in this
    # versioned branch; v6.2.2 must be additive rather than a silent rewrite.
    assert hashlib.sha256(v621_path.read_bytes()).hexdigest() == "5229fc831fd505f3edddecdcf1506524dae13f298a52464228af13c800123ca3"
    root = Path(__file__).resolve().parents[2]
    frozen_common_core = {
        "src/copromem/contrastive_graph_v6.py": "79cadedf2a46808d2ce5955ec3d2674198d6abc6cbaefdcc2fc5b70c47a14bba",
        "src/copromem/semantic_graph_v61.py": "a7a218b607471a019e4fea352decad5196189bd10116efcbf36bfb368116b287",
        "src/copromem/experiments/reme_copromem/copromem_dynamic_checkpoint.py": "2104f937e0e5ea6b930135399ab1b39f2e4e65c5357fb0093b056d99c6f6c949",
    }
    for relative, expected in frozen_common_core.items():
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == expected
    assert v622.frozen_policy()["dynamic"] == v621.frozen_policy()["dynamic"] == "exact_durable_pre_task_prefix_only"
    state, _marker = _learned_bank()
    manager = CoProMemDynamicCheckpointManager(
        root=tmp_path / "dynamic", manifest_sha256="m" * 64, source_identity_sha256="s" * 64,
        registry_sha256="public-registry", ordered_tasks=["task-1"],
        fixed_initial_state=state, dynamic_initial_state=state,
    )
    manager.freeze_task_pre_state("task-1", state)
    with pytest.raises(CoProMemDynamicCheckpointError, match="absent"):
        manager.record("task-1", "trajectories_complete", artifact_hashes=[], scorer_evidence_hashes=[])
    prefix = manager.reconcile(ledger_reconciled=True, fixed_current_state=state)
    assert prefix["next_transition"] == "retrievals_materialized"
