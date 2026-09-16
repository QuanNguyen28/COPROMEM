"""Preserve public task/code semantics; redact supported literal credentials only."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import runpy
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, canonical, digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CHECK = runpy.run_path(str(HERE / "static_name_check.py"))
VERSION = "public-task-api-code-presence-targeted-credential-redaction-v1"
SENSITIVE = {
    "access_token",
    "refresh_token",
    "password",
    "api_key",
    "client_secret",
    "secret",
    "token",
}
DOC_FIELDS = (
    "app_name",
    "api_name",
    "path",
    "method",
    "description",
    "parameters",
    "response_schemas",
)


def api_path(call):
    node, parts = call.func, []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name) and node.id == "apis" and len(parts) == 2:
        return ".".join(reversed(parts))
    return None


def called_apis(program):
    return sorted(
        {
            path
            for node in ast.walk(ast.parse(program))
            if isinstance(node, ast.Call) and (path := api_path(node)) is not None
        }
    )


def credential_name(name):
    return name in SENSITIVE or any(name.endswith("_" + term) for term in SENSITIVE)


def credential_literals(tree, docs):
    """Bounded direct-literal/alias analysis, not a general taint or secret detector."""
    nodes = list(ast.walk(tree))
    names = {n.id for n in nodes if isinstance(n, ast.Name) and credential_name(n.id)}
    expressions = []
    for node in nodes:
        if not isinstance(node, ast.Call) or (path := api_path(node)) is None:
            continue
        sensitive = {
            p["name"] for p in docs[path]["parameters"] if credential_name(p["name"])
        }
        for kw in node.keywords:
            if kw.arg in sensitive:
                expressions.append(kw.value)
                if isinstance(kw.value, ast.Name):
                    names.add(kw.value.id)
    assignments = []
    for node in nodes:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments.append((target.id, node.value))
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
        ):
            assignments.append((node.target.id, node.value))
    while True:
        before = set(names)
        for name, value in assignments:
            if name in names and isinstance(value, ast.Name):
                names.add(value.id)
        if names == before:
            break
    expressions.extend(value for name, value in assignments if name in names)
    literal_nodes, values = set(), []
    for expression in expressions:
        if isinstance(expression, ast.Name):
            continue  # Its value is either traced above or remains outside this view.
        if isinstance(expression, ast.Constant) and (
            expression.value is None or isinstance(expression.value, str)
        ):
            if isinstance(expression.value, str) and expression.value:
                literal_nodes.add(id(expression))
                if expression.value not in values:
                    values.append(expression.value)
            continue
        raise ValueError("unsupported credential expression; do not forward this view")
    for node in nodes:
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in literal_nodes
            and any(value in node.value for value in values)
        ):
            raise ValueError(
                "credential overlaps another literal; cannot preserve semantics safely"
            )
    return values, literal_nodes


def build_view(public, task_instruction, public_docs):
    analysis = CHECK["analysis_input"](public, context=True)
    if not analysis["covered"]:
        raise IntegrityError("unknown public presence coverage")
    if not isinstance(task_instruction, str) or not task_instruction.strip():
        raise ValueError("public task instruction required")
    docs = {}
    for path in sorted(public_docs):
        raw = public_docs[path]
        if (
            set(DOC_FIELDS) - set(raw)
            or path != raw["app_name"] + "." + raw["api_name"]
        ):
            raise ValueError("public API document identity/schema mismatch")
        docs[path] = {key: copy.deepcopy(raw[key]) for key in DOC_FIELDS}
    used = called_apis(public["program"])
    if any(path not in docs for path in used):
        raise ValueError("public documentation missing for a called API")
    tree = ast.parse(public["program"])
    credentials, literal_nodes = credential_literals(tree, docs)
    markers = {value: f"<opaque-credential:{i}>" for i, value in enumerate(credentials)}
    if any(marker in public["program"] for marker in markers.values()):
        raise ValueError("credential placeholder collides with source semantics")
    for node in ast.walk(tree):
        if id(node) in literal_nodes:
            node.value = markers[node.value]
    program = ast.unparse(tree)
    ast.parse(program)  # Inspection only; never execute source or replacement text.
    view = {
        "version": VERSION,
        "program": program,
        "task_instruction": task_instruction,
        "public_presence": copy.deepcopy(public["envelope"]),
        "api_docs": docs,
    }
    if any(value in canonical(view) for value in credentials):
        raise ValueError("credential value remains in public metadata; view withheld")
    return view, {
        "credential_literal_occurrences_redacted": len(literal_nodes),
        "distinct_credential_values_redacted": len(credentials),
        "called_apis": used,
        "program_executed": False,
    }


def main():
    source = RunStore(ROOT / "artifacts/research/cycle22_static_name_check")
    protocol = source.read("protocol", "preregistration")
    if (
        digest(protocol)
        != "193aae7253bae8239484d4e1414fb50bacaa2eeaf067bd5efa63a85179d7cad5"
    ):
        raise IntegrityError("registered fourteen-record source changed")
    original_sources = source.read("source_snapshots", protocol["source_snapshot"])
    if digest(original_sources) != protocol["source_snapshot"] or any(
        (ROOT / name).read_text(encoding="utf-8") != text
        for name, text in original_sources.items()
    ):
        raise IntegrityError("frozen source dependency changed")
    cases = [source.read("cases", key) for key in protocol["case_ids"]]
    if len(cases) != 14 or any(
        digest(case) != key
        for case, key in zip(cases, protocol["case_ids"], strict=True)
    ):
        raise IntegrityError("source-case inventory changed")
    bundle = ROOT / "artifacts/research/cycle15_reflection_source/public_bundle/data"
    paths = sorted(
        {
            path
            for case in cases
            for path in called_apis(case["public_input"]["program"])
        }
    )
    docs, files = {}, {}
    for path in paths:
        app, name = path.split(".")
        file = bundle / "api_docs/standard" / (app + ".json")
        files[file.relative_to(ROOT).as_posix()] = hashlib.sha256(
            file.read_bytes()
        ).hexdigest()
        docs[path] = json.loads(file.read_text(encoding="utf-8"))[name]
    store = RunStore(ROOT / "artifacts/research/post22_public_semantic_view")
    texts = {
        p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8")
        for p in (Path(__file__).resolve(), ROOT / "tests/test_public_semantic_view.py")
    }
    rows = []
    for i, case in enumerate(cases):
        origin_store = RunStore(Path(case["source_store"]))
        request = origin_store.read("worker_requests", case["source_cell"] + "-live")
        task = request["task_id"]
        if task not in {"aa8502b_1", "b7a9ee9_1"}:
            raise IntegrityError("unexpected or reserved task in bounded correction")
        file = bundle / "tasks" / task / "specs.json"
        files[file.relative_to(ROOT).as_posix()] = hashlib.sha256(
            file.read_bytes()
        ).hexdigest()
        instruction = json.loads(file.read_text(encoding="utf-8"))["instruction"]
        view, checks = build_view(case["public_input"], instruction, docs)
        store.write("public_views", digest(view), view)
        rows.append(
            {
                "record": i,
                "source_case_id": protocol["case_ids"][i],
                "view_id": digest(view),
                **checks,
            }
        )
    report = {
        "version": VERSION,
        "source_protocol": digest(protocol),
        "source_snapshot": digest(texts),
        "public_source_file_sha256": files,
        "shared_public_catalog": paths,
        "rows": rows,
        "views": len(rows),
        "credential_literal_occurrences_redacted": sum(
            r["credential_literal_occurrences_redacted"] for r in rows
        ),
        "model_calls": 0,
        "native_executions": 0,
        "api_usd": 0,
        "interpretation": "Bounded public input correction only, not a semantic verifier or learned-effect result; catalog derived from these known-build programs without outcome-based selection.",
    }
    store.bind_provenance({"correction_digest": digest(report)})
    store.write("source_snapshots", digest(texts), texts)
    store.write("reports", digest(report), report)
    if {p.stem for p in (store.root / "public_views").glob("*.json")} != {
        r["view_id"] for r in rows
    }:
        raise IntegrityError("missing or extra corrected public view")
    print(
        json.dumps(
            {
                "report_digest": digest(report),
                **{
                    k: v
                    for k, v in report.items()
                    if k not in {"rows", "public_source_file_sha256"}
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
