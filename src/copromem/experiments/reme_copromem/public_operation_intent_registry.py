"""Frozen public operation-intent descriptions for versioned retrieval.

This registry is separate from the v5.3 callable registry.  It contains only
public OpenAPI operation descriptions and never task data, execution traces,
returned values, scorers, or provider output.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from .public_path_registry import canonical_operation

VERSION = "appworld-public-operation-intent-registry-v1"
_METHODS = ("get", "post", "put", "patch", "delete")
_TOKEN = re.compile(r"[a-z][a-z0-9_]{1,}")


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _tokens(text: str) -> list[str]:
    return sorted(set(_TOKEN.findall(text.lower())))


def build(openapi_root: str | Path) -> dict[str, Any]:
    """Build an immutable, value-free intent registry from public OpenAPI."""
    root = Path(openapi_root)
    sources: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        raw = path.read_bytes(); document = json.loads(raw); app = path.stem
        sources.append({"name": path.name, "sha256": hashlib.sha256(raw).hexdigest()})
        for _endpoint, methods in sorted(document.get("paths", {}).items()):
            if not isinstance(methods, Mapping):
                continue
            for method in _METHODS:
                item = methods.get(method)
                if not isinstance(item, Mapping) or not isinstance(item.get("operationId"), str):
                    continue
                description = str(item.get("description") or item.get("summary") or "").strip()
                if not description:
                    raise ValueError("public OpenAPI operation lacks a description")
                operation = canonical_operation(app, str(item["operationId"]))
                rows.append({"operation": operation, "app": app.lower(), "http_method": method.upper(),
                             "description": description, "description_tokens": _tokens(description)})
    if not rows:
        raise ValueError("no public OpenAPI operations found")
    names = [row["operation"] for row in rows]
    if len(names) != len(set(names)):
        raise ValueError("duplicate public operation intent")
    result = {"version": VERSION, "sources": sources,
              "operations": sorted(rows, key=lambda row: row["operation"])}
    result["intent_registry_sha256"] = digest(result)
    return result


def verify(record: Mapping[str, Any]) -> None:
    observed = dict(record)
    expected = digest({key: value for key, value in observed.items() if key != "intent_registry_sha256"})
    if observed.get("version") != VERSION or observed.get("intent_registry_sha256") != expected:
        raise ValueError("public operation intent registry identity mismatch")
    rows = observed.get("operations")
    if not isinstance(rows, list) or not rows:
        raise ValueError("public operation intent registry is empty")
    names = []
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("operation"), str):
            raise ValueError("public operation intent row is malformed")
        if not isinstance(row.get("description"), str) or not isinstance(row.get("description_tokens"), list):
            raise ValueError("public operation intent description is malformed")
        if _tokens(str(row["description"])) != row["description_tokens"]:
            raise ValueError("public operation intent tokens do not reproduce")
        names.append(row["operation"])
    if names != sorted(names) or len(names) != len(set(names)):
        raise ValueError("public operation intent ordering is invalid")


def index(record: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    verify(record)
    return {str(row["operation"]): row for row in record["operations"]}
