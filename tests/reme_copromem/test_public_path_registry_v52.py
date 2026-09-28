from __future__ import annotations

import copy
import json

import pytest

from copromem.experiments.reme_copromem.public_path_registry import (
    REGISTRY_VERSION, build_public_registry, canonical_digest, observed_public_operation_matches, public_path_audit,
    verify_public_registry,
)


def _operation(operation_id, *, method, path, parameters=(), outputs=()):
    schema = {"type": "object", "properties": {item: {"type": "string"} for item in outputs}}
    operation = {"operationId": operation_id, "parameters": list(parameters),
                 "responses": {"200": {"content": {"application/json": {"schema": schema}}}}}
    return {path: {method: operation}}


def _registry(tmp_path):
    doc = {"openapi": "3.1.0", "paths": {}}
    doc["paths"].update(_operation("todo__show_items", method="get", path="/items", outputs=("item_id",)))
    doc["paths"].update(_operation("todo__complete_item", method="post", path="/items/{item_id}/complete",
                                    parameters=({"name": "item_id", "required": True},), outputs=("message",)))
    (tmp_path / "todo.json").write_text(json.dumps(doc), encoding="utf-8")
    registry = build_public_registry(tmp_path)
    verify_public_registry(registry)
    return registry


def test_registry_is_deterministic_content_addressed_and_contains_public_path(tmp_path):
    first = _registry(tmp_path); second = build_public_registry(tmp_path)
    assert first["registry_version"] == REGISTRY_VERSION
    assert first["registry_sha256"] == second["registry_sha256"]
    assert any(edge == {"from_operation": "apis.todo.show_items", "to_operation": "apis.todo.complete_item",
                        "via_slot": "item_id", "kind": "public_schema_flow"}
               for edge in first["dependency_edges"])
    assert all("task" not in json.dumps(row).lower() for row in first["operations"])


def test_complete_observed_read_write_path_passes_without_values(tmp_path):
    registry = _registry(tmp_path)
    result = public_path_audit(registry, [
        {"operation": "apis.todo.show_items", "input_slots": [], "output_slots": ["item_id"], "parameters": {}},
        {"operation": "apis.todo.complete_item", "input_slots": ["item_id"], "output_slots": ["message"], "parameters": {}},
    ])
    assert result["passed"] and len(result["selected_path"]) == 2
    assert result["selected_path_sha256"] == canonical_digest(result["selected_path"])


@pytest.mark.parametrize("events,reason", [
    ([{"operation": "apis.todo.complete_item", "input_slots": ["item_id"], "output_slots": ["message"], "parameters": {}}], "unsatisfied_public_dependency"),
    ([{"operation": "apis.todo.show_items", "input_slots": [], "output_slots": ["item_id"], "parameters": {"item_id": "secret"}}], "concrete_parameters_forbidden"),
    ([{"operation": "apis.todo.show_items", "input_slots": [], "output_slots": ["unknown"], "parameters": {}}], "operation_signature_mismatch"),
])
def test_partial_unsupported_and_value_bearing_paths_fail_closed(tmp_path, events, reason):
    result = public_path_audit(_registry(tmp_path), events)
    assert not result["passed"] and result["first_rejection"]["reason"] == reason


def test_tampered_metadata_hash_and_cycle_are_rejected(tmp_path):
    registry = _registry(tmp_path)
    tampered = copy.deepcopy(registry); tampered["operations"][0]["operation"] = "apis.changed"
    with pytest.raises(ValueError, match="hash"):
        verify_public_registry(tampered)
    cyclic = copy.deepcopy(registry)
    cyclic["dependency_edges"].append({"from_operation": "apis.todo.complete_item", "to_operation": "apis.todo.show_items",
                                        "via_slot": "item_id", "kind": "public_schema_flow"})
    cyclic["registry_sha256"] = canonical_digest({key: value for key, value in cyclic.items() if key != "registry_sha256"})
    with pytest.raises(ValueError, match="cyclic"):
        verify_public_registry(cyclic)


def test_optional_slots_are_not_mandatory_and_alternatives_are_not_semantic_aliases(tmp_path):
    registry = _registry(tmp_path)
    complete = next(row for row in registry["operations"] if row["operation"] == "apis.todo.complete_item")
    assert complete["input_slots"] == ["item_id"] and complete["optional_input_slots"] == []
    assert all(group["semantic_status"] == "schema_compatible_not_semantically_equivalent"
               for group in registry["alternative_groups"])


def test_runtime_variable_and_auth_slots_are_canonicalized_without_values(tmp_path):
    registry = _registry(tmp_path)
    expected = {"operation": "apis.todo.complete_item", "input_slots": ["item_id"], "output_slots": ["message"]}
    ok, audit = observed_public_operation_matches(registry, {
        "operation": "apis.todo.complete_item", "input_slots": ["access_token", "item_id", "var_42"],
        "output_slots": [], "parameters": {"must_not": "be used"},
    }, expected)
    assert ok and audit["canonical_outputs"] == ["message"]
    assert audit["local_slots_omitted"] == ["var_42"] and audit["infrastructure_slots_omitted"] == ["access_token"]
    bad, reason = observed_public_operation_matches(registry, {
        "operation": "apis.todo.complete_item", "input_slots": ["other_public_field"], "output_slots": [], "parameters": {},
    }, expected)
    assert not bad and reason["reason"] == "observed_public_input_signature_mismatch"
