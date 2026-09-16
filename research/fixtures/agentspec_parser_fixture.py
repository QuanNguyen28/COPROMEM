"""Native parser/Rule and unchanged interpreter-body checks, with no real actions."""

from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.metadata
import io
import json
import sys
from pathlib import Path

sys.path[:0] = ["/antlr.whl", "/upstream/src"]

from antlr4 import CommonTokenStream, InputStream, ParseTreeWalker
from antlr4.error.ErrorListener import ErrorListener
from rule import Rule
from spec_lang.AgentSpecLexer import AgentSpecLexer
from spec_lang.AgentSpecListener import AgentSpecListener
from spec_lang.AgentSpecParser import AgentSpecParser


def text(predicate="true", event="Tool", enforcement="stop", identifier="fixture"):
    return f"rule @{identifier}\ntrigger {event}\ncheck {predicate}\nenforce {enforcement}\nend"


def parse(raw):
    lexer = AgentSpecLexer(InputStream(raw))
    parser = AgentSpecParser(CommonTokenStream(lexer))
    tree = parser.program()
    return tree, parser.getNumberOfSyntaxErrors()


def record_case(name, function):
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            value = function()
            result = {"value": value, "error_type": None}
        except Exception as exc:  # noqa: BLE001 - preserve every upstream fixture failure
            result = {"value": None, "error_type": type(exc).__name__}
    return {
        "name": name,
        **result,
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
    }


def rule_summary(raw):
    _, errors = parse(raw)
    rule = Rule.from_text(raw)
    return {"rule_id": rule.id, "event": rule.event, "parser_syntax_errors": errors}


def interpreter_class():
    path = Path("/upstream/src/interpreter.py")
    source = path.read_text(encoding="utf-8")
    wanted = {"CustomErrorListener", "RuleInterpreter"}
    nodes = [
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef) and node.name in wanted
    ]
    if {node.name for node in nodes} != wanted:
        raise ValueError("reviewed interpreter class bodies are missing")
    globals_ = {
        "AgentSpecParser": AgentSpecParser,
        "AgentSpecLexer": AgentSpecLexer,
        "AgentSpecListener": AgentSpecListener,
        "ErrorListener": ErrorListener,
        "Rule": Rule,
        "RuleState": object,
        "Action": object,
        "InputStream": InputStream,
        "CommonTokenStream": CommonTokenStream,
        "ParseTreeWalker": ParseTreeWalker,
        "predicate_table": {},
        "ENFORCEMENT_TO_CLASS": {},
    }
    # Compile exact upstream class bodies; bypass only dependency-heavy imports
    # and the unrelated executable demo. No class method is rewritten.
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), globals_)  # noqa: S102 - pinned reviewed source, isolated no-network container
    return globals_["RuleInterpreter"], hashlib.sha256(source.encode()).hexdigest()


def main():
    interpreter, interpreter_hash = interpreter_class()
    cases = []
    for name, raw in (
        ("valid_rule", text()),
        (
            "two_rules_single_Rule_result",
            text(identifier="first", event="First")
            + "\n"
            + text(identifier="last", event="Last"),
        ),
        ("any_event_grammar", text(event="any")),
        ("readme_predicate_before_extension", text(predicate="is_destructive")),
        ("readme_self_examine_spelling", text(enforcement="llm_self_examine")),
        ("implementation_self_reflect_spelling", text(enforcement="llm_self_reflect")),
    ):
        cases.append(record_case(name, lambda raw=raw: rule_summary(raw)))
    for name, action_name, input_ in (
        ("exact_tool_match", "Tool", {}),
        ("text_prefix_trigger", "Other", "Tool argument"),
        ("unmatched_dict_input", "Other", {"argument": "fixture"}),
        ("unmatched_none_input", "finish", None),
    ):
        cases.append(
            record_case(
                name,
                lambda action_name=action_name, input_=input_: Rule.from_text(
                    text()
                ).triggered(action_name, input_),
            )
        )
    for predicate in (
        "true",
        "!true",
        "!!true",
        "!!!true",
        "false",
        "!!false",
        "custom(1)",
    ):

        def evaluate(predicate=predicate):
            raw = text(predicate=predicate)
            tree, errors = parse(raw)
            rule = Rule.from_text(raw)
            value = interpreter(rule, None).eval_predicate(
                tree.rule_(0).checkClause().predicate(0)
            )
            return {
                "predicate": predicate,
                "value": value,
                "parser_syntax_errors": errors,
            }

        cases.append(record_case("predicate_" + predicate, evaluate))

    # Only inspect whether the parsed dispatch key exists in the unchanged source
    # mapping; do not invoke an enforcement method or a real tool/model.
    def invoke_dispatch():
        raw = text(enforcement='invoke_action(Tool, {"argument": "fixture"})')
        tree, errors = parse(raw)
        key = tree.rule_(0).enforceClause().enforcement(0).getText()
        module = ast.parse(Path("/upstream/src/enforcement.py").read_text())
        mappings = [
            node.value
            for node in module.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "ENFORCEMENT_TO_CLASS"
                for target in node.targets
            )
        ]
        keys = [ast.literal_eval(node) for node in mappings[0].keys]
        return {
            "parser_syntax_errors": errors,
            "dispatch_key": key,
            "mapping_contains_key": key in keys,
            "mapping_keys": keys,
        }

    cases.append(record_case("invoke_action_dispatch_mapping", invoke_dispatch))
    print(
        "AGENTSPEC_FIXTURE="
        + json.dumps(
            {
                "cases": cases,
                "python": sys.version,
                "pydantic": importlib.metadata.version("pydantic"),
                "antlr_runtime": importlib.metadata.version("antlr4-python3-runtime"),
                "interpreter_source_sha256": interpreter_hash,
                "native_Rule_and_generated_parser_imported": True,
                "interpreter_class_bodies_unchanged": True,
                "interpreter_module_bootstrap_bypassed": True,
                "predicate_registry": "empty; only literal boolean/custom-symbol behavior tested",
                "real_enforcement_actions": 0,
                "model_calls": 0,
                "benchmark_tasks": 0,
                "limitation": "Authored native-parser/Rule and exact-class-body checks only, not native LangChain policy, predicate quality, recovery or paper-performance reproduction.",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
