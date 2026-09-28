"""Content-addressed v5.3 registry from AppWorld's public callable schemas.

OpenAPI describes endpoint and response structure, while AppWorld presents a
separate public function-calling schema to the executor.  This module keeps
those interfaces distinct and combines them only through their public
operation ID.  No task, history, value, scorer, or runtime state is an input.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from .public_path_registry import canonical_bytes, canonical_digest, canonical_operation, canonical_slot


REGISTRY_VERSION = "appworld-public-tool-schema-registry-v5_3"
_METHODS = ("get", "post", "put", "patch", "delete")
_CONTEXT_PARAMETER_NAMES = frozenset({"access_token"})
_LOCAL_BINDING = re.compile(r"^var_[0-9]+$")


def _files(root: Path) -> list[Path]:
    result = sorted(path for path in root.glob("*.json") if path.is_file())
    if not result:
        raise ValueError(f"no public schema files under {root}")
    return result


def _properties(schema: Any) -> dict[str, str]:
    if not isinstance(schema, dict):
        return {}
    if isinstance(schema.get("properties"), dict):
        return {canonical_slot(key): str(value.get("type", "unknown"))
                for key, value in schema["properties"].items() if isinstance(value, dict)}
    # Array item properties are still public response slots.  Keeping them is
    # necessary to represent ordinary lookup -> action dataflow without
    # retaining any returned item/value.
    if schema.get("type") == "array" and isinstance(schema.get("items"), dict):
        return _properties(schema["items"])
    return {}


def _openapi_request_fields(row: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    """Return public request-body fields without reading examples or values."""
    required: dict[str, str] = {}; optional: dict[str, str] = {}
    body = row.get("requestBody", {})
    if not isinstance(body, dict):
        return required, optional
    for media in body.get("content", {}).values():
        if not isinstance(media, dict) or not isinstance(media.get("schema"), dict):
            continue
        schema = media["schema"]
        required_names = {canonical_slot(name) for name in schema.get("required", ())}
        for name, type_name in _properties(schema).items():
            (required if name in required_names else optional)[name] = type_name
    return required, optional


def _openapi_operations(root: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    operations: dict[str, dict[str, Any]] = {}; sources = []
    for path in _files(root):
        raw = path.read_bytes(); document = json.loads(raw); app = path.stem
        sources.append({"name": path.name, "sha256": hashlib.sha256(raw).hexdigest()})
        for endpoint, methods in sorted(document.get("paths", {}).items()):
            if not isinstance(methods, dict): continue
            for method in _METHODS:
                row = methods.get(method)
                if not isinstance(row, dict) or not row.get("operationId"): continue
                operation = canonical_operation(app, row["operationId"])
                required, optional = {}, {}
                for parameter in row.get("parameters", ()):
                    if not isinstance(parameter, dict) or not parameter.get("name"): continue
                    target = required if parameter.get("required") else optional
                    target[canonical_slot(parameter["name"])] = str(parameter.get("schema", {}).get("type", "unknown"))
                body_required, body_optional = _openapi_request_fields(row)
                required.update(body_required)
                optional.update({name: type_name for name, type_name in body_optional.items() if name not in required})
                outputs: dict[str, str] = {}
                for status, response in row.get("responses", {}).items():
                    if not str(status).startswith("2") or not isinstance(response, dict): continue
                    for media in response.get("content", {}).values():
                        if isinstance(media, dict): outputs.update(_properties(media.get("schema")))
                operations[operation] = {"operation_id": str(row["operationId"]), "app": canonical_slot(app),
                    "http_method": method.upper(), "access_mode": "read" if method == "get" else "write",
                    "path_template": str(endpoint), "openapi_required": required, "openapi_optional": optional,
                    "output_slots": outputs}
    return operations, sources


def _function_operations(root: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    operations: dict[str, dict[str, Any]] = {}; sources = []
    for path in _files(root):
        raw = path.read_bytes(); rows = json.loads(raw); app = path.stem
        sources.append({"name": path.name, "sha256": hashlib.sha256(raw).hexdigest()})
        if not isinstance(rows, list): raise ValueError(f"function schema is not a list: {path.name}")
        for item in rows:
            function = item.get("function", {}) if isinstance(item, dict) else {}
            name = function.get("name")
            if not name: continue
            operation = canonical_operation(app, str(name))
            parameters = function.get("parameters", {}) if isinstance(function.get("parameters"), dict) else {}
            props = _properties(parameters)
            required = {canonical_slot(key) for key in parameters.get("required", ())}
            if not required.issubset(props): raise ValueError(f"function required field missing property: {operation}")
            if operation in operations: raise ValueError(f"duplicate function operation: {operation}")
            operations[operation] = {"function_name": str(name), "parameters": props,
                                     "function_required": sorted(required)}
    return operations, sources


def build_public_tool_schema_registry(openapi_root: str | Path, function_root: str | Path) -> dict[str, Any]:
    """Build from public OpenAPI + actual public function-calling schemas."""
    openapi, openapi_sources = _openapi_operations(Path(openapi_root))
    functions, function_sources = _function_operations(Path(function_root))
    if set(openapi) != set(functions):
        raise ValueError("public OpenAPI/function operation sets differ")
    operations = []
    for name in sorted(functions):
        endpoint, function = openapi[name], functions[name]
        function_parameters = function["parameters"]
        # A required endpoint field must be present in the public callable
        # schema, but the latter remains authoritative for executor inputs.
        if not set(endpoint["openapi_required"]).issubset(function_parameters):
            raise ValueError(f"required OpenAPI input absent from callable schema: {name}")
        parameter_kinds = {}
        for field, type_name in sorted(function_parameters.items()):
            if field in _CONTEXT_PARAMETER_NAMES: kind = "runtime_context"
            elif field in function["function_required"] or field in endpoint["openapi_required"]: kind = "public_required"
            else: kind = "public_optional"
            parameter_kinds[field] = {"type": type_name, "kind": kind}
        operations.append({"operation": name, "function_name": function["function_name"],
            "app": endpoint["app"], "http_method": endpoint["http_method"], "access_mode": endpoint["access_mode"],
            "path_template": endpoint["path_template"], "parameters": parameter_kinds,
            "required_parameters": sorted(field for field, item in parameter_kinds.items() if item["kind"] == "public_required"),
            "optional_parameters": sorted(field for field, item in parameter_kinds.items() if item["kind"] == "public_optional"),
            "context_parameters": sorted(field for field, item in parameter_kinds.items() if item["kind"] == "runtime_context"),
            "output_slots": sorted(endpoint["output_slots"]),
            "interface_differences": {
                "callable_only": sorted(field for field in function_parameters if field not in endpoint["openapi_required"] and field not in endpoint["openapi_optional"]),
                "openapi_only": sorted(field for field in set(endpoint["openapi_required"]) | set(endpoint["openapi_optional"]) if field not in function_parameters),
            }})
    index = {row["operation"]: row for row in operations}
    edges, groups = [], []
    for consumer in operations:
        for slot in consumer["required_parameters"]:
            producers = sorted(row["operation"] for row in operations if row["access_mode"] == "read" and
                               row["operation"] != consumer["operation"] and slot in row["output_slots"])
            # A learned procedure is restricted to public lookup -> action
            # flow.  This preserves an acyclic, directly observable path and
            # avoids inferring generic CRUD cycles from shared identifier
            # names.
            if consumer["access_mode"] != "write":
                continue
            if producers:
                groups.append({"group_id": f"input:{consumer['operation']}:{slot}", "consumer_operation": consumer["operation"],
                               "input_slot": slot, "producer_operations": producers,
                               "semantic_status": "schema_compatible_not_semantically_equivalent"})
                edges.extend({"from_operation": producer, "to_operation": consumer["operation"], "via_slot": slot,
                              "kind": "public_callable_schema_flow"} for producer in producers)
    registry = {"registry_version": REGISTRY_VERSION,
        "source_metadata": {"openapi": openapi_sources, "function_calling": function_sources},
        "operations": operations, "alternative_groups": groups,
        "dependency_edges": sorted(edges, key=lambda row: (row["from_operation"], row["to_operation"], row["via_slot"])),
        "normalization": {"operation_aliases": {row["function_name"]: row["operation"] for row in operations},
            "runtime_context_fields": sorted(_CONTEXT_PARAMETER_NAMES), "local_binding_pattern": "^var_[0-9]+$",
            "values": "never retained in operation_signature or learned procedure"},
        "path_rule": {"ordered": True, "direct_observation_required": True,
            "required_fields": "all callable public_required fields", "additional_fields": "only callable public_optional or runtime_context fields",
            "unknown_fields": "fail_closed", "concrete_values": "hash-only invocation_evidence"}}
    registry["registry_sha256"] = canonical_digest(registry)
    return registry


def verify_public_tool_schema_registry(registry: dict[str, Any]) -> None:
    expected = canonical_digest({key: value for key, value in registry.items() if key != "registry_sha256"})
    if registry.get("registry_version") != REGISTRY_VERSION or registry.get("registry_sha256") != expected:
        raise ValueError("tool schema registry hash/version mismatch")
    names = [row.get("operation") for row in registry.get("operations", ())]
    if len(names) != len(set(names)): raise ValueError("duplicate tool schema operation")
    for row in registry.get("operations", ()):
        params = row.get("parameters", {})
        if not set(row.get("required_parameters", ())).issubset(params): raise ValueError("missing required callable field")
        if set(row.get("required_parameters", ())) & set(row.get("context_parameters", ())): raise ValueError("context field cannot be required procedure field")
        if any(item.get("kind") not in {"public_required", "public_optional", "runtime_context"} for item in params.values()):
            raise ValueError("unknown callable parameter classification")
    graph: dict[str, set[str]] = {str(name): set() for name in names}
    for edge in registry.get("dependency_edges", ()):
        left, right = edge.get("from_operation"), edge.get("to_operation")
        if left not in graph or right not in graph or left == right:
            raise ValueError("tool schema dependency edge integrity failure")
        graph[left].add(right)
    visiting: set[str] = set(); visited: set[str] = set()
    def visit(node: str) -> None:
        if node in visiting: raise ValueError("tool schema cyclic dependency")
        if node in visited: return
        visiting.add(node)
        for child in graph[node]: visit(child)
        visiting.remove(node); visited.add(node)
    for node in graph: visit(node)


def tool_operation_index(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    verify_public_tool_schema_registry(registry)
    return {row["operation"]: row for row in registry["operations"]}


def canonical_operation_signature(registry: dict[str, Any], operation: str, parameter_names: Iterable[str],
                                  parameter_types: dict[str, str] | None = None, *, parameter_values: Any = None) -> dict[str, Any]:
    """Canonical public callable signature; values are forbidden at this boundary."""
    if parameter_values not in (None, {}, ()): raise ValueError("concrete invocation values cannot enter operation signature")
    aliases = registry["normalization"]["operation_aliases"]
    canonical = aliases.get(operation, operation)
    meta = tool_operation_index(registry).get(canonical)
    if meta is None: raise ValueError("unknown public callable operation")
    fields = {canonical_slot(item) for item in parameter_names if not _LOCAL_BINDING.match(canonical_slot(item))}
    known = set(meta["parameters"])
    unknown = sorted(fields - known)
    if unknown: raise ValueError(f"unknown undeclared callable fields: {unknown}")
    missing = sorted(set(meta["required_parameters"]) - fields)
    if missing: raise ValueError(f"missing required callable fields: {missing}")
    types = parameter_types or {}
    for field, type_name in types.items():
        key = canonical_slot(field)
        if key in meta["parameters"] and str(type_name) != str(meta["parameters"][key]["type"]):
            raise ValueError(f"callable parameter type mismatch: {key}")
    return {"application": meta["app"], "callable_name": meta["function_name"], "operation": canonical,
            "public_required": meta["required_parameters"], "public_optional_present": sorted(fields & set(meta["optional_parameters"])),
            "runtime_context_present": sorted(fields & set(meta["context_parameters"])),
            "output_slots": meta["output_slots"]}


def invocation_evidence(signature: dict[str, Any], *, raw_event_digest: str, concrete_value_digest: str | None) -> dict[str, Any]:
    """Keep hash-only execution evidence separate from learned memory."""
    evidence = {"operation_signature": signature, "raw_event_sha256": str(raw_event_digest),
                "concrete_value_sha256": concrete_value_digest}
    evidence["invocation_evidence_sha256"] = canonical_digest(evidence)
    return evidence


def public_tool_path_audit(registry: dict[str, Any], signatures: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Validate an ordered, value-free public callable path offline."""
    verify_public_tool_schema_registry(registry)
    rows = list(signatures); index = tool_operation_index(registry); produced: set[str] = set(); rejected = []
    for position, signature in enumerate(rows):
        operation = signature.get("operation")
        meta = index.get(operation)
        if meta is None:
            rejected.append({"index": position, "reason": "operation_not_in_registry"}); continue
        if signature.get("public_required") != meta["required_parameters"]:
            rejected.append({"index": position, "reason": "signature_required_fields_mismatch"}); continue
        missing = [field for field in meta["required_parameters"] if field not in produced]
        if missing:
            rejected.append({"index": position, "reason": "unsatisfied_public_dependency", "fields": missing}); continue
        produced.update(meta["output_slots"])
    passed = bool(rows) and any(index[row["operation"]]["access_mode"] == "write" for row in rows) and not rejected
    result = {"registry_sha256": registry["registry_sha256"], "path": rows,
              "path_sha256": canonical_digest(rows), "passed": passed,
              "rejections": rejected, "first_rejection": rejected[0] if rejected else None}
    return result
