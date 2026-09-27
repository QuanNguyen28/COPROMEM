"""Offline unit coverage for the sanitized v4 publication generator."""
from __future__ import annotations

import importlib.util
import pathlib

import pytest


SOURCE = pathlib.Path(__file__).parents[2] / "research/reme_copromem_fixed_dynamic_v4_results/build_v4_results.py"
SPEC = importlib.util.spec_from_file_location("v4_results", SOURCE)
assert SPEC and SPEC.loader
v4_results = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v4_results)


def test_report_digest_uses_the_executor_canonical_unicode_serialization() -> None:
    history = [{"role": "user", "content": "Hà Nội — café"}]
    assert v4_results.canonical_digest(history) == v4_results.sha256_bytes(
        b'[{"content":"H\xc3\xa0 N\xe1\xbb\x99i \xe2\x80\x94 caf\xc3\xa9","role":"user"}]'
    )


def test_display_table_is_a_reconciliation_target_not_a_source() -> None:
    aggregate = {
        "copromem_dynamic": {"successes": 48, "avg_score": 0.859227, "success_rate": 0.75, "avg_actions_all": 15.921},
        "copromem_fixed": {"successes": 43, "avg_score": 0.846999, "success_rate": 0.671875, "avg_actions_all": 17.781},
        "no_memory": {"successes": 49, "avg_score": 0.875006, "success_rate": 0.765625, "avg_actions_all": 17.328},
        "official_upstream_reme_dynamic": {"successes": 42, "avg_score": 0.798699, "success_rate": 0.65625, "avg_actions_all": 16.688},
        "official_upstream_reme_fixed": {"successes": 50, "avg_score": 0.873681, "success_rate": 0.78125, "avg_actions_all": 17.75},
    }
    v4_results.verify_display_reconciliation(aggregate)
    aggregate["no_memory"]["successes"] = 48
    with pytest.raises(RuntimeError, match="reconciliation"):
        v4_results.verify_display_reconciliation(aggregate)


def test_clustered_statistics_are_deterministic_and_offline() -> None:
    clusters = {"task-a": [0.0, 1.0], "task-b": [1.0, 1.0]}
    assert v4_results.clustered_bootstrap(clusters, iterations=10) == v4_results.clustered_bootstrap(clusters, iterations=10)
    assert v4_results.exact_cluster_signflip(clusters) == 0.5
    assert v4_results.holm_adjust({"a": 0.01, "b": 0.04}) == {"a": 0.02, "b": 0.04}
