"""Format-only, fail-closed JSON gate for CoProMem decomposition responses."""
from __future__ import annotations

import json
from typing import Any


class StrictJSONError(ValueError): pass


def classify(content: str | None, finish_reason: str | None, tool_present: bool) -> str:
    text = content or ""
    if tool_present: return "native_tool_call"
    if finish_reason == "length": return "truncated"
    if not text.strip(): return "empty"
    return "scan_required"


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result: raise StrictJSONError("duplicate_key")
        result[key] = value
    return result


def extract(schema_name: str, content: str | None, finish_reason: str | None, tool_present: bool) -> tuple[dict[str, Any], str, tuple[int, int]]:
    kind = classify(content, finish_reason, tool_present)
    if kind != "scan_required": raise StrictJSONError(kind)
    text = content or ""; decoder = json.JSONDecoder(object_pairs_hook=_no_duplicates)
    found: list[tuple[dict[str, Any], int, int]] = []; index = 0
    while index < len(text):
        start = text.find("{", index)
        if start < 0: break
        try:
            value, end = decoder.raw_decode(text, start)
        except (json.JSONDecodeError, StrictJSONError):
            index = start + 1; continue
        if not isinstance(value, dict): raise StrictJSONError("not_object")
        found.append((value, start, end)); index = end
    if not found: raise StrictJSONError("malformed_json")
    if len(found) != 1: raise StrictJSONError("multiple_objects")
    value, start, end = found[0]
    if not isinstance(value, dict): raise StrictJSONError("not_object")
    if schema_name == "copromem_complexity_v1":
        if set(value) != {"is_compound", "rationale"} or not isinstance(value["is_compound"], bool) or not isinstance(value["rationale"], str):
            raise StrictJSONError("schema_mismatch")
    elif schema_name == "copromem_subgoals_v1":
        if set(value) != {"subgoals"} or not isinstance(value["subgoals"], list):
            raise StrictJSONError("schema_mismatch")
    else:
        raise StrictJSONError("unknown_schema")
    return value, text[start:end], (start, end)


def parse(schema_name: str, content: str | None, finish_reason: str | None, tool_present: bool) -> dict[str, Any]:
    return extract(schema_name, content, finish_reason, tool_present)[0]
