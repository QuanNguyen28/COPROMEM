#!/usr/bin/env python3
"""Read-only v5.4 forensic audit of the immutable v5.3 run-012 A traces.

The frozen v5.3 registry and manifest are verified before histories are read.
Only public operation/slot signatures and hashes are emitted; task text, code,
values, prompts, responses, and scorer internals are never written.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any

from copromem.benchmarks.appworld.adapter import normalize_appworld_history
from copromem.experiments.reme_copromem.public_tool_schema_registry import (
    canonical_digest, canonical_operation_signature, tool_operation_index, verify_public_tool_schema_registry,
)


def _load(path: Path) -> dict[str, Any]: return json.loads(path.read_text(encoding="utf-8"))
def _sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()


def _operation_name(function: ast.AST) -> str | None:
    parts = []
    while isinstance(function, ast.Attribute):
        parts.append(function.attr); function = function.value
    return ".".join((function.id, *reversed(parts))) if isinstance(function, ast.Name) else None


def _program_call_evidence(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sanitize structural execution evidence without retaining code or values."""
    result = []; occurrence: dict[str, int] = {}
    for message_index, message in enumerate(history):
        if message.get("role") != "assistant": continue
        try: tree = ast.parse(str(message.get("content", "")))
        except SyntaxError: continue
        response = history[message_index + 1] if message_index + 1 < len(history) else {}
        response_observed = bool(response.get("role") == "user" and "Traceback (most recent call last)" not in str(response.get("content", "")))
        def visit(node: ast.AST, parents: tuple[str, ...], statement_direct: bool) -> None:
            if isinstance(node, ast.Call):
                operation = _operation_name(node.func)
                if operation:
                    ordinal = occurrence.get(operation, 0); occurrence[operation] = ordinal + 1
                    control = tuple(item for item in parents if item in {"For", "AsyncFor", "While", "If", "IfExp", "Try", "With", "comprehension"})
                    result.append({"operation": operation, "occurrence": ordinal,
                                   "program_response_observed": response_observed,
                                   "direct_statement": bool(statement_direct and not control),
                                   "control_context": list(control)})
            for child in ast.iter_child_nodes(node):
                visit(child, parents + (type(node).__name__,), isinstance(node, (ast.Expr, ast.Assign)))
        for statement in tree.body: visit(statement, (), isinstance(statement, (ast.Expr, ast.Assign)))
    return result


def _row(registry: dict[str, Any], artifact: Path, descriptor: list[dict[str, Any]]) -> dict[str, Any]:
    value = _load(artifact); events = normalize_appworld_history(value["history"], True)
    program_calls = _program_call_evidence(value["history"])
    terminal = descriptor[-1]["operation"]
    index = tool_operation_index(registry)
    operations, dataflow = [], []
    for event_index, event in enumerate(events):
        try:
            signature = canonical_operation_signature(registry, event.operation, event.input_slots)
            schema_result = {"matched": True, "signature": signature}
        except ValueError as exc:
            schema_result = {"matched": False, "rejection": str(exc)}
        role = ("terminal_effect" if event.operation == terminal else
                "descriptor_prerequisite" if event.operation in {step["operation"] for step in descriptor[:-1]} else
                "public_incidental_or_alternative" if event.operation in index else "unknown_operation")
        operations.append({"index": event_index, "operation": event.operation, "input_slots": sorted(event.input_slots),
                           "output_slots": sorted(event.output_slots), "observed": bool(event.observed and event.check),
                           "role": role, "callable_schema": schema_result})
    for producer_index, producer in enumerate(events):
        for consumer_index, consumer in enumerate(events[producer_index + 1:], producer_index + 1):
            shared = sorted(set(producer.output_slots) & set(consumer.input_slots))
            if shared:
                dataflow.append({"from_index": producer_index, "to_index": consumer_index,
                                 "from_operation": producer.operation, "to_operation": consumer.operation,
                                 "local_binding_slots": shared})
    observed_terminal = [row for row in operations if row["role"] == "terminal_effect" and row["observed"]]
    terminal_program_calls = [row for row in program_calls if row["operation"] == terminal]
    descriptor_ops = [step["operation"] for step in descriptor]
    observed_ops = [row["operation"] for row in operations if row["observed"]]
    missing = [operation for operation in descriptor_ops if operation not in observed_ops]
    return {"artifact_sha256": _sha(artifact), "history_sha256": value.get("history_sha256"),
            "normalized_operation_count": len(operations), "operations": operations, "dataflow_edges": dataflow,
            "terminal_effect": terminal, "terminal_effect_directly_observed": bool(observed_terminal),
            "terminal_effect_program_evidence": terminal_program_calls,
            "terminal_effect_present_in_response_attested_program": any(row["program_response_observed"] for row in terminal_program_calls),
            "frozen_descriptor_operations": descriptor_ops, "missing_descriptor_operations": missing,
            "decision": ("terminal_effect_nested_or_not_directly_observed" if not observed_terminal else
                         "frozen_prerequisite_chain_mismatch" if missing else "descriptor_path_observed")}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--run", type=Path, required=True); parser.add_argument("--registry", type=Path, required=True); parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    registry = _load(args.registry); verify_public_tool_schema_registry(registry)
    manifest = _load(args.run / "manifest.json")
    descriptor = manifest["evaluation"]["descriptors"][manifest["evaluation"]["a_task_id"]]
    artifacts = sorted((args.run / "evaluation" / "copromem_dynamic").glob("**/trial-*.json"))
    result = {"audit_version": "v5_4_effect_path_012_forensic_v1", "provider_calls": 0,
              "registry_sha256": registry["registry_sha256"], "manifest_sha256": _sha(args.run / "manifest.json"),
              "frozen_before_history_read": True, "artifact_count": len(artifacts),
              "artifacts": [_row(registry, artifact, descriptor) for artifact in artifacts]}
    result["terminal_effect_observed_in_all"] = bool(artifacts) and all(row["terminal_effect_directly_observed"] for row in result["artifacts"])
    result["audit_sha256"] = canonical_digest(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifacts": len(artifacts), "terminal_effect_observed_in_all": result["terminal_effect_observed_in_all"],
                      "audit_sha256": result["audit_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
