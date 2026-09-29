"""Public, deterministic task-conditioned CoProMem retrieval queries.

The query is intentionally derived before retrieval and independently of the
memory bank.  Ambiguous public evidence produces an empty query rather than a
union of learned schema operations.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping


POLICY_VERSION = "copromem-v6.2-public-task-query-v1"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(sorted(set(re.findall(r"[a-z][a-z0-9_]{2,}", value.lower()))))


def _app_names(metadata: Mapping[str, Any], registry: Mapping[str, Any]) -> tuple[str, ...]:
    descriptions = metadata.get("app_descriptions", {})
    if not isinstance(descriptions, Mapping):
        return ()
    public = {str(name).lower() for name in descriptions if isinstance(name, str)}
    registry_apps = {str(item.get("app") or "").lower() for item in registry.get("operations", [])}
    return tuple(sorted(public & registry_apps))


def derive_task_query(instruction: str, domain: str, public_tool_metadata: Mapping[str, Any],
                      callable_registry: Mapping[str, Any]) -> dict[str, Any]:
    """Return a content-addressed query from public pre-execution evidence.

    An operation is eligible only if its app is explicitly public for the task
    and every non-app operation component is explicitly present in the public
    instruction.  This deliberately favors empty guidance over speculative
    cross-domain retrieval.
    """
    if not isinstance(instruction, str) or not isinstance(domain, str):
        raise ValueError("public instruction and domain are required")
    registry_hash = str(callable_registry.get("registry_sha256") or "")
    if not registry_hash:
        raise ValueError("frozen callable registry identity required")
    instruction_tokens = _tokens(instruction)
    apps = _app_names(public_tool_metadata, callable_registry)
    operations: list[str] = []
    for item in callable_registry.get("operations", []):
        if not isinstance(item, Mapping):
            continue
        operation, app = str(item.get("operation") or ""), str(item.get("app") or "").lower()
        if not operation or app not in apps:
            continue
        # API names are public metadata.  Require every semantic name token
        # after the app namespace; generic names cannot create a query alone.
        components = tuple(token for token in re.split(r"[._-]+", operation.lower())
                           if token and token not in {app, "apis", "api"})
        if components and set(components) <= set(instruction_tokens):
            operations.append(operation)
    descriptor = {"domain": domain, "public_apps": list(apps),
                  "instruction_tokens": list(instruction_tokens),
                  "operations": sorted(set(operations))}
    status = "specific" if operations else "empty_public_query"
    record = {"policy_version": POLICY_VERSION,
              "instruction_sha256": hashlib.sha256(instruction.encode("utf-8")).hexdigest(),
              "public_tool_metadata_sha256": digest(public_tool_metadata),
              "callable_registry_sha256": registry_hash,
              "derived_public_descriptor": descriptor,
              "query_operations": sorted(set(operations)),
              "derivation_status": status,
              "derivation_reason": None if operations else "public evidence does not uniquely support an operation query"}
    record["query_sha256"] = digest({key: value for key, value in record.items() if key != "query_sha256"})
    return record


def validate_task_query(record: Mapping[str, Any], *, instruction: str, public_tool_metadata: Mapping[str, Any],
                        callable_registry: Mapping[str, Any]) -> None:
    expected = derive_task_query(instruction, str(record.get("derived_public_descriptor", {}).get("domain", "")),
                                 public_tool_metadata, callable_registry)
    if dict(record) != expected:
        raise ValueError("task-query provenance does not reproduce from public inputs")
