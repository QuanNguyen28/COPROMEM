"""Public direct-name observations with no introspection, values or object methods."""

from __future__ import annotations

import ast
import builtins
import json
import keyword
import runpy
from pathlib import Path

VERSION = "public-direct-reference-presence-only-v1"
MARKER = "COPROMEM_PRESENCE="
EMPTY = "COPROMEM_PRESENCE_EMPTY"
WORKER = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "containers/appworld/worker.py")
)


def selected_names(programs: list[str]) -> list[str]:
    if (
        not isinstance(programs, list)
        or not programs
        or any(not isinstance(p, str) for p in programs)
    ):
        raise ValueError("nonempty public source-program list required")
    return sorted(
        {
            node.id
            for program in programs
            for node in ast.walk(ast.parse(program))
            if isinstance(node, ast.Name)
            and node.id not in vars(builtins)
            and node.id != "apis"
        }
    )


def bound_control_names(prefix: list[str]) -> list[str]:
    found = set()
    for program in prefix:
        for node in ast.walk(ast.parse(program)):
            names = []
            if isinstance(node, ast.Name) and isinstance(
                node.ctx, (ast.Store, ast.Del)
            ):
                names.append(node.id)
            elif isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                names.append(node.name)
            elif isinstance(node, ast.alias):
                names.append(node.asname or node.name.split(".")[0])
                if node.name == "*":
                    names.extend(["print", "NameError"])
            elif isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)):
                names.append(node.name)
            elif isinstance(node, ast.MatchMapping):
                names.append(node.rest)
            found.update(name for name in names if name in {"print", "NameError"})
    return sorted(found)


def construct(public: dict) -> dict:
    if not isinstance(public, dict) or set(public) != {"programs", "prefix"}:
        raise ValueError("query constructor accepts only public source programs/prefix")
    if not isinstance(public["prefix"], list) or any(
        not isinstance(p, str) for p in public["prefix"]
    ):
        raise ValueError("public prefix must be a source string list")
    names = selected_names(public["programs"])
    if bound_control_names(public["prefix"]):
        raise ValueError("public prefix may shadow query control builtins")
    parts = []
    for name in names:
        if not name.isidentifier() or keyword.iskeyword(name):
            raise ValueError("invalid public identifier")
        positive = MARKER + json.dumps(
            {"name": name, "present": True}, sort_keys=True, separators=(",", ":")
        )
        negative = MARKER + json.dumps(
            {"name": name, "present": False}, sort_keys=True, separators=(",", ":")
        )
        parts.append(
            f"try:\n    (lambda probe_value: print({positive!r}))({name})\n"
            f"except NameError:\n    print({negative!r})\n"
        )
    query = "".join(parts) if parts else f"print({EMPTY!r})\n"
    WORKER["validate_program"](query)
    return {
        "version": VERSION,
        "names": names,
        "query": query,
        "values_exported": False,
        "type_or_length_exported": False,
    }


def unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate public presence JSON key")
        result[name] = value
    return result


def parse_output(output: str, names: list[str]) -> dict:
    if (
        not isinstance(output, str)
        or not isinstance(names, list)
        or names != sorted(set(names))
    ):
        raise ValueError("invalid public output or name registry")
    lines = output.strip().splitlines()
    if not names:
        if lines != [EMPTY]:
            raise ValueError("invalid empty public presence output")
        return {"version": VERSION, "bindings": []}
    if len(lines) != len(names):
        raise ValueError("presence output denominator differs from selected names")
    records = []
    for name, line in zip(names, lines, strict=True):
        if not line.startswith(MARKER):
            raise ValueError("missing public presence marker")
        try:
            record = json.loads(line[len(MARKER) :], object_pairs_hook=unique_object)
        except json.JSONDecodeError as exc:
            raise ValueError("malformed public presence JSON") from exc
        if (
            not isinstance(record, dict)
            or set(record) != {"name", "present"}
            or record["name"] != name
            or type(record["present"]) is not bool
        ):
            raise ValueError("presence schema/name/order mismatch")
        records.append(record)
    return {"version": VERSION, "bindings": records}
