"""Structural policy only; never execute a proposed monitor on the host."""

import ast
import keyword

POLICY_VERSION = "plain-functions-public-ast-no-io-v1"
BUILTIN_NAMES = (
    "all",
    "any",
    "bool",
    "dict",
    "enumerate",
    "float",
    "int",
    "isinstance",
    "len",
    "list",
    "max",
    "min",
    "range",
    "set",
    "sorted",
    "str",
    "sum",
    "tuple",
    "zip",
)
AST_UTILITIES = (
    "parse",
    "walk",
    "iter_child_nodes",
    "iter_fields",
    "dump",
    "unparse",
    "literal_eval",
    "get_source_segment",
)
FORBIDDEN_NAMES = {
    "open",
    "eval",
    "exec",
    "compile",
    "getattr",
    "setattr",
    "delattr",
    "vars",
    "globals",
    "locals",
    "dir",
    "input",
    "print",
    "help",
    "type",
    "object",
    "super",
    "classmethod",
    "staticmethod",
    "property",
    "breakpoint",
    "memoryview",
    "bytes",
    "bytearray",
}
FORBIDDEN_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.ClassDef,
    ast.Global,
    ast.Nonlocal,
    ast.Try,
    ast.TryStar,
    ast.Raise,
    ast.With,
    ast.AsyncWith,
    ast.AsyncFunctionDef,
    ast.AsyncFor,
    ast.Await,
    ast.Yield,
    ast.YieldFrom,
    ast.Lambda,
)


class PolicyError(ValueError):
    pass


def validate_public_input(value):
    if type(value) is not dict or set(value) != {"program", "present_names"}:
        raise PolicyError("runtime_input_fields")
    program, names = value["program"], value["present_names"]
    if not isinstance(program, str) or len(program.encode("utf-8")) > 50000:
        raise PolicyError("runtime_program_limit")
    if (
        type(names) is not list
        or len(names) > 128
        or any(
            not isinstance(n, str) or not n.isidentifier() or keyword.iskeyword(n)
            for n in names
        )
        or names != sorted(set(names))
    ):
        raise PolicyError("runtime_name_schema")
    ast.parse(program)


def validate_source(source):
    if not isinstance(source, str) or not source or len(source.encode("utf-8")) > 16000:
        raise PolicyError("source_length")
    tree = ast.parse(source)
    nodes = list(ast.walk(tree))
    if len(nodes) > 3000:
        raise PolicyError("source_complexity")
    if not tree.body or any(not isinstance(n, ast.FunctionDef) for n in tree.body):
        raise PolicyError("plain_functions_only")
    functions = {n.name: n for n in tree.body}
    if len(functions) != len(tree.body) or "judge" not in functions:
        raise PolicyError("unique_judge_required")
    for node in nodes:
        if isinstance(node, FORBIDDEN_NODES):
            raise PolicyError("forbidden_statement")
        if isinstance(node, ast.Attribute) and (
            node.attr.startswith("_") or not isinstance(node.ctx, ast.Load)
        ):
            raise PolicyError("private_or_writable_attribute")
        names = []
        if isinstance(node, ast.Name):
            names.append(node.id)
        if isinstance(node, ast.arg):
            names.append(node.arg)
            if node.annotation is not None:
                raise PolicyError("parameter_annotation")
        if isinstance(node, ast.keyword) and node.arg is not None:
            names.append(node.arg)
        if isinstance(node, ast.FunctionDef):
            names.append(node.name)
            if (
                node not in tree.body
                or node.decorator_list
                or node.returns is not None
                or node.args.defaults
                or any(v is not None for v in node.args.kw_defaults)
                or getattr(node, "type_params", ())
            ):
                raise PolicyError("function_evaluation_or_nesting")
        if any(n.startswith("_") or n in FORBIDDEN_NAMES for n in names):
            raise PolicyError("forbidden_name")
    args = functions["judge"].args
    if (
        [a.arg for a in args.args] != ["program", "present_names"]
        or args.posonlyargs
        or args.kwonlyargs
        or args.vararg
        or args.kwarg
    ):
        raise PolicyError("judge_signature")
    return {
        "policy": POLICY_VERSION,
        "node_count": len(nodes),
        "functions": list(functions),
    }
