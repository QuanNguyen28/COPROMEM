"""Human-written warning rules for the inspected public all-artists task families.

Not a learned contract, a general Python verifier, or a universal success oracle.
Target programs are parsed and never executed. Unknown forms are explicit.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import runpy
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest

VIEW = runpy.run_path(str(Path(__file__).with_name("public_semantic_view.py")))
VERSION = "manual-public-all-artists-coverage-diagnostic-v1"


def same(left, right):
    return ast.dump(left) == ast.dump(right)


def name(node, value):
    return isinstance(node, ast.Name) and node.id == value


def constant(node, value):
    return (
        isinstance(node, ast.Constant)
        and type(node.value) is type(value)
        and node.value == value
    )


def assigned(statement):
    if (
        isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
    ):
        return statement.targets[0].id, statement.value
    return None, None


def prior_value(body, before, variable):
    for statement in reversed(body[:before]):
        target, value = assigned(statement)
        if target == variable:
            return value
        if any(
            isinstance(n, ast.Name) and n.id == variable for n in ast.walk(statement)
        ):
            return None  # Unanalysed intervening access/mutation: do not infer a value.
    return None


def empty_list(node):
    return isinstance(node, ast.List) and not node.elts


def consumer(body, after, variable):
    for statement in body[after + 1 :]:
        if isinstance(statement, ast.For) and name(statement.iter, variable):
            return statement
        if any(
            isinstance(n, ast.Name) and n.id == variable for n in ast.walk(statement)
        ):
            return None
    return None


def extend_target(statement, response):
    if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
        return None
    call = statement.value
    if (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "extend"
        and isinstance(call.func.value, ast.Name)
        and len(call.args) == 1
        and name(call.args[0], response)
        and not call.keywords
    ):
        return call.func.value.id
    return None


def advances(statement, index):
    return (
        isinstance(statement, ast.AugAssign)
        and name(statement.target, index)
        and isinstance(statement.op, ast.Add)
        and constant(statement.value, 1)
    )


def only_break(statements):
    return len(statements) == 1 and isinstance(statements[0], ast.Break)


def result(status, *reasons):
    return {"status": status, "reasons": list(reasons)}


def pagination(tree, expected, docs, presence):
    parameters = {p["name"]: p for p in docs[expected]["parameters"]}
    if (
        not {"page_index", "page_limit"} <= parameters.keys()
        or parameters["page_index"].get("default") != 0
    ):
        return result("unknown", "unsupported_public_pagination_spec")
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and VIEW["api_path"](n) == expected
    ]
    if not calls:
        for i, statement in enumerate(tree.body):
            if (
                isinstance(statement, ast.For)
                and isinstance(statement.iter, ast.Name)
                and empty_list(prior_value(tree.body, i, statement.iter.id))
            ):
                return result(
                    "risk",
                    "explicit_empty_collection_consumed_without_required_producer",
                )
        return result(
            "unknown", "required_producer_not_observed_preexisting_values_unknown"
        )
    if len(calls) != 1:
        return result("unknown", "multiple_required_producer_calls")
    call = calls[0]
    for i, statement in enumerate(tree.body):
        target, value = assigned(statement)
        if value is call:
            if consumer(tree.body, i, target) is not None:
                return result(
                    "risk", "single_page_producer_for_full_collection_obligation"
                )
            return result("unknown", "producer_consumer_connection_not_established")
    loops = [
        (i, n)
        for i, n in enumerate(tree.body)
        if isinstance(n, ast.While) and call in list(ast.walk(n))
    ]
    if len(loops) != 1:
        return result("unknown", "unsupported_producer_control_flow")
    position, loop = loops[0]
    if not constant(loop.test, True) or loop.orelse or not loop.body:
        return result("unknown", "unsupported_loop_condition")
    response, value = assigned(loop.body[0])
    if value is not call or response is None:
        return result("unknown", "response_binding_not_established")
    kwargs = {k.arg: k.value for k in call.keywords}
    index_node = kwargs.get("page_index")
    if not isinstance(index_node, ast.Name):
        if index_node is None or isinstance(index_node, ast.Constant):
            return result("risk", "repeated_call_uses_fixed_or_default_page")
        return result("unknown", "unsupported_page_index_expression")
    index = index_node.id
    if not any(advances(n, index) for n in ast.walk(loop)):
        if any(
            isinstance(n, ast.Name) and n.id == index and isinstance(n.ctx, ast.Store)
            for n in ast.walk(loop)
        ):
            return result("unknown", "unrecognized_page_index_update")
        return result("risk", "requested_page_index_does_not_advance")
    collector, assumptions = None, []
    body = loop.body
    # Exact two common idioms, including statement order and break paths.
    if len(body) in {4, 5} and isinstance(body[1], ast.If):
        guard = body[1]
        if (
            isinstance(guard.test, ast.UnaryOp)
            and isinstance(guard.test.op, ast.Not)
            and name(guard.test.operand, response)
            and only_break(guard.body)
            and not guard.orelse
            and advances(body[-1], index)
        ):
            collector = extend_target(body[2], response)
            if len(body) == 5:
                short = body[3]
                limit = kwargs.get(
                    "page_limit", ast.Constant(parameters["page_limit"].get("default"))
                )
                expected_test = ast.Compare(
                    left=ast.Call(
                        func=ast.Name(id="len", ctx=ast.Load()),
                        args=[ast.Name(id=response, ctx=ast.Load())],
                        keywords=[],
                    ),
                    ops=[ast.Lt()],
                    comparators=[limit],
                )
                if (
                    not isinstance(short, ast.If)
                    or not same(short.test, expected_test)
                    or not only_break(short.body)
                    or short.orelse
                ):
                    collector = None
                else:
                    assumptions.append(
                        "short_page_termination_requires_an_API_guarantee_not_established_here"
                    )
    elif len(body) == 2 and isinstance(body[1], ast.If):
        guard = body[1]
        if (
            name(guard.test, response)
            and len(guard.body) == 2
            and only_break(guard.orelse)
            and advances(guard.body[1], index)
        ):
            collector = extend_target(guard.body[0], response)
    if collector is None:
        return result(
            "unknown", "advancement_accumulation_or_exit_not_in_supported_pattern"
        )
    if response == collector or response == index or collector == index:
        return result("risk", "pagination_response_collector_index_alias")
    if consumer(tree.body, position, collector) is None:
        return result("unknown", "accumulated_collection_not_linked_to_consumer")
    if not constant(prior_value(tree.body, position, index), 0):
        return result("unknown", "initial_page_zero_not_established")
    initial = prior_value(tree.body, position, collector)
    if not empty_list(initial):
        if initial is not None or not presence.get(collector, False):
            return result("unknown", "collector_initialization_not_established")
        assumptions.append("preexisting_collector_value_and_type_are_unobserved")
    return result(
        "pattern_observed",
        "response_accumulates_into_consumed_collection_with_advancing_pages",
        *assumptions,
        "API_stability_termination_and_downstream_correctness_not_proved",
    )


def subscript(node, key):
    return isinstance(node, ast.Subscript) and constant(node.slice, key)


def consumer_risks(tree, classical):
    risks = []
    if classical:
        filters = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Compare)
            and subscript(n.left, "genre")
            and len(n.ops) == 1
            and isinstance(n.ops[0], ast.Eq)
            and len(n.comparators) == 1
            and isinstance(n.comparators[0], ast.Constant)
        ]
        if any(not constant(n.comparators[0], "classical") for n in filters):
            risks.append("genre_comparison_differs_from_public_classical_requirement")
    for node in ast.walk(tree):
        target, value = assigned(node)
        if (
            target is None
            or not subscript(value, "id")
            or not subscript(value.value, 0)
            or not subscript(value.value.value, "artists")
        ):
            continue
        if any(
            isinstance(n, ast.Call)
            and VIEW["api_path"](n) == "spotify.follow_artist"
            and any(k.arg == "artist_id" and name(k.value, target) for k in n.keywords)
            for n in ast.walk(tree)
        ):
            risks.append(
                "first_artist_selection_feeds_follow_call_not_all_artist_certificate"
            )
    return sorted(set(risks))


def inspect(view):
    if (
        set(view)
        != {"version", "program", "task_instruction", "public_presence", "api_docs"}
        or view["version"] != VIEW["VERSION"]
    ):
        raise ValueError("manual control accepts only the shared public semantic view")
    public = {"program": view["program"], "envelope": view["public_presence"]}
    if not VIEW["CHECK"]["analysis_input"](public, context=True)["covered"]:
        raise ValueError("incomplete public presence coverage")
    for path, doc in view["api_docs"].items():
        if (
            set(doc) != set(VIEW["DOC_FIELDS"])
            or path != doc["app_name"] + "." + doc["api_name"]
        ):
            raise ValueError("unexpected public API metadata")
    instruction = view["task_instruction"].lower()
    tree = ast.parse(view["program"])
    presence = VIEW["CHECK"]["validate_public"](
        {"program": view["program"], "envelope": view["public_presence"]}
    )
    if (
        "follow all" not in instruction
        or "artist" not in instruction
        or "spotify" not in instruction
    ):
        return {
            "version": VERSION,
            "scope": None,
            "pagination": result("out_of_scope"),
            "consumer_risks": [],
            "decision": "abstain",
        }
    classical = "classical" in instruction and "playlist" in instruction
    expected = (
        "spotify.show_playlist_library"
        if classical
        else "spotify.show_liked_songs"
        if "liked" in instruction and "song" in instruction
        else None
    )
    if expected is None or expected not in view["api_docs"]:
        return {
            "version": VERSION,
            "scope": None,
            "pagination": result("out_of_scope"),
            "consumer_risks": [],
            "decision": "abstain",
        }
    page = pagination(tree, expected, view["api_docs"], presence)
    risks = consumer_risks(tree, classical)
    return {
        "version": VERSION,
        "scope": expected,
        "pagination": page,
        "consumer_risks": risks,
        "decision": "warn"
        if page["status"] == "risk" or risks
        else "no_detected_risk"
        if page["status"] == "pattern_observed"
        else "abstain",
    }


def main():
    root = Path(__file__).resolve().parents[2]
    views = RunStore(root / "artifacts/research/post22_public_semantic_view")
    view_key = "b0310aa011240150c6efa344d575ae24579681072b44b87a39631233c436f74d"
    inputs = views.read("reports", view_key)
    source = RunStore(root / "artifacts/research/cycle22_static_name_check")
    source_key = "44089b0c774a60e7f942675dbccb0b77e3d2e81f6fdeb68af51205a8383dfe8a"
    original = source.read("reports", source_key)
    protocol = source.read("protocol", "preregistration")
    if (
        digest(inputs) != view_key
        or digest(original) != source_key
        or digest(protocol) != inputs["source_protocol"]
        or len(inputs["rows"]) != 14
    ):
        raise IntegrityError("frozen source report changed")
    for store, snapshot_id in (
        (views, inputs["source_snapshot"]),
        (source, protocol["source_snapshot"]),
    ):
        snapshot = store.read("source_snapshots", snapshot_id)
        if digest(snapshot) != snapshot_id or any(
            (root / n).read_text(encoding="utf-8") != t for n, t in snapshot.items()
        ):
            raise IntegrityError("frozen input/checker dependency changed")
    for path, expected in inputs["public_source_file_sha256"].items():
        if hashlib.sha256((root / path).read_bytes()).hexdigest() != expected:
            raise IntegrityError("public source documentation changed")
    b = {r["case_index"]: r for r in original["rows"] if r["context"]}
    rows = []
    for i, row in enumerate(inputs["rows"]):
        if row["record"] != i or row["source_case_id"] != protocol["case_ids"][i]:
            raise IntegrityError("public-view row binding changed")
        view = views.read("public_views", row["view_id"])
        if digest(view) != row["view_id"]:
            raise IntegrityError("public view content changed")
        decision = inspect(view)
        if digest(view) != row["view_id"] or inspect(copy.deepcopy(view)) != decision:
            raise IntegrityError("public-view mutation or unstable manual decision")
        # Outcomes and source identifiers are attached AFTER the public-only call.
        case = source.read("cases", row["source_case_id"])
        if (
            digest(case) != row["source_case_id"]
            or b[i]["case_id"] != row["source_case_id"]
        ):
            raise IntegrityError("source-case identity changed")
        b_warn = bool(b[i]["parsed"]["warning_names"])
        rows.append(
            {
                "record": i,
                "view_id": row["view_id"],
                "source_case_id": row["source_case_id"],
                "manual": decision,
                "b_warning": b_warn,
                "combined_decision": "warn" if b_warn else decision["decision"],
                "saved_native_success_audit_only": case[
                    "final_native_success_audit_only"
                ],
            }
        )
    # Recheck the actual record-13 information-loss counterexample, without
    # executing either program. The altered view is preserved as constructed.
    base = views.read("public_views", inputs["rows"][13]["view_id"])
    raw = copy.deepcopy(source.read("cases", protocol["case_ids"][13])["public_input"])
    tree = ast.parse(raw["program"])
    changed = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Compare)
            and subscript(node.left, "genre")
            and len(node.comparators) == 1
            and constant(node.comparators[0], "classical")
        ):
            node.comparators[0].value = "__counterexample_other_genre__"
            changed += 1
    if changed != 1:
        raise IntegrityError("actual-source genre counterexample changed")
    raw["program"] = ast.unparse(tree)
    altered, _ = VIEW["build_view"](raw, base["task_instruction"], base["api_docs"])
    if altered == base:
        raise IntegrityError("semantic genre collision remains")
    mutation = {
        "original_view_id": digest(base),
        "altered_view_id": digest(altered),
        "altered_manual_decision": inspect(altered),
        "changed_genre_comparisons": changed,
        "constructed_only_not_native": True,
    }
    totals = {
        "records": len(rows),
        "pagination_risk_indices": [
            r["record"] for r in rows if r["manual"]["pagination"]["status"] == "risk"
        ],
        "consumer_risk_indices": [
            r["record"] for r in rows if r["manual"]["consumer_risks"]
        ],
        "combined_warn_native_failure": sum(
            r["combined_decision"] == "warn"
            and not r["saved_native_success_audit_only"]
            for r in rows
        ),
        "combined_warn_native_success": sum(
            r["combined_decision"] == "warn" and r["saved_native_success_audit_only"]
            for r in rows
        ),
        "added_warnings_on_native_failure": [
            r["record"]
            for r in rows
            if not r["b_warning"]
            and r["combined_decision"] == "warn"
            and not r["saved_native_success_audit_only"]
        ],
        "added_warnings_on_native_success": [
            r["record"]
            for r in rows
            if not r["b_warning"]
            and r["combined_decision"] == "warn"
            and r["saved_native_success_audit_only"]
        ],
        "combined_abstention_indices": [
            r["record"] for r in rows if r["combined_decision"] == "abstain"
        ],
        "combined_no_risk_native_failure": sum(
            r["combined_decision"] == "no_detected_risk"
            and not r["saved_native_success_audit_only"]
            for r in rows
        ),
        "combined_no_risk_native_success": sum(
            r["combined_decision"] == "no_detected_risk"
            and r["saved_native_success_audit_only"]
            for r in rows
        ),
    }
    texts = {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
        for p in (
            Path(__file__).resolve(),
            root / "tests/test_manual_coverage_control.py",
            root / "research/058_POST_GATE_MANUAL_CONTROL_DIAGNOSTIC.md",
        )
    }
    report = {
        "version": VERSION,
        "source_report": source_key,
        "public_input_report": view_key,
        "source_snapshot": digest(texts),
        "rows": rows,
        "aggregate": totals,
        "genre_counterexample": mutation,
        "manual_record_inspections": 28,
        "constructed_mutation_inspections": 1,
        "model_calls": 0,
        "native_executions": 0,
        "api_usd": 0,
        "task_beneficial_flips": None,
        "task_harmful_flips": None,
        "learned_component_incremental_value": None,
        "interpretation": "Post-hoc known-build human-written warning diagnostic, not learned or held-out efficacy, native failure relabeling, or a sound semantic certificate.",
    }
    store = RunStore(root / "artifacts/research/post22_manual_coverage_control")
    store.bind_provenance({"report_digest": digest(report)})
    store.write("source_snapshots", digest(texts), texts)
    store.write("constructed_views", digest(altered), altered)
    store.write("reports", digest(report), report)
    print(
        json.dumps(
            {
                "report_digest": digest(report),
                **{k: v for k, v in report.items() if k != "rows"},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
