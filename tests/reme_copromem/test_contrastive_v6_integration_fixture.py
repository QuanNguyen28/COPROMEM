"""Zero-provider end-to-end checks for v6 contrastive graph memory."""
from __future__ import annotations

import copy
import shutil
import uuid
from pathlib import Path

import pytest

from copromem.benchmarks.appworld.execution_evidence import partition_v6_graph_evidence
from copromem.contrastive_graph_v6 import build_graph, commit, digest, plan_task_batch, reproduce_retrieval, retrieve
from copromem.experiments.reme_copromem.contrastive_v6_integration_fixture import (
    FIXTURE_ID,
    fixture_registry,
    run_fixture,
    run_restart_drills,
    run_telemetry_equivalence,
)
from copromem.experiments.reme_copromem.contrastive_v6_runner import fresh_state


def _root(name: str) -> Path:
    # `journal_records` intentionally requires the real E-backed persistence
    # boundary.  Never use /tmp for this integration test.
    root = Path(__file__).resolve().parents[2] / "artifacts" / "zero-cost-validation" / f"{name}-{uuid.uuid4().hex}"
    assert str(root).startswith("/mnt/e/")
    return root


def test_v6_fixture_proves_production_lifecycle_restart_and_a_to_b_retrieval():
    root = _root("v6-fixture")
    try:
        final = run_fixture(root)
        restarts = run_restart_drills(root / "restarts")
        equivalence = run_telemetry_equivalence(root)
        assert final["fixture_id"] == FIXTURE_ID
        assert final["provider_calls"] == 0 and final["ledger"]["unresolved"] == 0
        assert final["a_scores"] == [1.0, 1.0, 0.0]
        assert final["schema_id"]
        assert final["negative_fallback"] == "empty"
        assert len(restarts["rows"]) == 7
        assert equivalence["telemetry_on_return_sha256"] == equivalence["telemetry_off_return_sha256"]
        assert equivalence["public_call_events"] == 5
        assert (root / "state-machine-transition-record.json").exists()
        assert (root / "promoted-schema-audit.json").exists()
        assert (root / "a-to-b-retrieval-audit.json").exists()
        assert (root / "restarts" / "restart-replay-matrix.json").exists()
        state = __import__("json").loads((root / "state-machine" / "fixture-A" / "commit_persisted.json").read_text())["post_state"]
        assert "fixture-item" not in repr(state)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _event(registry: dict, *, operation: str, index: int, success: bool = True, accepted: bool = True) -> dict:
    meta = next(item for item in registry["operations"] if item["operation"] == operation)
    signature = {"operation": operation, "application": "demo", "callable_name": meta["function_name"],
                 "public_required": list(meta["required_parameters"]), "output_slots": list(meta["output_slots"])}
    event = {"version": "public-execution-evidence-v1", "parent_program_id": "negative", "monotonic_index": index,
             "callable_registry_sha256": registry["registry_sha256"], "schema_accepted": accepted,
             "response_success": success, "response_error_class": None if success else "http_400",
             "operation_signature": signature, "invocation_value_hashes": {"item_id": digest("abstract-value")},
             "response_output_value_hashes": {"item_id": digest("abstract-value")} if meta["output_slots"] else {}}
    event["event_sha256"] = digest(event)
    return event


def test_v6_negative_controls_fail_closed_and_fixed_retrieval_does_not_mutate():
    registry = fixture_registry()
    one = build_graph([_event(registry, operation="apis.demo.inspect", index=0), _event(registry, operation="apis.demo.apply_effect", index=1)], registry)
    before = fresh_state(); rejected, marker = commit(before, plan_task_batch([one], [], before))
    assert marker["state"] == "rejected" and rejected == before
    incompatible = build_graph([_event(registry, operation="apis.demo.irrelevant_lookup", index=0)], registry)
    missing_terminal = build_graph([_event(registry, operation="apis.demo.inspect", index=0)], registry)
    no_core = plan_task_batch([one, incompatible], [], before)
    no_terminal = plan_task_batch([missing_terminal, missing_terminal], [], before)
    assert not commit(before, no_core)[1]["state"] == "committed"
    assert commit(before, no_terminal)[1]["state"] == "rejected"
    malformed = _event(registry, operation="apis.demo.inspect", index=0); malformed["event_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="integrity"):
        partition_v6_graph_evidence([malformed], registry["registry_sha256"])
    audit_only = {"version": "public-execution-evidence-v1", "parent_program_id": "audit", "monotonic_index": 0,
                  "callable_registry_sha256": registry["registry_sha256"], "event_kind": "audit"}
    audit_only["event_sha256"] = digest(audit_only)
    eligible, audit = partition_v6_graph_evidence([audit_only], registry["registry_sha256"])
    assert not eligible and audit["audit_only_rows"] == 1
    errored = _event(registry, operation="apis.demo.inspect", index=0, success=False)
    eligible, audit = partition_v6_graph_evidence([errored], registry["registry_sha256"])
    assert not eligible and audit["callable_error_rows"] == 1
    plan = plan_task_batch([one, one], [], before); state, good = commit(before, plan)
    assert good["state"] == "committed"
    frozen = copy.deepcopy(state); guidance, provenance = retrieve(state, ["apis.demo.inspect", "apis.demo.apply_effect"], registry["registry_sha256"])
    assert guidance and state == frozen and reproduce_retrieval(state, ["apis.demo.inspect", "apis.demo.apply_effect"], provenance) == guidance
    tampered = dict(provenance); tampered["guidance_sha256"] = "tampered"
    with pytest.raises(ValueError):
        reproduce_retrieval(state, ["apis.demo.inspect", "apis.demo.apply_effect"], tampered)
    assert "abstract-value" not in repr(state)
