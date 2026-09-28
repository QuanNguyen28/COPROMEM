from __future__ import annotations

import copy
import json
import subprocess
import sys

import pytest

from copromem.experiments.reme_copromem.public_tool_schema_registry import (
    build_public_tool_schema_registry, canonical_operation_signature, invocation_evidence, public_tool_path_audit,
    verify_public_tool_schema_registry,
)


def _openapi(operation_id, *, method, path, required=(), optional=(), outputs=()):
    params = [{"name": item, "required": True, "schema": {"type": "string"}} for item in required]
    params += [{"name": item, "required": False, "schema": {"type": "string"}} for item in optional]
    return {"openapi": "3.1", "paths": {path: {method: {"operationId": operation_id, "parameters": params,
        "responses": {"200": {"content": {"application/json": {"schema": {"type": "object",
        "properties": {item: {"type": "string"} for item in outputs}}}}}}}}}}


def _function(name, parameters, required=()):
    return [{"type": "function", "function": {"name": name, "parameters": {"type": "object",
        "properties": parameters, "required": list(required)}}}]


def _registry(tmp_path):
    openapi = tmp_path / "openapi"; functions = tmp_path / "functions"; openapi.mkdir(); functions.mkdir()
    (openapi / "todo.json").write_text(json.dumps(_openapi("todo__show_items", method="get", path="/items", outputs=("item_id",))), encoding="utf-8")
    (openapi / "task.json").write_text(json.dumps(_openapi("task__complete_item", method="post", path="/items/{item_id}", required=("item_id",), outputs=("message",))), encoding="utf-8")
    (functions / "todo.json").write_text(json.dumps(_function("todo__show_items", {"access_token": {"type": "string"}, "filter": {"type": "string"}})), encoding="utf-8")
    (functions / "task.json").write_text(json.dumps(_function("task__complete_item", {"item_id": {"type": "string"}, "access_token": {"type": "string"}}, required=("item_id",))), encoding="utf-8")
    registry = build_public_tool_schema_registry(openapi, functions); verify_public_tool_schema_registry(registry)
    return registry, openapi, functions


def test_required_optional_context_alias_and_evidence_are_canonical(tmp_path):
    registry, _, _ = _registry(tmp_path)
    signature = canonical_operation_signature(registry, "task__complete_item", ["item_id", "access_token", "var_9"],
                                              {"item_id": "string", "access_token": "string"})
    assert signature["operation"] == "apis.task.complete_item" and signature["runtime_context_present"] == ["access_token"]
    assert canonical_operation_signature(registry, "apis.todo.show_items", ["filter", "access_token"])["public_optional_present"] == ["filter"]
    evidence = invocation_evidence(signature, raw_event_digest="a" * 64, concrete_value_digest="b" * 64)
    assert "item-value" not in json.dumps(evidence) and evidence["invocation_evidence_sha256"]


@pytest.mark.parametrize("names,types,error", [
    (["access_token"], {}, "missing required"),
    (["item_id", "unknown"], {}, "unknown undeclared"),
    (["item_id"], {"item_id": "integer"}, "type mismatch"),
])
def test_missing_unknown_and_type_mismatch_fail_closed(tmp_path, names, types, error):
    registry, _, _ = _registry(tmp_path)
    with pytest.raises(ValueError, match=error): canonical_operation_signature(registry, "apis.task.complete_item", names, types)


def test_concrete_values_registry_tamper_and_cross_process_determinism(tmp_path):
    registry, openapi, functions = _registry(tmp_path)
    with pytest.raises(ValueError, match="concrete invocation values"):
        canonical_operation_signature(registry, "apis.task.complete_item", ["item_id"], parameter_values={"item_id": "secret"})
    bad = copy.deepcopy(registry); bad["operations"][0]["parameters"]["access_token"]["kind"] = "public_required"
    with pytest.raises(ValueError, match="hash"):
        verify_public_tool_schema_registry(bad)
    code = ("from copromem.experiments.reme_copromem.public_tool_schema_registry import build_public_tool_schema_registry; "
            "import sys; print(build_public_tool_schema_registry(sys.argv[1],sys.argv[2])['registry_sha256'])")
    output = subprocess.check_output([sys.executable, "-c", code, str(openapi), str(functions)], text=True).strip()
    assert output == registry["registry_sha256"]


def test_runtime_public_schema_hash_mismatch_fails_closed(tmp_path, monkeypatch):
    registry, openapi, functions = _registry(tmp_path)
    monkeypatch.setenv("COPROMEM_RUN_DIR", str(tmp_path / "run"))
    from copromem.experiments.reme_copromem.task_boundary_v6 import verify_runtime_tool_schema
    runtime = {"openapi_root": str(openapi), "function_calling_root": str(functions)}
    verify_runtime_tool_schema(registry, runtime)
    (functions / "task.json").write_text(json.dumps(_function("task__complete_item", {
        "item_id": {"type": "string"}, "access_token": {"type": "string"}, "unexpected_public": {"type": "string"}}, required=("item_id",))), encoding="utf-8")
    with pytest.raises(RuntimeError, match="runtime callable schema"):
        verify_runtime_tool_schema(registry, runtime)


def test_cyclic_public_path_is_rejected(tmp_path):
    registry, _, _ = _registry(tmp_path)
    show = canonical_operation_signature(registry, "todo__show_items", ["access_token"])
    complete = canonical_operation_signature(registry, "task__complete_item", ["item_id"])
    result = public_tool_path_audit(registry, [show, complete, show])
    assert not result["passed"] and result["first_rejection"]["reason"] == "cyclic_or_repeated_operation"
