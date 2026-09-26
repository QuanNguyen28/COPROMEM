#!/usr/bin/env python3
"""Static, zero-cost compatibility gate for the official-ReMe pilot.

This does not alter upstream source or contact a model endpoint.  It documents
the interfaces that a locked route must implement before the official source
can be used without a local lifecycle/executor adaptation.
"""
from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

SOURCE = pathlib.Path("/home/xiqhq/copromem-reme")
EXPECTED_COMMIT = "2f37a159b72a04ac1885a7db7f1a663a833e7791"
EXPECTED_DIGEST = "5d2706b7b0e304475c71778b9336a733874e2492f4fdb5d311a2914751fe47fa"


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(SOURCE), *args], text=True).strip()


def main() -> int:
    if git("rev-parse", "HEAD") != EXPECTED_COMMIT:
        raise RuntimeError("pinned ReMe commit mismatch")
    # This deliberately matches audit_pinned_reme.sh, rather than inventing a
    # different tree digest that includes filenames or untracked bytecode.
    digest = subprocess.check_output(
        "git ls-files -z | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}'",
        shell=True,
        text=True,
        cwd=SOURCE,
    ).strip()
    print(f"source_commit={EXPECTED_COMMIT}")
    print(f"source_digest_calculated={digest}")
    print(f"source_digest_expected={EXPECTED_DIGEST}")

    if digest != EXPECTED_DIGEST:
        raise RuntimeError("pinned ReMe tracked-content digest mismatch")

    agent_path = SOURCE / "benchmark/appworld/appworld_react_agent.py"
    agent = ast.parse(agent_path.read_text(encoding="utf-8"))
    create_calls = [node for node in ast.walk(agent) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute) and node.func.attr == "create"]
    chat_call = next((node for node in create_calls if any(k.arg == "model" for k in node.keywords)), None)
    if chat_call is None:
        raise RuntimeError("upstream AppWorld chat-completion call not found")
    kwargs = sorted(k.arg for k in chat_call.keywords if k.arg)
    print("upstream_executor_completion_kwargs=" + ",".join(kwargs))
    print("upstream_executor_native_tools=" + str("tools" in kwargs).lower())
    print("upstream_executor_forced_tool_choice=" + str("tool_choice" in kwargs).lower())
    print("upstream_executor_protocol=code_fence_then_world.execute")

    config = (SOURCE / "reme_ai/config/default.yaml").read_text(encoding="utf-8")
    required_flow = "RecallVectorStoreOp()"
    required_embedding = "embedding_model:\n  default:\n    backend: openai_compatible\n    model_name: text-embedding-v4"
    if required_flow not in config or required_embedding not in config:
        raise RuntimeError("expected official ReMe retrieval/embedding configuration absent")
    print("upstream_retrieval=RecallVectorStoreOp")
    print("upstream_embedding_backend=openai_compatible")
    print("upstream_embedding_model=text-embedding-v4")
    print("locked_route_model=deepseek/deepseek-v4.1-flash")
    print("locked_route_documented_output=text")
    print("locked_route_embedding_compatibility=not-established")
    print("result=FAIL_CLOSED_ROUTE_ADAPTER_REQUIRED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
