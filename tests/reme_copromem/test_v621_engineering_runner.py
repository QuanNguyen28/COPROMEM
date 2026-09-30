from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from copromem.experiments.reme_copromem.task_conditioned_retrieval_v621 import derive_task_query


def _runner():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("v621_runner", root / "scripts/run_v621_task_conditioned_retrieval_engineering.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_engineering_runner_requires_preregistered_two_compatible_one_negative_audit(tmp_path: Path):
    runner = _runner()
    (tmp_path / "allocation-audit.json").write_text(json.dumps({
        "selected_task_ids": ["a", "b", "c"], "payloads_opened": False,
        "selection_source": "public_pre_execution_metadata_only", "compatible_task_count": 2,
        "negative_control_count": 1, "split": "test_normal",
    }), encoding="utf-8")
    runner._configure(tmp_path)
    assert runner.base.PROTOCOL == runner.PROTOCOL
    assert runner.base.COPRO_FIXED_ARM == "copromem_v6_2_1_fixed"
    assert runner.base.COPRO_DYNAMIC_ARM == "copromem_v6_2_1_dynamic"


def test_engineering_adapter_requires_and_uses_the_frozen_registry():
    registry = {"registry_sha256": "r", "normalization": {"operation_aliases": {}},
                "operations": [{"operation": "apis.spotify.update_playlist", "app": "spotify"}], "dependency_edges": []}
    query = derive_task_query("Update Spotify playlist", "appworld", {"app_descriptions": {"spotify": "public"}}, registry)
    state = {"contrastive_v6_schemas": {"schema": {
        "policy_version": "copromem-v6.1-semantic-graph-v1", "registry_sha256": "r",
        "required_operations": ["apis.spotify.update_playlist"], "terminal_effect": "apis.spotify.update_playlist",
        "typed_constraints": [{"operation": "apis.spotify.update_playlist", "required": [], "outputs": ["message"]}],
        "support": {"successes": 2, "failures": 0, "failure_counts": {}},
    }}}
    runner = _runner()
    guidance, provenance = runner._retrieval_record(state=state, query_operations=query["canonical_query_operations"],
        registry_sha256="r", task_query=query, callable_registry=registry)
    assert guidance and provenance["selected_schema_id"] == "schema"
