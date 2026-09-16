"""Linux-container driver, appended to the policy source; not imported on host."""

# The policy definitions are prepended verbatim before this driver is executed.
# ruff: noqa: F821

import builtins
import hashlib
import json
import resource
import signal
import sys
import types

DRIVER_VERSION = "isolated-public-input-monitor-driver-v1"


def canonical_json(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def content_digest(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class CPUTimeExceeded(BaseException):
    pass


def cpu_limit(signum, frame):
    raise CPUTimeExceeded()


def ast_facade():
    # Do not expose module globals such as ast.sys through a real module object.
    members = {
        name: item
        for name, item in vars(ast).items()
        if not name.startswith("_")
        and isinstance(item, type)
        and issubclass(item, ast.AST)
    }
    members.update({name: getattr(ast, name) for name in AST_UTILITIES})
    return types.SimpleNamespace(**members)


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (1, 2))
    signal.signal(signal.SIGXCPU, cpu_limit)
    payload = json.loads(sys.stdin.read(80000))
    if type(payload) is not dict or set(payload) != {"source", "input"}:
        raise ValueError("invalid driver envelope")
    validate_public_input(payload["input"])
    result = {
        "version": DRIVER_VERSION,
        "source_digest": content_digest(payload["source"]),
        "input_digest": content_digest(payload["input"]),
        "status": "pending",
        "verdict": None,
        "error_type": None,
    }
    try:
        validate_source(payload["source"])
    except (PolicyError, SyntaxError, ValueError, TypeError, RecursionError) as exc:
        result.update(status="policy_rejected", error_type=type(exc).__name__)
    else:
        namespace = {
            "__builtins__": {name: getattr(builtins, name) for name in BUILTIN_NAMES},
            "ast": ast_facade(),
        }
        try:
            exec(compile(payload["source"], "<proposed-monitor>", "exec"), namespace)  # noqa: S102 -- restricted monitor, only in the isolated container
            verdict = namespace["judge"](
                payload["input"]["program"], tuple(payload["input"]["present_names"])
            )
            if type(verdict) is bool or verdict is None:
                result.update(status="ok", verdict=verdict)
            else:
                result.update(status="invalid_result", error_type="NonBooleanResult")
        except CPUTimeExceeded:
            result.update(status="cpu_timeout", error_type="CPUTimeExceeded")
        except BaseException as exc:  # noqa: BLE001 -- account for every untrusted monitor failure without exposing messages
            result.update(status="runtime_error", error_type=type(exc).__name__)
    print(canonical_json(result), flush=True)


if __name__ == "__main__":
    main()
