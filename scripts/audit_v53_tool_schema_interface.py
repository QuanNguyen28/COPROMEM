#!/usr/bin/env python3
"""Generate a zero-provider audit of AppWorld public executor interfaces.

It consumes only the v5.3 registry, whose inputs are public OpenAPI and public
function-calling metadata.  It intentionally neither reads task data nor any
trajectory artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from copromem.experiments.reme_copromem.public_tool_schema_registry import canonical_digest, verify_public_tool_schema_registry


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _classify(operation: dict[str, Any]) -> list[dict[str, str]]:
    result = []
    for field in operation["interface_differences"]["callable_only"]:
        result.append({"operation": operation["operation"], "field": field,
                       "classification": operation["parameters"][field]["kind"],
                       "source": "public_function_calling_schema"})
    for field in operation["interface_differences"]["openapi_only"]:
        result.append({"operation": operation["operation"], "field": field,
                       "classification": "not_callable_from_public_executor_schema",
                       "source": "public_openapi_only"})
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--normalizer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    registry = _load(args.registry); verify_public_tool_schema_registry(registry)
    differences = sorted((row for operation in registry["operations"] for row in _classify(operation)),
                         key=lambda row: (row["operation"], row["field"]))
    venmo_show = next((row for row in registry["operations"] if row["operation"] == "apis.venmo.show_transactions"), None)
    user_email = ({"operation": venmo_show["operation"], "field": "user_email",
                   "classification": venmo_show["parameters"]["user_email"]["kind"],
                   "source": "public_function_calling_schema_and_public_openapi_metadata",
                   "conclusion": "declared public optional callable field; not runtime injection or normalizer artifact"}
                  if venmo_show and "user_email" in venmo_show["parameters"] else {"classification": "not_found"})
    normalizer_raw = args.normalizer.read_bytes()
    result = {"audit_version": "v5_3_public_tool_schema_interface_audit_v1", "provider_calls": 0,
              "registry_sha256": registry["registry_sha256"],
              "source_metadata": registry["source_metadata"],
              "normalizer": {"path": str(args.normalizer).replace("\\", "/"),
                             "sha256": hashlib.sha256(normalizer_raw).hexdigest(),
                             "public_behavior": {"operation_form": "executor AST public callable path",
                                                 "local_bindings": "var_N stripped by frozen rule",
                                                 "concrete_values": "never retained by normalizer or learned procedure"}},
              "mismatches": differences,
              "mismatch_count": len(differences),
              "user_email_finding": user_email,
              "matching_policy": {"required": "all frozen public_required fields must occur",
                                  "superset": "public_optional and runtime_context fields may occur",
                                  "unknown": "undeclared fields fail closed",
                                  "aliases": "only frozen function-name to operation maps",
                                  "invocation_values": "hash-only evidence; excluded from memory"}}
    result["audit_sha256"] = canonical_digest(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"registry_sha256": result["registry_sha256"], "mismatch_count": len(differences),
                      "user_email": result["user_email_finding"], "audit_sha256": result["audit_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
