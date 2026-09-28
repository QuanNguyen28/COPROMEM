"""Deterministic public AppWorld operation-path registry for v5.2.

The builder deliberately consumes OpenAPI documents only.  It has no task,
trajectory, scorer, prompt, or runtime-state input.  Its graph is therefore a
*capability* graph, not an assertion that every syntactically possible API path
solves a task.  A later task-boundary plan can promote only an actually
observed, complete path from this frozen graph.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


REGISTRY_VERSION = "appworld-public-alternative-path-registry-v5_2"
_METHOD_ORDER = ("get", "post", "put", "patch", "delete")
_READ_METHODS = {"get"}
_SAFE_SLOT = re.compile(r"[^a-z0-9_]+")
_LOCAL_SLOT = re.compile(r"^var_[0-9]+$")
_INFRASTRUCTURE_INPUTS = {"access_token"}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def canonical_slot(value: str) -> str:
    """Public-schema-only slot normalisation; it never sees values."""
    return _SAFE_SLOT.sub("_", str(value).strip().lower()).strip("_")


def canonical_operation(app: str, operation_id: str) -> str:
    suffix = str(operation_id).split("__", 1)[-1]
    return f"apis.{canonical_slot(app)}.{canonical_slot(suffix)}"


def _schema_properties(schema: Any) -> list[str]:
    if not isinstance(schema, dict):
        return []
    if isinstance(schema.get("properties"), dict):
        return sorted(canonical_slot(key) for key in schema["properties"])
    if schema.get("type") == "array" and isinstance(schema.get("items"), dict):
        return _schema_properties(schema["items"])
    # OpenAPI may wrap a list response in an object.  The wrapper key is a
    # public return slot and is retained rather than guessing its contents.
    return []


def _operation_inputs(operation: dict[str, Any]) -> tuple[list[str], list[str]]:
    required: list[str] = []
    optional: list[str] = []
    for parameter in operation.get("parameters", []):
        if isinstance(parameter, dict) and parameter.get("name"):
            (required if parameter.get("required") else optional).append(canonical_slot(parameter["name"]))
    content = operation.get("requestBody", {}).get("content", {}) if isinstance(operation.get("requestBody"), dict) else {}
    for media in content.values():
        if isinstance(media, dict):
            schema = media.get("schema")
            names = _schema_properties(schema)
            schema_required = set(schema.get("required", ())) if isinstance(schema, dict) else set()
            required.extend(name for name in names if name in schema_required)
            optional.extend(name for name in names if name not in schema_required)
    required_slots = sorted(set(slot for slot in required if slot))
    optional_slots = sorted(set(slot for slot in optional if slot and slot not in required_slots))
    return required_slots, optional_slots


def _operation_outputs(operation: dict[str, Any]) -> list[str]:
    slots = []
    for status, response in operation.get("responses", {}).items():
        if not str(status).startswith("2") or not isinstance(response, dict):
            continue
        for media in response.get("content", {}).values():
            if isinstance(media, dict):
                slots.extend(_schema_properties(media.get("schema")))
    return sorted(set(slot for slot in slots if slot))


def _metadata_files(api_docs_root: Path) -> list[Path]:
    files = sorted(path for path in api_docs_root.glob("*.json") if path.is_file())
    if not files:
        raise ValueError(f"no public OpenAPI documents under {api_docs_root}")
    return files


def build_public_registry(api_docs_root: str | Path) -> dict[str, Any]:
    """Build a content-addressed registry from public AppWorld OpenAPI files."""
    root = Path(api_docs_root)
    sources: list[dict[str, str]] = []
    operations: list[dict[str, Any]] = []
    for path in _metadata_files(root):
        raw = path.read_bytes()
        document = json.loads(raw)
        app = path.stem
        sources.append({"name": path.name, "sha256": hashlib.sha256(raw).hexdigest()})
        for endpoint, methods in sorted(document.get("paths", {}).items()):
            if not isinstance(methods, dict):
                continue
            for method in _METHOD_ORDER:
                operation = methods.get(method)
                if not isinstance(operation, dict) or not operation.get("operationId"):
                    continue
                name = canonical_operation(app, operation["operationId"])
                required_inputs, optional_inputs = _operation_inputs(operation)
                operations.append({
                    "operation": name,
                    "app": canonical_slot(app),
                    "http_method": method.upper(),
                    "access_mode": "read" if method in _READ_METHODS else "write",
                    "path_template": str(endpoint),
                    "input_slots": required_inputs,
                    "optional_input_slots": optional_inputs,
                    "output_slots": _operation_outputs(operation),
                    # This is a public identifier only; summaries/descriptions
                    # can contain natural-language examples and are excluded.
                    "operation_id": str(operation["operationId"]),
                })
    by_name = {row["operation"]: row for row in operations}
    if len(by_name) != len(operations):
        raise ValueError("public OpenAPI operation-name collision")
    operations = [by_name[name] for name in sorted(by_name)]

    edges: list[dict[str, str]] = []
    alternatives: dict[str, list[str]] = {}
    for consumer in operations:
        for slot in consumer["input_slots"]:
            producers = sorted(row["operation"] for row in operations
                               if row["operation"] != consumer["operation"] and slot in row["output_slots"])
            group_id = f"input:{consumer['operation']}:{slot}"
            alternatives[group_id] = producers
            # A learned procedural path is intentionally restricted to the
            # public read -> write dependency direction.  It avoids inventing
            # arbitrary cyclic CRUD chains from generic ``id`` slots while
            # still representing the observable lookup/action pattern.
            for producer in producers:
                if consumer["access_mode"] != "write" or by_name[producer]["access_mode"] != "read":
                    continue
                edges.append({"from_operation": producer, "to_operation": consumer["operation"],
                              "via_slot": slot, "kind": "public_schema_flow"})
    edges.sort(key=lambda row: (row["from_operation"], row["to_operation"], row["via_slot"]))
    # Alternative groups are explicit candidate producer sets.  They do not
    # declare semantic interchangeability; a promotion records the exact
    # selected path and must contain its observed producer.
    alternative_groups = [{"group_id": key, "consumer_operation": key.split(":", 2)[1],
                           "input_slot": key.rsplit(":", 1)[1], "producer_operations": value,
                           "semantic_status": "schema_compatible_not_semantically_equivalent"}
                          for key, value in sorted(alternatives.items()) if value]
    registry = {
        "registry_version": REGISTRY_VERSION,
        "source_metadata": sources,
        "operations": operations,
        "alternative_groups": alternative_groups,
        "dependency_edges": edges,
        "normalization": {
            "operation": "openapi operationId app__name -> apis.app.name",
            "slots": "lowercase ASCII snake_case schema property or parameter names",
            "aliases": [],
            "rule": "no lexical or outcome-derived aliases; aliases require public metadata",
        },
        "path_rule": {
            "ordered": True,
            "direct_observation_required": True,
            "concrete_parameters_permitted": False,
            "optional_nodes": "only nodes absent from selected observed path",
            "mandatory_nodes": "every node in selected observed path",
            "edge_rule": "non-public-input consumer slots must be supplied by an earlier selected path output",
        },
    }
    registry["registry_sha256"] = canonical_digest(registry)
    return registry


def verify_public_registry(registry: dict[str, Any]) -> None:
    expected = canonical_digest({key: value for key, value in registry.items() if key != "registry_sha256"})
    if registry.get("registry_version") != REGISTRY_VERSION or registry.get("registry_sha256") != expected:
        raise ValueError("public registry hash/version mismatch")
    names = [row.get("operation") for row in registry.get("operations", [])]
    if len(names) != len(set(names)) or not all(isinstance(name, str) and name.startswith("apis.") for name in names):
        raise ValueError("public registry operation integrity failure")
    graph: dict[str, set[str]] = {name: set() for name in names}
    for edge in registry.get("dependency_edges", []):
        left, right = edge.get("from_operation"), edge.get("to_operation")
        if left not in graph or right not in graph or left == right:
            raise ValueError("public registry dependency edge integrity failure")
        graph[left].add(right)
    # Cycles make a finite ordered procedure ambiguous and are rejected.
    visiting: set[str] = set(); visited: set[str] = set()
    def visit(node: str) -> None:
        if node in visiting: raise ValueError("public registry cyclic dependency")
        if node in visited: return
        visiting.add(node)
        for child in graph[node]: visit(child)
        visiting.remove(node); visited.add(node)
    for node in graph: visit(node)


def operation_index(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    verify_public_registry(registry)
    return {str(row["operation"]): row for row in registry["operations"]}


def observed_public_operation_matches(registry: dict[str, Any], event: dict[str, Any],
                                      expected: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """Match an observed API call to a frozen public operation schema.

    The maintained action normalizer represents local Python bindings as
    ``var_N`` and authentication as ``access_token``.  Neither is an API
    schema field or a task value.  They are omitted here while retaining every
    named public input; response slots are canonicalized from the observed API
    operation's *frozen public schema*, not from response values.
    """
    meta = operation_index(registry).get(str(event.get("operation", "")))
    if meta is None or meta["operation"] != expected.get("operation"):
        return False, {"reason": "operation_not_in_frozen_registry"}
    expected_inputs = sorted(canonical_slot(slot) for slot in expected.get("input_slots", ()))
    expected_outputs = sorted(canonical_slot(slot) for slot in expected.get("output_slots", ()))
    if expected_inputs != meta["input_slots"] or expected_outputs != meta["output_slots"]:
        return False, {"reason": "descriptor_not_equal_to_frozen_public_signature"}
    observed = {canonical_slot(slot) for slot in event.get("input_slots", ())}
    public_inputs = sorted(slot for slot in observed if slot not in _INFRASTRUCTURE_INPUTS and not _LOCAL_SLOT.match(slot))
    allowed = set(meta["input_slots"]) | set(meta.get("optional_input_slots", ()))
    if not set(meta["input_slots"]).issubset(public_inputs) or not set(public_inputs).issubset(allowed):
        return False, {"reason": "observed_public_input_signature_mismatch", "observed_public_inputs": public_inputs,
                       "required_inputs": meta["input_slots"], "optional_inputs": meta.get("optional_input_slots", [])}
    return True, {"canonical_operation": meta["operation"], "canonical_inputs": meta["input_slots"],
                  "canonical_outputs": meta["output_slots"], "observed_public_inputs": public_inputs,
                  "local_slots_omitted": sorted(slot for slot in observed if _LOCAL_SLOT.match(slot)),
                  "infrastructure_slots_omitted": sorted(slot for slot in observed if slot in _INFRASTRUCTURE_INPUTS)}


def public_path_audit(registry: dict[str, Any], events: Iterable[dict[str, Any]],
                      *, public_inputs: Iterable[str] = ("access_token",)) -> dict[str, Any]:
    """Validate one directly observed ordered path against a frozen registry.

    The function accepts only operation/slot evidence.  Parameters and values
    are ignored and rejected when supplied, preventing them from entering a
    promotable procedure.
    """
    index = operation_index(registry)
    rows = list(events)
    selected: list[dict[str, Any]] = []
    produced = set()
    public = {canonical_slot(slot) for slot in public_inputs}
    reasons: list[dict[str, Any]] = []
    for position, event in enumerate(rows):
        if event.get("parameters") not in ({}, None):
            reasons.append({"index": position, "reason": "concrete_parameters_forbidden"}); continue
        operation = str(event.get("operation", ""))
        meta = index.get(operation)
        if meta is None:
            reasons.append({"index": position, "operation": operation, "reason": "operation_not_in_public_registry"}); continue
        observed_inputs = sorted(canonical_slot(slot) for slot in event.get("input_slots", ()))
        observed_outputs = sorted(canonical_slot(slot) for slot in event.get("output_slots", ()))
        required_inputs = set(meta["input_slots"])
        allowed_inputs = required_inputs | set(meta.get("optional_input_slots", ()))
        allowed_outputs = set(meta["output_slots"])
        if (not required_inputs.issubset(observed_inputs) or not set(observed_inputs).issubset(allowed_inputs)
                or not observed_outputs or not set(observed_outputs).issubset(allowed_outputs)):
            reasons.append({"index": position, "operation": operation, "reason": "operation_signature_mismatch",
                            "required_inputs": meta["input_slots"], "optional_inputs": meta.get("optional_input_slots", []),
                            "allowed_outputs": meta["output_slots"],
                            "observed_inputs": observed_inputs, "observed_outputs": observed_outputs}); continue
        missing = [slot for slot in meta["input_slots"] if slot not in public and slot not in produced]
        if missing:
            reasons.append({"index": position, "operation": operation, "reason": "unsatisfied_public_dependency", "slots": missing}); continue
        selected.append({"operation": operation, "input_slots": observed_inputs, "output_slots": observed_outputs,
                         "access_mode": meta["access_mode"]})
        produced.update(observed_outputs)
    # A complete learned path requires a directly observed read/write path;
    # pure reads are intentionally not promoted as procedural memory.
    complete = bool(selected) and any(row["access_mode"] == "write" for row in selected) and not reasons
    result = {"registry_sha256": registry["registry_sha256"], "selected_path": selected,
              "selected_path_sha256": canonical_digest(selected), "rejections": reasons,
              "passed": complete, "first_rejection": reasons[0] if reasons else None}
    return result
