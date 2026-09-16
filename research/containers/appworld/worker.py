"""One fresh AppWorld process, reviewed or restricted actions, no evaluator access.

Container isolation protects the host; this syntax policy additionally prevents
ordinary agent code from using implementation internals as extra benchmark tools.
It is not a formal proof of Python sandbox security.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import json
import marshal
import math
import os
import random
import re
import sys
import types
from datetime import datetime
from pathlib import Path

MAX_ACTIONS = 50
MAX_REQUEST_CHARS = 2_500_000

ALLOWED_IMPORTS = {
    "calendar",
    "collections",
    "collections.abc",
    "copy",
    "datetime",
    "functools",
    "itertools",
    "json",
    "math",
    "pendulum",
    "random",
    "re",
}
FORBIDDEN_NAMES = {
    "eval",
    "exec",
    "compile",
    "open",
    "input",
    "getattr",
    "setattr",
    "delattr",
    "globals",
    "locals",
    "vars",
    "dir",
    "help",
    "breakpoint",
    "memoryview",
    "exit",
    "quit",
    "type",
    "object",
    "super",
    "classmethod",
    "staticmethod",
    "property",
    "builtins",
    "apispec",
    "Requester",
    "requester",
    "ApiCollection",
}


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=False,
    )


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def validate_program(program: str, protected_names=None) -> None:
    if not isinstance(program, str) or len(program) > 24_000:
        raise ValueError("action must be a bounded Python string")
    tree = ast.parse(program)
    protected_names = protected_names or set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            item.name not in ALLOWED_IMPORTS for item in node.names
        ):
            raise ValueError("import outside the shared public action language")
        if isinstance(node, ast.ImportFrom):
            if node.level or node.module not in ALLOWED_IMPORTS:
                raise ValueError("import outside the shared public action language")
            if any(
                item.name.startswith("_") or item.name == "*" for item in node.names
            ):
                raise ValueError("private or wildcard import")
        if isinstance(node, (ast.Name, ast.Attribute)):
            name = node.id if isinstance(node, ast.Name) else node.attr
            if name.startswith("_") or name in FORBIDDEN_NAMES:
                raise ValueError("introspection or non-public operation")
            if isinstance(node, ast.Attribute) and isinstance(
                node.ctx, (ast.Store, ast.Del)
            ):
                raise ValueError(  # noqa: TRY004 - prohibited AST operation, not argument type
                    "mutating module/API attributes is not a public action"
                )
            if (
                isinstance(node, ast.Name)
                and isinstance(node.ctx, (ast.Store, ast.Del))
                and name in protected_names
            ):
                raise ValueError("cannot overwrite a native preamble binding")
        if isinstance(node, (ast.ClassDef, ast.Global, ast.Nonlocal)):
            raise ValueError("unsupported stateful language construct")  # noqa: TRY004
        if (
            isinstance(node, ast.alias)
            and node.asname
            and (
                node.asname.startswith("_")
                or node.asname in FORBIDDEN_NAMES
                or node.asname in protected_names
            )
        ):
            raise ValueError("invalid import alias")


def checked_request(value: dict) -> dict:
    if set(value) != {"task_id", "seed", "actions"}:
        raise ValueError("unexpected worker request fields")
    if not re.fullmatch(r"[a-f0-9]{7}_[1-9][0-9]*", value["task_id"]):
        raise ValueError("invalid task ID")
    if type(value["seed"]) is not int or not 0 <= value["seed"] < 2**31:
        raise ValueError("invalid seed")
    if not isinstance(value["actions"], list) or len(value["actions"]) > MAX_ACTIONS:
        raise ValueError("bounded action list required")
    for program in value["actions"]:
        validate_program(program)
    return value


def file_state(directory: Path) -> dict:
    return {
        item.name: hashlib.sha256(item.read_bytes()).hexdigest()
        for item in sorted(directory.iterdir())
        if item.is_file()
    }


def namespace_state(namespace: dict, original_names: set[str]) -> dict:
    serializable, unsupported = {}, {}
    references = {}
    for name in sorted(set(namespace) - original_names):
        if name.startswith("_"):
            continue
        value = namespace[name]
        try:
            serializable[name] = encode_state(value, references)
        except (TypeError, ValueError, RecursionError):
            unsupported[name] = type(value).__name__
    return {"serializable": serializable, "unsupported": unsupported}


def encode_state(value, references=None):
    """Typed/order-preserving object graph, retaining aliases and cycles."""
    references = {} if references is None else references
    if type(value) is float and math.isinf(value):
        return ["float_infinity", "+" if value > 0 else "-"]
    if value is None or type(value) in (bool, int, float, str):
        canonical(value)
        return [type(value).__name__, value]
    if id(value) in references:
        return ["reference", references[id(value)]]
    reference_id = len(references)
    references[id(value)] = reference_id

    def wrap(encoded):
        return ["object", reference_id, encoded]

    if isinstance(value, dict):
        return wrap(
            [
                "dict",
                [
                    [encode_state(k, references), encode_state(v, references)]
                    for k, v in value.items()
                ],
            ]
        )
    if isinstance(value, (list, tuple)):
        return wrap(
            [type(value).__name__, [encode_state(v, references) for v in value]]
        )
    if isinstance(value, (set, frozenset)):
        return wrap(
            [
                type(value).__name__,
                sorted((encode_state(v, {}) for v in value), key=canonical),
            ]
        )
    if isinstance(value, types.ModuleType) and value.__name__ in ALLOWED_IMPORTS:
        return wrap(["module", value.__name__])
    if isinstance(value, types.FunctionType):
        closure = [
            encode_state(cell.cell_contents, references)
            for cell in (value.__closure__ or ())
        ]
        return wrap(
            [
                "function",
                hashlib.sha256(marshal.dumps(value.__code__)).hexdigest(),
                encode_state(value.__defaults__, references),
                encode_state(value.__kwdefaults__, references),
                closure,
            ]
        )
    if (
        isinstance(value, types.BuiltinFunctionType)
        and value.__module__ in ALLOWED_IMPORTS
    ):
        return wrap(["builtin_function", value.__module__, value.__name__])
    if isinstance(value, type) and value.__module__.split(".")[0] in ALLOWED_IMPORTS:
        return wrap(["public_type", value.__module__, value.__qualname__])
    if (
        isinstance(value, datetime)
        or value.__class__.__module__.split(".")[0] in {"datetime", "pendulum"}
    ) and hasattr(value, "isoformat"):
        return wrap(["datetime_value", value.__class__.__qualname__, value.isoformat()])
    raise TypeError("unsupported namespace object")


def execute_recorded(world, program: str, protected_names=None) -> str:
    try:
        validate_program(program, protected_names)
    except (ValueError, SyntaxError) as exc:
        return f"Execution failed. Shared action policy: {type(exc).__name__}: {exc}"
    return world.execute(program)


def run(value: dict, *, stream: bool = False) -> dict:
    # Shape validation is strict. Action-policy errors become public observations
    # inside the episode, allowing no-memory agents the same self-repair ability.
    original_actions = value["actions"]
    checked_request({**value, "actions": []})
    if (
        not isinstance(original_actions, list)
        or len(original_actions) > MAX_ACTIONS
        or any(not isinstance(p, str) or len(p) > 24_000 for p in original_actions)
    ):
        raise ValueError("invalid initial action list")
    if os.getuid() == 0:
        raise RuntimeError("execution worker must not run as root")
    if any(
        word in key.upper()
        for key in os.environ
        for word in ("API_KEY", "TOKEN", "SECRET", "PASSWORD")
    ):
        raise RuntimeError("credential-like environment variables are prohibited")
    root = Path("/sandbox")
    if (root / "data/tasks" / value["task_id"] / "ground_truth").exists():
        raise RuntimeError("ground truth must not be mounted in the execution worker")
    if (root / "experiments/outputs/canonical/tasks" / value["task_id"]).exists():
        raise RuntimeError("each worker requires a fresh output directory")
    from appworld import AppWorld

    results = []
    with AppWorld(
        task_id=value["task_id"],
        experiment_name="canonical",
        load_ground_truth=False,
        random_seed=value["seed"],
        max_interactions=MAX_ACTIONS + 4,
        max_api_calls_per_interaction=100,
        timeout_seconds=15,
        raise_on_unsafe_syntax=True,
        null_patch_unsafe_execution=True,
    ) as world:
        initial_names = set(world.shell.user_ns)
        dbs = Path(world.output_db_home_path_on_disk)
        before = file_state(dbs)

        def snapshot():
            completion = world.task_completed()
            state = {
                "encoding": "typed-public-bindings-v3-infinity",
                "database_files": file_state(dbs),
                "namespace": namespace_state(world.shell.user_ns, initial_names),
                "clock": datetime.now().isoformat(),  # noqa: DTZ005 - native benchmark clock is naive
                "random_state": sha(random.getstate()),
            }
            return {
                "request_id": sha(
                    {**value, "actions": [item["program"] for item in results]}
                ),
                "task_id": value["task_id"],
                "action_limit": MAX_ACTIONS,
                "native_version": importlib.metadata.version("appworld"),
                "public_instruction": world.task.instruction,
                "results": list(results),
                "harness_only_state": state,
                "state_digest": sha(state),
                "initial_database_files": before,
                "completion_flag": completion,
                "model_calls": 0,
                "native_evaluation": "not run in execution worker",
                "status": "completed",
                "guards_enabled": True,
                "limitations": "Harness state is not agent-visible; unsupported state is unverified. Completion flag is not task success.",
            }

        report = snapshot()
        for program in original_actions:
            results.append(
                {
                    "program": program,
                    "output": execute_recorded(world, program, initial_names),
                }
            )
            report = snapshot()
        if stream:
            print("COPROMEM_WORKER_RESULT=" + canonical(report), flush=True)
            for raw in sys.stdin:
                if len(raw) > 100_000:
                    raise ValueError("stream request too large")
                message = json.loads(raw)
                if message == {"close": True}:
                    break
                if set(message) != {"program"} or len(results) >= MAX_ACTIONS:
                    raise ValueError("invalid stream action or episode limit")
                program = message["program"]
                if not isinstance(program, str) or len(program) > 24_000:
                    raise ValueError("invalid stream action")
                results.append(
                    {
                        "program": program,
                        "output": execute_recorded(world, program, initial_names),
                    }
                )
                report = snapshot()
                print("COPROMEM_WORKER_RESULT=" + canonical(report), flush=True)
    return report


def main():
    stream = "--stream" in sys.argv[1:]
    raw = (
        sys.stdin.readline(MAX_REQUEST_CHARS + 1)
        if stream
        else sys.stdin.read(MAX_REQUEST_CHARS + 1)
    )
    if len(raw) > MAX_REQUEST_CHARS:
        raise ValueError("request too large")
    value = json.loads(raw)
    report = run(value, stream=stream)
    prefix = "COPROMEM_WORKER_DONE=" if stream else "COPROMEM_WORKER_RESULT="
    print(prefix + canonical(report), flush=True)


if __name__ == "__main__":
    main()
