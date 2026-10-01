"""Zero-provider regression coverage for the v6.2.1 engineering-003 audit."""
from __future__ import annotations

import importlib.util
import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "audit_v621_engineering_003.py"


def _module():
    spec = importlib.util.spec_from_file_location("audit_v621_engineering_003", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_completed_engineering_run_passes_sanitized_terminal_audit() -> None:
    audit = _module().audit()
    assert audit["interpretation"]["classification"] == "ENGINEERING-VALIDATED"
    assert audit["integrity"]["unique_registered_trajectories"] == 30
    assert audit["integrity"]["ledger"]["unresolved_reservation_count"] == 0
    assert len(audit["copromem_retrieval_rows"]) == 12
    assert len(audit["reme_retrieval_rows"]) == 12


def test_retrieval_gate_distinguishes_compatible_and_negative_control() -> None:
    audit = _module().audit()
    gates = audit["copromem_gates"]
    assert gates["compatible_nonempty_and_selected"] is True
    assert gates["negative_control_empty_and_unselected"] is True
    assert gates["negative_prompt_identical_to_no_memory"] is True
    assert gates["offline_reproduction"] is True
    for row in audit["copromem_retrieval_rows"]:
        if row["compatibility_class"] == "negative_control":
            assert row["guidance_nonempty"] is False
            assert row["selected_schema_id"] is None


def test_dynamic_prefix_and_reme_online_chain_are_durable() -> None:
    audit = _module().audit()
    boundaries = audit["copromem_dynamic_boundaries"]
    assert all(row["both_trials_scored_before_update"] for row in boundaries)
    assert all(row["commit_persisted"] and row["post_state_persisted"] for row in boundaries)
    markers = audit["reme_dynamic_checkpoint_chain"]
    assert [row["update_index"] for row in markers] == list(range(1, 7))
    assert all(row["post_state_semantic_sha256"] for row in markers)
